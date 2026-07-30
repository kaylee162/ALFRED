from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser
from dateutil.relativedelta import relativedelta

from .calendar_service import (
    LOCAL_TZ,
    TIMEZONE,
    create_calendar_event,
    list_events_between,
    list_events_for_day,
    list_upcoming_events,
)

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
CREATE_RE = re.compile(r"\b(add|create|schedule|book|set up)\b", re.I)
UPDATE_RE = re.compile(r"\b(update|edit|change|move|reschedule|rename)\b", re.I)
DELETE_RE = re.compile(r"\b(delete|remove|cancel)\b", re.I)
TIME_RE = re.compile(r"(?<![\d/])(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)
DATE_WORD_RE = re.compile(
    r"\b(today|tomorrow|tommorow|tmrw|tmr|tmw|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|sunday)\b", re.I
)


def _now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _calendar_response(
    *,
    overview: str,
    presentation: str,
    events: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "type": "calendar",
        "response": overview,
        "overview": overview,
        "calendar": {
            "presentation": presentation,
            "timezone": TIMEZONE,
            "events": events or [],
            **extra,
        },
        "requires_confirmation": presentation in {"update_options", "delete_options"},
    }


def _next_weekday(target: int, base: date) -> date:
    return base + timedelta(days=(target - base.weekday()) % 7)


def _explicit_date(text: str, base: date | None = None) -> date | None:
    base = base or _now().date()
    lowered = text.lower()
    if any(term in lowered for term in ("tomorrow", "tommorow", "tmrw", "tmr", "tmw")):
        return base + timedelta(days=1)
    if "today" in lowered:
        return base
    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", lowered):
            return _next_weekday(weekday, base)

    slash = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
    if slash:
        year = int(slash.group(3) or base.year)
        if year < 100:
            year += 2000
        return date(year, int(slash.group(1)), int(slash.group(2)))

    month_names = "|".join(MONTHS)
    match = re.search(
        rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b",
        text, re.I,
    )
    if match:
        return date(int(match.group(3) or base.year), MONTHS[match.group(1).lower()], int(match.group(2)))
    reverse = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})(?:,?\s+(\d{{4}}))?\b",
        text, re.I,
    )
    if reverse:
        return date(int(reverse.group(3) or base.year), MONTHS[reverse.group(2).lower()], int(reverse.group(1)))
    return None


def _clock_matches(text: str) -> list[re.Match[str]]:
    matches = []
    for match in TIME_RE.finditer(text):
        before = text[max(0, match.start() - 5):match.start()].lower()
        hour = int(match.group(1))
        # Avoid treating bare date numbers as times unless introduced by at/@ or am/pm/colon.
        if not match.group(2) and not match.group(3) and not re.search(r"(?:at\s*|@\s*)$", before):
            continue
        if hour <= 24:
            matches.append(match)
    return matches


def _parse_clock(match: re.Match[str], inherited_meridiem: str | None = None) -> time:
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or inherited_meridiem or "").lower()
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    elif not meridiem and 1 <= hour <= 7:
        hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Invalid time")
    return time(hour, minute)


def _extract_times(text: str) -> tuple[time | None, time | None]:
    matches = _clock_matches(text)
    if not matches:
        return None, None
    if len(matches) == 1:
        return _parse_clock(matches[0]), None
    inherited = matches[1].group(3)
    return _parse_clock(matches[0], inherited), _parse_clock(matches[1])


def _extract_title(text: str, action: str) -> str | None:
    explicit = re.search(r'\b(?:title|titled|called|named)\s+["“]?(.+?)["”]?(?=\s+(?:on|at|from|to|location|description)\b|$)', text, re.I)
    if explicit:
        return explicit.group(1).strip(' "“”')
    cleaned = re.sub(r"^\s*(?:please\s+)?(?:can you\s+)?", "", text, flags=re.I)
    cleaned = re.sub(rf"^.*?\b{action}\b", "", cleaned, count=1, flags=re.I)
    cleaned = re.sub(r"^\s*(?:an?\s+)?(?:calendar\s+)?(?:event|meeting|appointment|call)?\s*", "", cleaned, flags=re.I)
    split = re.split(
        r"\b(?:on|for|at|from|today|tomorrow|tommorow|tmrw|tmr|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
        cleaned, maxsplit=1, flags=re.I,
    )[0].strip(" ,.-")
    return split or None


def _extract_metadata(text: str) -> tuple[str | None, str | None]:
    location = None
    description = None
    location_match = re.search(r"\blocation\s+(.+?)(?=\s+description\b|$)", text, re.I)
    description_match = re.search(r"\bdescription\s+(.+)$", text, re.I)
    if location_match:
        location = location_match.group(1).strip()
    if description_match:
        description = description_match.group(1).strip()
    return location, description


def _create(command: str) -> dict[str, Any]:
    title = _extract_title(command, r"(?:add|create|schedule|book|set up)")
    target_date = _explicit_date(command)
    start_clock, end_clock = _extract_times(command)
    location, description = _extract_metadata(command)

    # Explicit all-day wording is the only path that creates an all-day event.
    all_day = bool(re.search(r"\ball[- ]day\b", command, re.I))
    missing: list[str] = []
    if not title:
        missing.append("title")
    if not target_date:
        missing.append("date")
    if not all_day and not start_clock:
        missing.append("time")

    draft = {
        "title": title or "",
        "date": target_date.isoformat() if target_date else "",
        "start_time": start_clock.strftime("%H:%M") if start_clock else "",
        "end_time": end_clock.strftime("%H:%M") if end_clock else "",
        "all_day": all_day,
        "location": location,
        "description": description,
    }
    if missing:
        labels = ", ".join(missing)
        return _calendar_response(
            overview=f"I need the {labels} before I can create that event.",
            presentation="missing_fields",
            missing_fields=missing,
            draft=draft,
        )

    if all_day:
        created = create_calendar_event(
            title=title or "Untitled", start_date=target_date.isoformat(),
            end_date=(target_date + timedelta(days=1)).isoformat(), all_day=True,
            location=location, description=description,
        )
    else:
        start = datetime.combine(target_date, start_clock, tzinfo=LOCAL_TZ)
        end = datetime.combine(target_date, end_clock, tzinfo=LOCAL_TZ) if end_clock else start + timedelta(hours=1)
        if end <= start:
            end += timedelta(days=1)
        created = create_calendar_event(
            title=title or "Untitled", start_time=start.isoformat(), end_time=end.isoformat(),
            location=location, description=description,
        )
    return _calendar_response(
        overview=f"Created event: {created['title']}",
        presentation="created",
        events=[created],
    )


def _strip_selector_noise(text: str) -> str | None:
    cleaned = re.sub(r"\b(update|edit|change|move|reschedule|rename|delete|remove|cancel)\b", " ", text, flags=re.I)
    cleaned = re.sub(r"\b(my|the|an?|calendar|event|meeting|appointment|call|called|named|titled|title|on|for|at|from)\b", " ", cleaned, flags=re.I)
    cleaned = DATE_WORD_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", cleaned)
    for match in reversed(_clock_matches(cleaned)):
        cleaned = cleaned[:match.start()] + " " + cleaned[match.end():]
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!?\"")
    return cleaned.lower() or None


def _event_datetime(event: dict[str, Any], key: str = "start") -> datetime | None:
    value = event.get(key)
    if not value:
        return None
    try:
        parsed = parser.parse(value)
        return parsed.replace(tzinfo=LOCAL_TZ) if parsed.tzinfo is None else parsed.astimezone(LOCAL_TZ)
    except Exception:
        return None


def _score_title(title: str, query: str | None) -> int:
    if not query:
        return 1
    normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    normalized_query = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    if normalized_title == normalized_query:
        return 100
    if normalized_title.startswith(normalized_query):
        return 90
    if normalized_query in normalized_title:
        return 80
    overlap = len(set(normalized_title.split()) & set(normalized_query.split()))
    return 40 + overlap if overlap else 0


def _find_candidates(selector: str) -> list[dict[str, Any]]:
    target_date = _explicit_date(selector)
    requested_time, _ = _extract_times(selector)
    query = _strip_selector_noise(selector)
    events = list_events_for_day(target_date) if target_date else list_upcoming_events(days=90, max_results=250)
    scored: list[tuple[int, datetime, dict[str, Any]]] = []
    for event in events:
        start = _event_datetime(event)
        if not start or not event.get("id"):
            continue
        if requested_time and (start.hour, start.minute) != (requested_time.hour, requested_time.minute):
            continue
        score = _score_title(event.get("title", ""), query)
        if score:
            scored.append((score, start, event))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[:12]]


def _split_update(command: str) -> tuple[str, str]:
    parts = re.split(r"\s+\bto\b\s+", command.strip(), maxsplit=1, flags=re.I)
    return (parts[0], parts[1]) if len(parts) == 2 else (command, "")


def _preview_update(
    event: dict[str, Any],
    change: str,
    *,
    rename_mode: bool = False,
) -> dict[str, Any]:
    preview = dict(event)
    preview["original"] = dict(event)
    preview["original_title"] = event.get("title")
    preview["original_start"] = event.get("start")
    preview["original_end"] = event.get("end")
    current_start = _event_datetime(event)
    current_end = _event_datetime(event, "end")
    if not current_start:
        return preview
    duration = current_end - current_start if current_end and current_end > current_start else timedelta(hours=1)
    new_date = _explicit_date(change, current_start.date()) if change else None
    new_time, new_end_time = _extract_times(change)
    start = datetime.combine(new_date or current_start.date(), new_time or current_start.timetz().replace(tzinfo=None), tzinfo=LOCAL_TZ)
    end = datetime.combine(start.date(), new_end_time, tzinfo=LOCAL_TZ) if new_end_time else start + duration
    if end <= start:
        end += timedelta(days=1)
    rename = re.match(r"\s*(?:title|titled|called|named)\s+(.+)$", change, re.I)
    renamed_title = None
    if rename:
        renamed_title = rename.group(1).strip(' "“”')
    elif rename_mode and change.strip():
        # "rename Dentist to Dental Appointment" should use everything after
        # "to" as the new title; the user should not have to type "named".
        renamed_title = change.strip().strip(' "“”')

    preview.update({
        "title": renamed_title or event.get("title"),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "all_day": False,
    })
    return preview


def _update(command: str) -> dict[str, Any]:
    selector, change = _split_update(command)
    matches = _find_candidates(selector)
    if not matches:
        return _calendar_response(
            overview="I couldn't find a matching event. No event was changed.",
            presentation="message",
        )
    rename_mode = bool(re.search(r"\brename\b", command, re.I))
    previews = [
        _preview_update(event, change, rename_mode=rename_mode)
        for event in matches
    ]
    overview = "I found one matching event. Review the proposed change before saving." if len(previews) == 1 else f"I found {len(previews)} possible events. Choose the correct one."
    return _calendar_response(
        overview=overview,
        presentation="update_options",
        events=previews,
        action="update",
    )


def _delete(command: str) -> dict[str, Any]:
    matches = _find_candidates(command)
    if not matches:
        return _calendar_response(
            overview="I couldn't find a matching event. No event was deleted.",
            presentation="message",
        )
    overview = "I found one matching event. Confirm deletion before continuing." if len(matches) == 1 else f"I found {len(matches)} possible events. Choose the one to delete."
    return _calendar_response(
        overview=overview,
        presentation="delete_options",
        events=matches,
        action="delete",
    )


def _daily(target: date, label: str, *, remaining_only: bool = False) -> dict[str, Any]:
    events = list_events_for_day(target)
    if remaining_only:
        now = _now()
        events = [event for event in events if event.get("all_day") or (_event_datetime(event) and _event_datetime(event) >= now)]
    overview = f"Absolutely, here’s your calendar for {label}."
    if not events:
        overview += " Looks clear, you have no events."
    else:
        titles = ", ".join(event.get("title", "Untitled") for event in events)
        overview += f" You have {len(events)} event{'s' if len(events) != 1 else ''}: {titles}."
    return _calendar_response(
        overview=overview,
        presentation="day",
        events=events,
        label=label,
        date=target.isoformat(),
    )


def _week(today: date) -> dict[str, Any]:
    start = today - timedelta(days=(today.weekday() + 1) % 7)
    days = []
    all_events: list[dict[str, Any]] = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        events = list_events_for_day(day)
        all_events.extend(events)
        days.append({"date": day.isoformat(), "events": events, "event_count": len(events)})
    busiest = max(days, key=lambda item: item["event_count"])
    lightest = min(days, key=lambda item: item["event_count"])
    overview = (
        "Absolutely, here’s what your week looks like. "
        f"Busiest day: {busiest['date']} with {busiest['event_count']} events. "
        f"Lightest day: {lightest['date']} with {lightest['event_count']} events."
    )
    return _calendar_response(
        overview=overview,
        presentation="week",
        events=all_events,
        week_start=start.isoformat(),
        days=days,
        summary={"busiest": busiest, "lightest": lightest},
    )


def handle_calendar_command(command: str) -> dict[str, Any] | None:
    text = command.strip()
    lowered = text.lower()
    if DELETE_RE.search(text):
        return _delete(text)
    if UPDATE_RE.search(text):
        return _update(text)
    if CREATE_RE.search(text):
        return _create(text)

    calendar_terms = ("calendar", "schedule", "event", "meeting", "today", "tomorrow", "week", "month", "upcoming", "what's left", "whats left", "rest of today")
    if not any(term in lowered for term in calendar_terms):
        return None

    today = _now().date()
    explicit = _explicit_date(text)
    if explicit and not any(term in lowered for term in ("week", "month")):
        label = "today" if explicit == today else "tomorrow" if explicit == today + timedelta(days=1) else explicit.strftime("%A, %B %d").replace(" 0", " ")
        return _daily(explicit, label, remaining_only=("left" in lowered or "rest of today" in lowered))
    if "week" in lowered:
        return _week(today)
    if "month" in lowered:
        start = today.replace(day=1)
        end = start + relativedelta(months=1)
        events = list_events_between(datetime.combine(start, time.min, tzinfo=LOCAL_TZ), datetime.combine(end, time.min, tzinfo=LOCAL_TZ))
        return _calendar_response(
            overview=f"Absolutely, here’s your calendar for this month. You have {len(events)} events.",
            presentation="list", events=events, label="this month",
        )
    if "upcoming" in lowered or "next" in lowered:
        events = list_upcoming_events(days=7, max_results=20)
        return _calendar_response(
            overview=f"Absolutely, here are your upcoming events. I found {len(events)}.",
            presentation="list", events=events, label="next 7 days",
        )
    return _daily(today, "today", remaining_only=("left" in lowered or "rest of today" in lowered))
