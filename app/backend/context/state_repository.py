"""SQLite persistence for ALFRED's agent state.

This database stores recent conversation, pending confirmations, resumable
workflow journals, and episodic outcome summaries. It uses the same SQLite file
as long-term memory, but separate tables.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "alfred_memory.db"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class AgentStateRepository:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_text TEXT NOT NULL,
                    assistant_text TEXT NOT NULL,
                    route TEXT NOT NULL,
                    response_type TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_turns_session_created
                ON conversation_turns(session_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS pending_actions (
                    session_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    route TEXT NOT NULL,
                    original_command TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    workflow_id TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_pending_expires
                ON pending_actions(expires_at);

                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    original_command TEXT NOT NULL,
                    route TEXT NOT NULL,
                    status TEXT NOT NULL,
                    final_response TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_workflows_session_updated
                ON workflows(session_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS ix_workflows_status_updated
                ON workflows(status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS workflow_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id)
                        ON DELETE CASCADE,
                    UNIQUE(workflow_id, fingerprint, status)
                );
                CREATE INDEX IF NOT EXISTS ix_steps_workflow_index
                ON workflow_steps(workflow_id, step_index);

                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    workflow_id TEXT,
                    route TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    normalized_summary TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 0.55,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_episodes_created
                ON episodes(created_at DESC);
                CREATE INDEX IF NOT EXISTS ix_episodes_route_created
                ON episodes(route, created_at DESC);
                """
            )

    @staticmethod
    def dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))

    @staticmethod
    def loads(value: str | None, default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
