"""Deterministic natural-language commands for explicit persistent memory."""

from __future__ import annotations

import re
from typing import Any

from memory.memory_models import MemoryRecord
from memory.memory_service import MemoryService, MemoryValidationError, get_memory_service


REMEMBER_PATTERNS = [
    re.compile(r"^(?:please\s+)?remember\s+that\s+(.+)$", re.I | re.S),
    re.compile(r"^(?:please\s+)?remember\s+(.+)$", re.I | re.S),
    re.compile(r"^(?:please\s+)?save\s+(?:this\s+)?(?:to\s+)?memory\s*[:,-]?\s*(.+)$", re.I | re.S),
]
LIST_PATTERN = re.compile(
    r"^(?:what|show|tell)\s+(?:me\s+)?(?:do\s+you\s+)?remember(?:\s+about\s+(.+))?[?.!]*$",
    re.I | re.S,
)
LIST_ALT_PATTERN = re.compile(r"^(?:list|show)\s+(?:all\s+)?memories[?.!]*$", re.I)
FORGET_ID_PATTERN = re.compile(r"^(?:please\s+)?forget\s+(?:memory\s+)?#?(\d+)[?.!]*$", re.I)
FORGET_TEXT_PATTERN = re.compile(r"^(?:please\s+)?forget\s+(?:that\s+)?(.+)$", re.I | re.S)
UPDATE_PATTERN = re.compile(
    r"^(?:please\s+)?(?:update|change|edit)\s+memory\s+#?(\d+)\s+(?:to|as)\s+(.+)$",
    re.I | re.S,
)
CLEAR_PATTERN = re.compile(r"^(?:please\s+)?(?:clear|delete|forget)\s+all\s+memories[?.!]*$", re.I)


def is_memory_command(command: str) -> bool:
    text = command.strip()
    return bool(
        any(pattern.match(text) for pattern in REMEMBER_PATTERNS)
        or LIST_PATTERN.match(text)
        or LIST_ALT_PATTERN.match(text)
        or FORGET_ID_PATTERN.match(text)
        or FORGET_TEXT_PATTERN.match(text)
        or UPDATE_PATTERN.match(text)
        or CLEAR_PATTERN.match(text)
    )


def _memory_payload(response: str, *, action: str, memories: list[MemoryRecord] | None = None) -> dict[str, Any]:
    return {
        "response": response,
        "overview": response,
        "type": "memory",
        "memory_action": action,
        "memories": [memory.to_dict() for memory in (memories or [])],
        "requires_confirmation": False,
    }


def _format_memory_list(memories: list[MemoryRecord], heading: str) -> str:
    if not memories:
        return f"{heading} Nothing is stored yet."
    lines = [heading]
    for memory in memories:
        pin = " · pinned" if memory.is_pinned else ""
        lines.append(f"{memory.id}. {memory.content} ({memory.category}{pin})")
    return "\n".join(lines)


def handle_memory_command(
    command: str,
    service: MemoryService | None = None,
) -> dict[str, Any]:
    service = service or get_memory_service()
    text = command.strip()

    for pattern in REMEMBER_PATTERNS:
        match = pattern.match(text)
        if match:
            content = match.group(1).strip()
            try:
                memory, created = service.remember(content)
            except MemoryValidationError as exc:
                return _memory_payload(str(exc), action="rejected")
            if not created:
                return _memory_payload(
                    f"I already have that saved as memory {memory.id}.",
                    action="duplicate",
                    memories=[memory],
                )
            return _memory_payload(
                f"Remembered: {memory.content}",
                action="created",
                memories=[memory],
            )

    update_match = UPDATE_PATTERN.match(text)
    if update_match:
        memory_id = int(update_match.group(1))
        content = update_match.group(2).strip()
        try:
            memory = service.update(memory_id, content)
        except MemoryValidationError as exc:
            return _memory_payload(str(exc), action="rejected")
        if memory is None:
            return _memory_payload(
                f"I couldn't find active memory {memory_id}.",
                action="not_found",
            )
        return _memory_payload(
            f"Memory {memory.id} updated: {memory.content}",
            action="updated",
            memories=[memory],
        )

    forget_id_match = FORGET_ID_PATTERN.match(text)
    if forget_id_match:
        memory_id = int(forget_id_match.group(1))
        memory = service.get(memory_id)
        if memory is None:
            return _memory_payload(
                f"I couldn't find active memory {memory_id}.",
                action="not_found",
            )
        service.forget(memory_id)
        return _memory_payload(
            f"Forgotten: {memory.content}",
            action="deleted",
            memories=[memory],
        )

    if CLEAR_PATTERN.match(text):
        count = len(service.list_memories(limit=10_000))
        if count == 0:
            return _memory_payload(
                "There are no saved memories to clear.",
                action="not_found",
            )
        noun = "memory" if count == 1 else "memories"
        response = (
            f"This will clear all {count} saved {noun}. "
            "Confirm?"
        )
        payload = _memory_payload(
            response,
            action="confirmation_required",
        )
        payload["requires_confirmation"] = True
        payload["pending_action"] = {
            "kind": "memory_clear",
            "route": "memory",
            "count": count,
        }
        payload["confirmation"] = {
            "kind": "memory_clear",
            "count": count,
            "yes_label": "Yes",
            "no_label": "No",
        }
        return payload

    list_match = LIST_PATTERN.match(text)
    if list_match or LIST_ALT_PATTERN.match(text):
        topic = list_match.group(1).strip() if list_match and list_match.group(1) else ""
        if topic:
            candidates = service.search(topic, limit=20, minimum_score=0.08)
            memories = [candidate.memory for candidate in candidates]
            heading = f"Here is what I remember about {topic}:"
        else:
            memories = service.list_memories(limit=100)
            heading = "Here is what I remember:"
        return _memory_payload(
            _format_memory_list(memories, heading),
            action="listed",
            memories=memories,
        )

    forget_text_match = FORGET_TEXT_PATTERN.match(text)
    if forget_text_match:
        query = forget_text_match.group(1).strip().rstrip(".?!")
        candidates = service.find_for_forget(query, limit=5)
        if not candidates:
            return _memory_payload(
                f"I couldn't find a memory matching: {query}",
                action="not_found",
            )
        top = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        exact = top.memory.normalized_content == query.casefold().strip(" .,!;:")
        clearly_unique = top.score >= 0.65 and (top.score - second_score) >= 0.18
        if exact or clearly_unique:
            service.forget(top.memory.id)
            return _memory_payload(
                f"Forgotten: {top.memory.content}",
                action="deleted",
                memories=[top.memory],
            )
        memories = [candidate.memory for candidate in candidates]
        response = _format_memory_list(
            memories,
            "I found several possible matches. Use ‘forget memory <number>’:",
        )
        return _memory_payload(response, action="ambiguous", memories=memories)

    return _memory_payload(
        "I couldn't determine the memory action.",
        action="unknown",
    )
