"""Models for persistent ALFRED conversation and workflow context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ConversationTurn:
    user_text: str
    assistant_text: str
    route: str
    response_type: str
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
            "route": self.route,
            "response_type": self.response_type,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class PendingAction:
    kind: str
    route: str
    original_command: str
    payload: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    workflow_id: str | None = None
    action_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "kind": self.kind,
            "route": self.route,
            "original_command": self.original_command,
            "payload": dict(self.payload),
            "summary": self.summary,
            "workflow_id": self.workflow_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass(slots=True)
class WorkflowRecord:
    workflow_id: str
    session_id: str
    original_command: str
    route: str
    status: str
    final_response: str
    error: str
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "original_command": self.original_command,
            "route": self.route,
            "status": self.status,
            "final_response": self.final_response,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
