"""Data models used by ALFRED's persistent memory system."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


VALID_CATEGORIES = {
    "preference",
    "personal",
    "project",
    "person",
    "behavior",
    "general",
}


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: int
    content: str
    normalized_content: str
    category: str
    importance: float
    source: str
    is_pinned: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    memory: MemoryRecord
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.memory.to_dict(),
            "relevance_score": round(self.score, 4),
        }
