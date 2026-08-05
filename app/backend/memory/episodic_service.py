"""Persistent episodic memory for notable past actions and outcomes."""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from typing import Any

from context.state_repository import AgentStateRepository, utc_now_iso
from memory.memory_service import STOP_WORDS, normalize_memory_text


MAX_EPISODES = 1_000
DEFAULT_LIMIT = 5


def _tokens(text: str) -> list[str]:
    return [
        token for token in re.findall(r"[a-z0-9']+", text.casefold())
        if len(token) > 1 and token not in STOP_WORDS
    ]


class EpisodicMemoryService:
    def __init__(self, repository: AgentStateRepository | None = None) -> None:
        self.repository = repository or AgentStateRepository()

    def record(
        self,
        *,
        session_id: str,
        route: str,
        event_type: str,
        summary: str,
        workflow_id: str | None = None,
        importance: float = 0.55,
    ) -> int | None:
        cleaned = re.sub(r"\s+", " ", str(summary or "").strip())
        if not cleaned or len(cleaned) < 8:
            return None
        if route == "email":
            # Preserve outcome-level context, not full email bodies.
            cleaned = cleaned[:700]
        else:
            cleaned = cleaned[:1_200]

        with self.repository.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO episodes (
                    session_id, workflow_id, route, event_type, summary,
                    normalized_summary, importance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, workflow_id, route, event_type, cleaned,
                    normalize_memory_text(cleaned),
                    max(0.0, min(float(importance), 1.0)),
                    utc_now_iso(),
                ),
            )
            connection.execute(
                """
                DELETE FROM episodes
                WHERE id NOT IN (
                    SELECT id FROM episodes ORDER BY created_at DESC LIMIT ?
                )
                """,
                (MAX_EPISODES,),
            )
        return int(cursor.lastrowid)

    def search(self, query: str, *, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        query_tokens = Counter(_tokens(query))
        normalized_query = normalize_memory_text(query)
        with self.repository.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM episodes ORDER BY created_at DESC LIMIT 500"
            ).fetchall()

        candidates: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            summary = str(row["summary"])
            summary_tokens = Counter(_tokens(summary))
            shared = sum((query_tokens & summary_tokens).values())
            lexical = shared / max(sum(query_tokens.values()), sum(summary_tokens.values()), 1)
            phrase = 0.5 if normalized_query and normalized_query in str(row["normalized_summary"]) else 0.0
            recency = 0.12 / (1 + len(candidates))
            score = lexical + phrase + float(row["importance"]) * 0.12 + recency
            if shared > 0 or phrase > 0:
                candidates.append(
                    (
                        score,
                        {
                            "id": int(row["id"]),
                            "route": str(row["route"]),
                            "event_type": str(row["event_type"]),
                            "summary": summary,
                            "workflow_id": row["workflow_id"],
                            "importance": float(row["importance"]),
                            "created_at": str(row["created_at"]),
                            "score": score,
                        },
                    )
                )
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in candidates[: max(1, min(limit, 20))]]

    def build_prompt_context(self, query: str, *, limit: int = DEFAULT_LIMIT) -> str:
        episodes = self.search(query, limit=limit)
        if not episodes:
            return ""
        lines = [
            "Relevant past actions and outcomes:",
            "These are historical records. Do not imply they are still current without checking.",
        ]
        for episode in episodes:
            lines.append(
                f"- [{episode['created_at']}, {episode['route']}] {episode['summary']}"
            )
        return "\n".join(lines)

    def list_recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.repository.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "session_id": str(row["session_id"]),
                "workflow_id": row["workflow_id"],
                "route": str(row["route"]),
                "event_type": str(row["event_type"]),
                "summary": str(row["summary"]),
                "importance": float(row["importance"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]


@lru_cache(maxsize=1)
def get_episodic_memory_service() -> EpisodicMemoryService:
    return EpisodicMemoryService()
