from __future__ import annotations

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from calendar_tools.calendar_service import list_events_for_day
from gmail_tools.gmail_service import gmail_health, search_emails
from services.voice_service import voice_service

LOGGER = logging.getLogger(__name__)

TIMEZONE = "America/New_York"
LOCAL_TZ = ZoneInfo(TIMEZONE)
MAX_UNREAD_PREVIEW = 5

# Startup should remain fast. Individual providers that exceed this target are
# logged so they can be optimized without blocking the rest of ALFRED.
SLOW_SOURCE_WARNING_SECONDS = 1.5


def _now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _safe_call(
    name: str,
    function: Callable[[], Any],
) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()

    try:
        value = function()
        elapsed = time.perf_counter() - started

        if elapsed >= SLOW_SOURCE_WARNING_SECONDS:
            LOGGER.warning(
                "Startup source %s took %.2fs",
                name,
                elapsed,
            )
        else:
            LOGGER.info(
                "Startup source %s ready in %.2fs",
                name,
                elapsed,
            )

        return name, {
            "online": True,
            "data": value,
            "error": None,
            "elapsed_seconds": round(elapsed, 3),
        }
    except Exception as exc:
        elapsed = time.perf_counter() - started
        LOGGER.warning(
            "Startup briefing source %s failed after %.2fs: %s",
            name,
            elapsed,
            exc,
        )
        return name, {
            "online": False,
            "data": None,
            "error": str(exc),
            "elapsed_seconds": round(elapsed, 3),
        }


def _parse_event_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=LOCAL_TZ)

    return parsed.astimezone(LOCAL_TZ)


def _calendar_snapshot(now: datetime) -> dict[str, Any]:
    events = list_events_for_day(now.date())
    remaining: list[dict[str, Any]] = []

    for event in events:
        if event.get("all_day"):
            remaining.append(event)
            continue

        parsed = _parse_event_datetime(event.get("end") or event.get("start"))
        if parsed and parsed > now:
            remaining.append(event)

    remaining.sort(
        key=lambda event: (
            0 if event.get("all_day") else 1,
            str(event.get("start") or ""),
        )
    )

    return {
        "today_count": len(events),
        "remaining_count": len(remaining),
        "events": remaining[:5],
    }


def _gmail_snapshot() -> dict[str, Any]:
    health = gmail_health()
    if not health.get("connected"):
        raise RuntimeError(
            health.get("error") or "Gmail is not connected."
        )

    unread = search_emails(
        "in:inbox is:unread",
        max_results=MAX_UNREAD_PREVIEW,
        include_body=False,
    )

    return {
        "unread_count": len(unread),
        "unread_preview": [
            {
                "id": item.get("id"),
                "subject": item.get("subject") or "(No subject)",
                "from_name": (
                    item.get("from_name")
                    or item.get("from")
                    or "Unknown sender"
                ),
                "date": item.get("date"),
                "snippet": item.get("snippet") or "",
            }
            for item in unread
        ],
    }


def _system_snapshot() -> dict[str, Any]:
    # Weather is intentionally excluded. It is now loaded only when the user
    # explicitly asks for weather.
    return {
        "backend": {"online": True},
        "calendar": {"online": False},
        "gmail": {"online": False},
        "ollama": {"online": True},
        "voice": {"online": True},
    }


def _format_event_time(
    event: dict[str, Any],
    now: datetime,
) -> tuple[str, int | None]:
    if event.get("all_day"):
        return "all day", None

    parsed = _parse_event_datetime(event.get("start"))
    if parsed is None:
        return "later today", None

    minutes = max(
        0,
        round((parsed - now).total_seconds() / 60),
    )

    if minutes < 60:
        relative = (
            f"in {minutes} minute"
            + ("" if minutes == 1 else "s")
        )
    else:
        hours = round(minutes / 60, 1)
        relative = f"in {hours:g} hours"

    clock = parsed.strftime("%I:%M %p").lstrip("0")
    return f"{clock}, {relative}", minutes


def _build_briefing(
    snapshot: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    calendar_source = snapshot["sources"].get("calendar") or {}
    gmail_source = snapshot["sources"].get("gmail") or {}

    calendar_data = (
        calendar_source.get("data") or {}
        if calendar_source.get("online")
        else {}
    )
    gmail_data = (
        gmail_source.get("data") or {}
        if gmail_source.get("online")
        else {}
    )

    events = calendar_data.get("events") or []
    unread_count = int(gmail_data.get("unread_count") or 0)

    next_event = events[0] if events else None
    next_event_time = None
    minutes_until_event = None

    if next_event:
        next_event_time, minutes_until_event = _format_event_time(
            next_event,
            now,
        )

    if now.hour < 12:
        greeting = "Good morning"
    elif now.hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    available_systems = [
        name
        for name in ("calendar", "gmail")
        if snapshot["systems"][name]["online"]
    ]

    unavailable_systems = [
        name
        for name in ("calendar", "gmail")
        if not snapshot["systems"][name]["online"]
    ]

    if unavailable_systems:
        opening = (
            "Core systems are ready, though "
            + " and ".join(unavailable_systems)
            + (" are" if len(unavailable_systems) > 1 else " is")
            + " currently unavailable."
        )
    elif len(available_systems) == 2:
        openings = [
            "Core systems are online and behaving themselves.",
            "Calendar and Gmail are online. Everything looks steady.",
            "Primary systems are ready. Nothing appears to be on fire.",
            "Startup checks are complete. ALFRED is ready.",
        ]
        seed = hashlib.sha256(
            f"{now.date().isoformat()}:{now.hour}".encode()
        ).digest()[0]
        opening = openings[seed % len(openings)]
    else:
        opening = "ALFRED is ready."

    action = None

    if (
        next_event
        and minutes_until_event is not None
        and minutes_until_event <= 90
    ):
        title = next_event.get("title") or "your next event"
        message = (
            f"{opening} You have {title} {next_event_time}. "
            "You may want to get ahead of it."
        )
        action = {
            "label": "Prepare meeting notes",
            "command": f"Help me prepare notes for {title}",
            "kind": "command",
        }
    elif unread_count:
        noun = "email" if unread_count == 1 else "emails"
        message = (
            f"{opening} You have {unread_count} unread {noun} waiting."
        )
        action = {
            "label": "Read unread emails",
            "command": "Summarize my unread inbox",
            "kind": "command",
        }
    elif next_event:
        title = next_event.get("title") or "an event"
        message = (
            f"{opening} Your next item is {title} {next_event_time}."
        )
        action = {
            "label": "Review today",
            "command": "Show me the rest of today",
            "kind": "command",
        }
    elif calendar_source.get("online") and gmail_source.get("online"):
        message = (
            f"{opening} Your calendar is clear and your inbox is quiet. "
            "Enjoy the anomaly."
        )
    else:
        message = (
            f"{opening} You can still use all available tools normally."
        )

    return {
        "greeting": greeting,
        "message": message,
        "action": action,
    }


def build_startup_briefing() -> dict[str, Any]:
    started = time.perf_counter()
    now = _now()
    systems = _system_snapshot()
    voice_health = voice_service.health()
    systems["voice"] = {
        "online": bool(voice_health.get("available", True)),
        "ready": bool(voice_health.get("ready", False)),
        "warming": bool(voice_health.get("warming", False)),
    }

    # Calendar and Gmail are independent and should initialize concurrently.
    jobs: dict[str, Callable[[], Any]] = {
        "calendar": lambda: _calendar_snapshot(now),
        "gmail": _gmail_snapshot,
    }

    sources: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(
        max_workers=len(jobs),
        thread_name_prefix="alfred-startup",
    ) as executor:
        futures = {
            executor.submit(_safe_call, name, function): name
            for name, function in jobs.items()
        }

        for future in as_completed(futures):
            name, result = future.result()
            sources[name] = result
            systems[name]["online"] = bool(result["online"])

    snapshot = {
        "generated_at": now.isoformat(),
        "timezone": TIMEZONE,
        "systems": systems,
        "sources": sources,
    }

    # Do not call Ollama during startup. A deterministic briefing avoids model
    # loading and prompt-evaluation delay while preserving ALFRED's tone.
    generated = _build_briefing(snapshot, now)

    elapsed = time.perf_counter() - started
    LOGGER.info(
        "Startup briefing ready in %.2fs",
        elapsed,
    )

    return {
        "type": "startup_briefing",
        "generated_at": snapshot["generated_at"],
        "greeting": generated["greeting"],
        "message": generated["message"],
        "action": generated["action"],
        "systems": systems,
        "calendar": (sources.get("calendar") or {}).get("data"),
        "gmail": (sources.get("gmail") or {}).get("data"),
        "performance": {
            "total_seconds": round(elapsed, 3),
            "sources": {
                name: result.get("elapsed_seconds")
                for name, result in sources.items()
            },
        },
    }
