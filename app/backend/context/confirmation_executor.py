"""Execute a response to ALFRED's persistent pending action."""

from __future__ import annotations

import inspect
import re
from typing import Any

from context.context_models import PendingAction
from memory.memory_service import get_memory_service


AFFIRMATIVE = {
    "yes", "y", "yep", "yeah", "confirm", "confirmed",
    "do it", "go ahead", "proceed", "send it", "delete it",
}
NEGATIVE = {
    "no", "n", "nope", "cancel", "never mind", "nevermind",
    "don't", "do not", "stop",
}


def confirmation_choice(command: str) -> bool | None:
    normalized = re.sub(r"[.!?]+$", "", command.strip().casefold())
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in AFFIRMATIVE:
        return True
    if normalized in NEGATIVE:
        return False
    return None


def _gmail_confirmation(token: str, confirmed: bool) -> dict[str, Any]:
    from gmail_tools.gmail_intent import handle_gmail_confirmation
    return handle_gmail_confirmation(token, confirmed)


def _calendar_confirmation(action: PendingAction, confirmed: bool) -> dict[str, Any]:
    from calendar_tools import calendar_intent

    # Prefer a durable confirmation API when the calendar module provides one.
    for name in (
        "handle_calendar_confirmation",
        "confirm_calendar_action",
        "execute_calendar_confirmation",
    ):
        handler = getattr(calendar_intent, name, None)
        if callable(handler):
            token = (
                action.payload.get("confirmation_token")
                or action.payload.get("token")
                or action.action_id
            )
            try:
                parameters = inspect.signature(handler).parameters
                if len(parameters) >= 2:
                    return handler(str(token), confirmed)
                return handler(confirmed)
            except (TypeError, ValueError):
                return handler(str(token), confirmed)

    # Backward-compatible fallback for the current intent layer.
    from ai.tool_executor import execute_tool_call
    return execute_tool_call(
        "calendar",
        {"command": "yes" if confirmed else "no"},
    )


def execute_pending_action(
    action: PendingAction,
    *,
    confirmed: bool,
) -> dict[str, Any]:
    if action.kind == "memory_clear":
        if not confirmed:
            return {
                "response": "Cancelled. Your saved memories are unchanged.",
                "overview": "Cancelled. Your saved memories are unchanged.",
                "type": "memory",
                "memory_action": "cancelled",
                "requires_confirmation": False,
            }
        removed = get_memory_service().clear_all()
        noun = "memory" if removed == 1 else "memories"
        response = f"Cleared {removed} saved {noun}."
        return {
            "response": response,
            "overview": response,
            "type": "memory",
            "memory_action": "cleared",
            "cleared_count": removed,
            "requires_confirmation": False,
        }

    token = str(action.payload.get("confirmation_token") or "").strip()
    if action.route == "email" and token:
        return _gmail_confirmation(token, confirmed)

    if action.route == "calendar":
        return _calendar_confirmation(action, confirmed)

    if action.route == "email":
        from ai.tool_executor import execute_tool_call
        return execute_tool_call(
            "gmail",
            {"command": "yes" if confirmed else "no"},
        )

    if not confirmed:
        return {
            "response": "Cancelled. Nothing was changed.",
            "overview": "Cancelled. Nothing was changed.",
            "type": "confirmation_cancelled",
            "requires_confirmation": False,
        }

    return {
        "response": "I could not safely reconstruct that confirmation. Nothing was changed.",
        "overview": "I could not safely reconstruct that confirmation. Nothing was changed.",
        "type": "confirmation_error",
        "requires_confirmation": False,
    }
