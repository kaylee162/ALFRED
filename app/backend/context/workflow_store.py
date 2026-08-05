"""Durable workflow journal and resume support for ALFRED."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from uuid import uuid4

from context.context_models import WorkflowRecord
from context.state_repository import AgentStateRepository, parse_datetime, utc_now_iso


RESUMABLE_STATUSES = {"active", "waiting_confirmation", "failed", "interrupted"}


def tool_fingerprint(tool_name: str, arguments: dict[str, Any]) -> str:
    payload = f"{tool_name}:{AgentStateRepository.dumps(arguments)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WorkflowStore:
    def __init__(self, repository: AgentStateRepository | None = None) -> None:
        self.repository = repository or AgentStateRepository()

    @staticmethod
    def _row_to_workflow(row) -> WorkflowRecord:
        return WorkflowRecord(
            workflow_id=str(row["workflow_id"]),
            session_id=str(row["session_id"]),
            original_command=str(row["original_command"]),
            route=str(row["route"]),
            status=str(row["status"]),
            final_response=str(row["final_response"]),
            error=str(row["error"]),
            created_at=parse_datetime(str(row["created_at"])) or datetime.now(timezone.utc),
            updated_at=parse_datetime(str(row["updated_at"])) or datetime.now(timezone.utc),
        )

    def start(
        self,
        *,
        session_id: str,
        original_command: str,
        route: str = "unknown",
        workflow_id: str | None = None,
    ) -> WorkflowRecord:
        workflow_id = workflow_id or uuid4().hex
        now = utc_now_iso()
        with self.repository.connect() as connection:
            connection.execute(
                """
                INSERT INTO workflows (
                    workflow_id, session_id, original_command, route, status,
                    final_response, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'active', '', '', ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    status = 'active', updated_at = excluded.updated_at
                """,
                (workflow_id, session_id, original_command, route, now, now),
            )
            row = connection.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return self._row_to_workflow(row)

    def update_status(
        self,
        workflow_id: str,
        status: str,
        *,
        route: str | None = None,
        final_response: str = "",
        error: str = "",
    ) -> None:
        with self.repository.connect() as connection:
            connection.execute(
                """
                UPDATE workflows
                SET status = ?,
                    route = COALESCE(?, route),
                    final_response = ?,
                    error = ?,
                    updated_at = ?
                WHERE workflow_id = ?
                """,
                (
                    status, route, final_response[:8_000], error[:4_000],
                    utc_now_iso(), workflow_id,
                ),
            )

    def get(self, workflow_id: str) -> WorkflowRecord | None:
        with self.repository.connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return self._row_to_workflow(row) if row else None

    def latest_resumable(self, session_id: str) -> WorkflowRecord | None:
        placeholders = ",".join("?" for _ in RESUMABLE_STATUSES)
        with self.repository.connect() as connection:
            row = connection.execute(
                f"""
                SELECT * FROM workflows
                WHERE session_id = ? AND status IN ({placeholders})
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (session_id, *sorted(RESUMABLE_STATUSES)),
            ).fetchone()
        return self._row_to_workflow(row) if row else None

    def record_step(
        self,
        *,
        workflow_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
        status: str = "completed",
    ) -> None:
        fingerprint = tool_fingerprint(tool_name, arguments)
        with self.repository.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(step_index), 0) AS value FROM workflow_steps WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            step_index = int(row["value"]) + 1
            connection.execute(
                """
                INSERT OR REPLACE INTO workflow_steps (
                    workflow_id, step_index, tool_name, arguments_json,
                    fingerprint, result_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id, step_index, tool_name,
                    self.repository.dumps(arguments), fingerprint,
                    self.repository.dumps(result), status, utc_now_iso(),
                ),
            )

    def completed_result(
        self,
        workflow_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any | None:
        fingerprint = tool_fingerprint(tool_name, arguments)
        with self.repository.connect() as connection:
            row = connection.execute(
                """
                SELECT result_json FROM workflow_steps
                WHERE workflow_id = ? AND fingerprint = ? AND status = 'completed'
                ORDER BY id DESC LIMIT 1
                """,
                (workflow_id, fingerprint),
            ).fetchone()
        return self.repository.loads(str(row["result_json"]), None) if row else None

    def steps(self, workflow_id: str) -> list[dict[str, Any]]:
        with self.repository.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM workflow_steps
                WHERE workflow_id = ?
                ORDER BY step_index ASC
                """,
                (workflow_id,),
            ).fetchall()
        return [
            {
                "step_index": int(row["step_index"]),
                "tool_name": str(row["tool_name"]),
                "arguments": self.repository.loads(str(row["arguments_json"]), {}),
                "result": self.repository.loads(str(row["result_json"]), {}),
                "status": str(row["status"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def list_recent(self, session_id: str, *, limit: int = 20) -> list[WorkflowRecord]:
        with self.repository.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM workflows
                WHERE session_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (session_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._row_to_workflow(row) for row in rows]


@lru_cache(maxsize=1)
def get_workflow_store() -> WorkflowStore:
    return WorkflowStore()
