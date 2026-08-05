"""Persistent confirmation state for consequential ALFRED actions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from context.context_models import PendingAction
from context.conversation_context import ConversationContext
from context.state_repository import AgentStateRepository, parse_datetime, utc_now_iso


PENDING_TTL_HOURS = 24

_TOKEN_PATHS = (
    ("confirmation", "token"),
    ("confirmation", "confirmation_token"),
    ("gmail", "confirmation_token"),
    ("calendar", "confirmation_token"),
)


def _nested_value(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


class PendingActionStore:
    def __init__(
        self,
        repository: AgentStateRepository | None = None,
        *,
        ttl_hours: int = PENDING_TTL_HOURS,
        ttl_minutes: int | None = None,
    ) -> None:
        self.repository = repository or AgentStateRepository()
        self.ttl = (
            timedelta(minutes=max(1, ttl_minutes))
            if ttl_minutes is not None
            else timedelta(hours=max(1, ttl_hours))
        )
        self._cache: dict[str, PendingAction] = {}

    @staticmethod
    def normalize_session_id(session_id: str | None) -> str:
        return ConversationContext.normalize_session_id(session_id)

    def _row_to_action(self, row) -> PendingAction:
        return PendingAction(
            action_id=str(row["action_id"]),
            kind=str(row["kind"]),
            route=str(row["route"]),
            original_command=str(row["original_command"]),
            payload=self.repository.loads(str(row["payload_json"]), {}),
            summary=str(row["summary"]),
            workflow_id=str(row["workflow_id"]) if row["workflow_id"] else None,
            created_at=parse_datetime(str(row["created_at"])) or datetime.now(timezone.utc),
            expires_at=parse_datetime(str(row["expires_at"])),
        )

    def set(
        self,
        *,
        session_id: str | None,
        kind: str,
        route: str,
        original_command: str,
        payload: dict[str, Any] | None = None,
        summary: str = "",
        workflow_id: str | None = None,
    ) -> PendingAction:
        sid = self.normalize_session_id(session_id)
        now = datetime.now(timezone.utc)
        action = PendingAction(
            kind=kind,
            route=route,
            original_command=original_command,
            payload=dict(payload or {}),
            summary=summary,
            workflow_id=workflow_id,
            created_at=now,
            expires_at=now + self.ttl,
        )
        self._cache[sid] = action
        with self.repository.connect() as connection:
            connection.execute(
                """
                INSERT INTO pending_actions (
                    session_id, action_id, kind, route, original_command,
                    payload_json, summary, workflow_id, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    action_id = excluded.action_id,
                    kind = excluded.kind,
                    route = excluded.route,
                    original_command = excluded.original_command,
                    payload_json = excluded.payload_json,
                    summary = excluded.summary,
                    workflow_id = excluded.workflow_id,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (
                    sid, action.action_id, kind, route, original_command,
                    self.repository.dumps(action.payload), summary[:2_000],
                    workflow_id, action.created_at.isoformat(),
                    action.expires_at.isoformat() if action.expires_at else None,
                ),
            )
        return action

    def get(self, session_id: str | None) -> PendingAction | None:
        sid = self.normalize_session_id(session_id)
        cached = self._cache.get(sid)
        if cached is not None:
            if cached.expires_at and cached.expires_at <= datetime.now(timezone.utc):
                self.clear(sid)
                return None
            return cached
        with self.repository.connect() as connection:
            row = connection.execute(
                "SELECT * FROM pending_actions WHERE session_id = ?",
                (sid,),
            ).fetchone()
            if row is None:
                return None
            action = self._row_to_action(row)
            if action.expires_at and action.expires_at <= datetime.now(timezone.utc):
                connection.execute(
                    "DELETE FROM pending_actions WHERE session_id = ?",
                    (sid,),
                )
                return None
        self._cache[sid] = action
        return action

    def pop(self, session_id: str | None) -> PendingAction | None:
        action = self.get(session_id)
        if action is not None:
            self.clear(session_id)
        return action

    def clear(self, session_id: str | None) -> bool:
        sid = self.normalize_session_id(session_id)
        self._cache.pop(sid, None)
        with self.repository.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM pending_actions WHERE session_id = ?",
                (sid,),
            )
        return cursor.rowcount > 0

    def capture_from_result(
        self,
        *,
        session_id: str | None,
        original_command: str,
        route: str,
        result: dict[str, Any],
        workflow_id: str | None = None,
    ) -> PendingAction | None:
        if not bool(result.get("requires_confirmation")):
            return None

        explicit = result.get("pending_action")
        payload: dict[str, Any] = {"result_snapshot": result}
        kind = "tool_confirmation"

        if isinstance(explicit, dict):
            payload.update(explicit)
            kind = str(explicit.get("kind") or kind)
            route = str(explicit.get("route") or route)

        for path in _TOKEN_PATHS:
            token = _nested_value(result, path)
            if token:
                payload.setdefault("confirmation_token", str(token))
                break

        for key in (
            "confirmation_token", "token", "event_id", "draft_id",
            "message_id", "action", "operation", "confirm_command",
        ):
            value = result.get(key)
            if value is not None:
                payload.setdefault(key, value)

        return self.set(
            session_id=session_id,
            kind=kind,
            route=route,
            original_command=original_command,
            payload=payload,
            summary=str(result.get("response") or result.get("overview") or "")[:2_000],
            workflow_id=workflow_id,
        )

    def snapshot(self, session_id: str | None) -> dict[str, Any]:
        action = self.get(session_id)
        return {
            "pending_action": action.to_dict() if action else None,
            "ttl_hours": int(self.ttl.total_seconds() // 3600),
            "persistent": True,
        }


@lru_cache(maxsize=1)
def get_pending_action_store() -> PendingActionStore:
    return PendingActionStore()
