"""SQLite persistence for ALFRED memories.

This module owns database access only. Natural-language parsing and safety
decisions belong in memory_intent.py and memory_service.py.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from memory.memory_models import MemoryRecord


DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "alfred_memory.db"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MemoryRepository:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    normalized_content TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    importance REAL NOT NULL DEFAULT 0.5
                        CHECK (importance >= 0.0 AND importance <= 1.0),
                    source TEXT NOT NULL DEFAULT 'explicit',
                    is_pinned INTEGER NOT NULL DEFAULT 0
                        CHECK (is_pinned IN (0, 1)),
                    is_active INTEGER NOT NULL DEFAULT 1
                        CHECK (is_active IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS ux_memories_active_normalized
                ON memories(normalized_content)
                WHERE is_active = 1;

                CREATE INDEX IF NOT EXISTS ix_memories_active_category
                ON memories(is_active, category);

                CREATE INDEX IF NOT EXISTS ix_memories_updated_at
                ON memories(updated_at DESC);
                """
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=int(row["id"]),
            content=str(row["content"]),
            normalized_content=str(row["normalized_content"]),
            category=str(row["category"]),
            importance=float(row["importance"]),
            source=str(row["source"]),
            is_pinned=bool(row["is_pinned"]),
            is_active=bool(row["is_active"]),
            created_at=_parse_datetime(str(row["created_at"])),
            updated_at=_parse_datetime(str(row["updated_at"])),
        )

    def add(
        self,
        *,
        content: str,
        normalized_content: str,
        category: str,
        importance: float,
        source: str = "explicit",
        is_pinned: bool = False,
    ) -> tuple[MemoryRecord, bool]:
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM memories
                WHERE normalized_content = ? AND is_active = 1
                """,
                (normalized_content,),
            ).fetchone()
            if existing is not None:
                return self._row_to_record(existing), False

            cursor = connection.execute(
                """
                INSERT INTO memories (
                    content, normalized_content, category, importance, source,
                    is_pinned, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    content, normalized_content, category, importance, source,
                    int(is_pinned), now, now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            if row is None:
                raise RuntimeError("The memory was inserted but could not be read back.")
            return self._row_to_record(row), True

    def get(self, memory_id: int, *, include_inactive: bool = False) -> MemoryRecord | None:
        query = "SELECT * FROM memories WHERE id = ?"
        parameters: tuple[object, ...] = (memory_id,)
        if not include_inactive:
            query += " AND is_active = 1"
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return self._row_to_record(row) if row is not None else None

    def list_active(self, *, limit: int = 100) -> list[MemoryRecord]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memories
                WHERE is_active = 1
                ORDER BY is_pinned DESC, importance DESC, updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def update(
        self,
        memory_id: int,
        *,
        content: str,
        normalized_content: str,
        category: str | None = None,
        importance: float | None = None,
        is_pinned: bool | None = None,
    ) -> MemoryRecord | None:
        current = self.get(memory_id)
        if current is None:
            return None

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE memories
                SET content = ?, normalized_content = ?, category = ?,
                    importance = ?, is_pinned = ?, updated_at = ?
                WHERE id = ? AND is_active = 1
                """,
                (
                    content, normalized_content, category or current.category,
                    current.importance if importance is None else importance,
                    int(current.is_pinned if is_pinned is None else is_pinned),
                    _utc_now(), memory_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def deactivate(self, memory_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE memories
                SET is_active = 0, updated_at = ?
                WHERE id = ? AND is_active = 1
                """,
                (_utc_now(), memory_id),
            )
        return cursor.rowcount == 1

    def clear_all(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE memories
                SET is_active = 0, updated_at = ?
                WHERE is_active = 1
                """,
                (_utc_now(),),
            )
        return int(cursor.rowcount)
