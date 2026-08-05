"""Persistent, expiring recent-conversation context for ALFRED."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from context.context_models import ConversationTurn
from context.state_repository import AgentStateRepository, parse_datetime, utc_now_iso


DEFAULT_SESSION_ID = "default"
MAX_TURNS = 10
TURN_TTL_DAYS = 14
MAX_PROMPT_CHARS = 5_500

_CONTEXTUAL_PATTERNS = [
    re.compile(r"^(?:yes|no|yep|nope|correct|confirm|cancel|do it|go ahead)[.!]?$", re.I),
    re.compile(r"^(?:open|show|read|use|send|delete|remove|archive|rename|move|edit|update)\s+(?:it|that|this|one|the\s+(?:first|second|third|last)\s+one)\b", re.I),
    re.compile(r"^(?:the\s+)?(?:first|second|third|last)\s+one\b", re.I),
    re.compile(r"^(?:make|change|move|rename|send|open)\s+(?:it|that|this)\b", re.I),
    re.compile(r"^(?:continue|resume|finish)\s+(?:it|that|the task|the workflow)?[.!]?$", re.I),
]


class ConversationContext:
    def __init__(
        self,
        repository: AgentStateRepository | None = None,
        *,
        max_turns: int = MAX_TURNS,
        ttl_days: int = TURN_TTL_DAYS,
        ttl_minutes: int | None = None,
    ) -> None:
        self.repository = repository or AgentStateRepository()
        self.max_turns = max(1, max_turns)
        self.ttl = (
            timedelta(minutes=max(1, ttl_minutes))
            if ttl_minutes is not None
            else timedelta(days=max(1, ttl_days))
        )

    @staticmethod
    def normalize_session_id(session_id: str | None) -> str:
        value = str(session_id or DEFAULT_SESSION_ID).strip()
        return value[:100] or DEFAULT_SESSION_ID

    def _prune(self, session_id: str) -> None:
        cutoff = (datetime.now(timezone.utc) - self.ttl).isoformat()
        with self.repository.connect() as connection:
            connection.execute(
                "DELETE FROM conversation_turns WHERE session_id = ? AND created_at < ?",
                (session_id, cutoff),
            )
            connection.execute(
                """
                DELETE FROM conversation_turns
                WHERE session_id = ? AND id NOT IN (
                    SELECT id FROM conversation_turns
                    WHERE session_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                )
                """,
                (session_id, session_id, self.max_turns),
            )

    def add_turn(
        self,
        *,
        session_id: str | None,
        user_text: str,
        assistant_text: str,
        route: str,
        response_type: str,
    ) -> None:
        sid = self.normalize_session_id(session_id)
        with self.repository.connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation_turns (
                    session_id, user_text, assistant_text, route,
                    response_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    user_text.strip()[:4_000],
                    assistant_text.strip()[:8_000],
                    route or "chat",
                    response_type or "chat",
                    utc_now_iso(),
                ),
            )
        self._prune(sid)

    def recent(self, session_id: str | None, *, limit: int = 8) -> list[ConversationTurn]:
        sid = self.normalize_session_id(session_id)
        self._prune(sid)
        safe_limit = max(1, min(limit, self.max_turns))
        with self.repository.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversation_turns
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (sid, safe_limit),
            ).fetchall()
        rows = list(reversed(rows))
        return [
            ConversationTurn(
                user_text=str(row["user_text"]),
                assistant_text=str(row["assistant_text"]),
                route=str(row["route"]),
                response_type=str(row["response_type"]),
                created_at=parse_datetime(str(row["created_at"])) or datetime.now(timezone.utc),
            )
            for row in rows
        ]

    def last_turn(self, session_id: str | None) -> ConversationTurn | None:
        turns = self.recent(session_id, limit=1)
        return turns[-1] if turns else None

    def last_route(self, session_id: str | None) -> str | None:
        turn = self.last_turn(session_id)
        return turn.route if turn else None

    def clear(self, session_id: str | None) -> int:
        sid = self.normalize_session_id(session_id)
        with self.repository.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM conversation_turns WHERE session_id = ?",
                (sid,),
            )
        return int(cursor.rowcount)

    def is_contextual_follow_up(self, command: str) -> bool:
        text = re.sub(r"\s+", " ", command.strip())
        if not text:
            return False
        if len(text.split()) <= 5 and any(
            token in text.casefold()
            for token in ("it", "that", "this", "one", "yes", "no", "continue", "resume")
        ):
            return True
        return any(pattern.search(text) for pattern in _CONTEXTUAL_PATTERNS)

    def build_prompt_context(self, session_id: str | None, *, limit: int = 8) -> str:
        turns = self.recent(session_id, limit=limit)
        if not turns:
            return ""
        lines = [
            "Recent persisted conversation context:",
            "Use it to resolve follow-ups. New instructions override older context.",
            "Do not claim an old action is still pending unless pending-action state says so.",
        ]
        for turn in turns:
            lines.append(f"User ({turn.route}): {turn.user_text[:750]}")
            lines.append(f"ALFRED: {turn.assistant_text[:1_000]}")
        return "\n".join(lines)[:MAX_PROMPT_CHARS]

    def snapshot(self, session_id: str | None) -> dict:
        sid = self.normalize_session_id(session_id)
        turns = self.recent(sid, limit=self.max_turns)
        return {
            "session_id": sid,
            "turns": [turn.to_dict() for turn in turns],
            "count": len(turns),
            "ttl_days": int(self.ttl.total_seconds() // 86400),
            "persistent": True,
        }


@lru_cache(maxsize=1)
def get_conversation_context() -> ConversationContext:
    return ConversationContext()
