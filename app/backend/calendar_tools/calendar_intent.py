from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, time

from dateutil import parser
from dateutil.relativedelta import relativedelta

from .calendar_service import (
    list_events_for_day,
    list_upcoming_events,
    create_calendar_event,
)
from .planning_service import generate_daily_plan, generate_weekly_summary


WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

CREATE_RE = re.compile(
    r"\b(add|create|schedule|book|set up)\b.*\b(event|meeting|appointment|call)\b",
    re.IGNORECASE,
)

TIME_RE = re.compile(
    r"(?<![/\d])(?:\bat\s+|@)?\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b(?!/\d)",
    re.IGNORECASE,
)

DATE_RE = re.compile(
    r"\b("
    r"today|tomorrow|tommorow|tmrw|tmr|tmw|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"\d{1,2}(?:st|nd|rd|th)?|"
    r"\d{1,2}/\d{1,2}(?:/\d{2,4})?"
    r")\b",
    re.IGNORECASE,
)

TITLE_RE = re.compile(
    r'\b(?:title|titled|called|named)\s+["“]?(.+?)["”]?(?=\s+(?:for|on|at|from|to|tomorrow|today|tmr|tmrw|description|location)\b|$)',
    re.IGNORECASE,
)

RANGE_RE = re.compile(
    r"\b(?:from\s+)?(.+?)\s+(?:to|until|through)\s+(.+?)(?=\s+(?:location|description)\b|$)",
    re.IGNORECASE,
)

COMPACT_RANGE_RE = re.compile(
    r"\bfrom\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)(?=\s|$)",
    re.IGNORECASE,
)


def _format_event(event: dict) -> str:
    title = event.get("title", "Untitled")
    start = event.get("start")

    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        time_text = start_dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        time_text = "All day"

    location = event.get("location")
    if location:
        return f"• {time_text} — {title} at {location}"

    return f"• {time_text} — {title}"


def _format_events(date_label: str, events: list[dict]) -> str:
    if not events:
        if date_label == "tomorrow":
            return "No events tomorrow."
        if date_label == "today":
            return "No events today."
        return f"No events for {date_label}."

    event_lines = "\n".join(_format_event(event) for event in events)
    return f"Here’s your calendar for {date_label}:\n{event_lines}"


def _start_of_week(date):
    days_since_sunday = (date.weekday() + 1) % 7
    return date - timedelta(days=days_since_sunday)


def _default_title(text: str) -> str:
    lowered = text.lower()

    if "meeting" in lowered:
        return "Meeting"
    if "appointment" in lowered:
        return "Appointment"
    if "call" in lowered:
        return "Call"

    return "New Event"


def _has_date(text: str) -> bool:
    return bool(DATE_RE.search(text))


def _has_time(text: str) -> bool:
    return bool(TIME_RE.search(text))


def _next_weekday(target_weekday: int, base_date: datetime.date) -> datetime.date:
    days_ahead = (target_weekday - base_date.weekday()) % 7
    return base_date + timedelta(days=days_ahead)

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _clean_date_text(text: str) -> str:
    return re.sub(
        r"\b(for|on|at|from|to|until|through|called|named|titled|title)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    ).strip()


def _parse_explicit_date(text: str) -> datetime.date | None:
    today = datetime.now().date()
    cleaned = _clean_date_text(text.lower())

    slash_match = re.search(
        r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b",
        cleaned,
    )
    if slash_match:
        month = int(slash_match.group(1))
        day = int(slash_match.group(2))
        year = int(slash_match.group(3)) if slash_match.group(3) else today.year

        if year < 100:
            year += 2000

        return datetime(year, month, day).date()

    month_names = "|".join(MONTHS.keys())

    month_day_match = re.search(
        rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b",
        cleaned,
        re.IGNORECASE,
    )
    if month_day_match:
        month = MONTHS[month_day_match.group(1).lower()]
        day = int(month_day_match.group(2))
        year = int(month_day_match.group(3)) if month_day_match.group(3) else today.year

        return datetime(year, month, day).date()

    day_month_match = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})(?:,?\s+(\d{{4}}))?\b",
        cleaned,
        re.IGNORECASE,
    )
    if day_month_match:
        day = int(day_month_match.group(1))
        month = MONTHS[day_month_match.group(2).lower()]
        year = int(day_month_match.group(3)) if day_month_match.group(3) else today.year

        return datetime(year, month, day).date()

    day_only_match = re.search(
        r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\b",
        cleaned,
        re.IGNORECASE,
    )
    if day_only_match:
        day = int(day_only_match.group(1))
        return datetime(today.year, today.month, day).date()

    return None

def _resolve_date_from_text(
    text: str,
    fallback_text: str = "",
    *,
    fallback_date: datetime.date | None = None,
) -> datetime.date:
    today = datetime.now().date()
    lowered = text.lower()

    if any(word in lowered for word in ["tomorrow", "tommorow", "tmrw", "tmr", "tmw"]):
        return today + timedelta(days=1)

    if "today" in lowered:
        return today

    explicit_date = _parse_explicit_date(text)
    if explicit_date:
        return explicit_date

    for name, index in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", lowered):
            return _next_weekday(index, today)

    if fallback_date:
        return fallback_date

    if fallback_text:
        return _resolve_date_from_text(fallback_text)

    return today

def _parse_clock(text: str, inherited_meridiem: str | None = None) -> time:
    match = TIME_RE.search(text)

    if not match:
        raise ValueError("Missing time")

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)

    if not meridiem and inherited_meridiem:
        meridiem = inherited_meridiem

    if meridiem:
        meridiem = meridiem.lower()

        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    elif 1 <= hour <= 7:
        hour += 12

    return time(hour=hour, minute=minute)


def _meridiem_from_text(text: str) -> str | None:
    match = TIME_RE.search(text)

    if not match:
        return None

    return match.group(3).lower() if match.group(3) else None


def _pending_event_response(missing_fields: list[str], draft: dict) -> str:
    readable = {
        "title": "title",
        "date": "date",
        "time": "time",
    }

    labels = [readable[field] for field in missing_fields]

    if len(labels) == 1:
        message = f"Add a {labels[0]}."
    elif len(labels) == 2:
        message = f"Add a {labels[0]} and {labels[1]}."
    else:
        message = f"Add a {', '.join(labels[:-1])}, and {labels[-1]}."

    return (
        f"{message}\n"
        f"__ALFRED_PENDING_EVENT__={json.dumps({
            'missing_fields': missing_fields,
            'draft': draft,
        })}"
    )


def _extract_created_datetime(created: dict, key: str, fallback: datetime) -> str:
    value = created.get(key)

    if isinstance(value, dict):
        return value.get("dateTime") or value.get("date") or fallback.isoformat()

    if isinstance(value, str):
        return value

    return fallback.isoformat()


def _strip_date_prefix(text: str) -> str:
    return re.sub(r"^\s*(for|on)\s+", "", text.strip(), flags=re.IGNORECASE)


def _part_has_time(text: str) -> bool:
    return bool(TIME_RE.search(text))


def _parse_event_window(text: str) -> tuple[datetime, datetime, str]:
    compact_match = COMPACT_RANGE_RE.search(text)
    range_match = RANGE_RE.search(text)

    if compact_match:
        start_part = compact_match.group(1)
        end_part = compact_match.group(2)

        date_part = text[:compact_match.start()] + text[compact_match.end():]
        start_date = _resolve_date_from_text(date_part)

        end_meridiem = _meridiem_from_text(end_part)

        start = datetime.combine(start_date, _parse_clock(start_part, end_meridiem))
        end = datetime.combine(start_date, _parse_clock(end_part))

        if end <= start:
            end += timedelta(days=1)

        cleaned_text = text[:compact_match.start()] + text[compact_match.end():]
        return start, end, cleaned_text.strip()

    if range_match:
        start_part = _strip_date_prefix(range_match.group(1))
        end_part = _strip_date_prefix(range_match.group(2))

        start_date = _resolve_date_from_text(start_part, text)
        end_date = _resolve_date_from_text(end_part, fallback_date=start_date)

        start_has_time = _part_has_time(start_part)
        end_has_time = _part_has_time(end_part)

        if start_has_time:
            end_meridiem = _meridiem_from_text(end_part)
            start_time = _parse_clock(start_part, end_meridiem)
        else:
            start_time = time(0, 0)

        if end_has_time:
            end_time = _parse_clock(end_part)
        else:
            end_time = time(23, 59)

        start = datetime.combine(start_date, start_time)
        end = datetime.combine(end_date, end_time)

        if end <= start:
            end += timedelta(days=1)

        cleaned_text = text[:range_match.start()] + text[range_match.end():]
        return start, end, cleaned_text.strip()

    time_match = TIME_RE.search(text)

    if not time_match:
        raise ValueError("Missing time")

    target_date = _resolve_date_from_text(text)
    start = datetime.combine(target_date, _parse_clock(text))
    end = start + timedelta(hours=1)

    cleaned_text = text[:time_match.start()] + text[time_match.end():]
    return start, end, cleaned_text.strip()

def _try_create_event(command: str) -> str | None:
    original = command.strip()
    text = re.sub(r"^\s*alfred[, ]*", "", original, flags=re.IGNORECASE)

    if not CREATE_RE.search(text):
        return None

    title = _default_title(text)
    has_explicit_title = False

    title_match = TITLE_RE.search(text)
    if title_match:
        title = title_match.group(1).strip().strip('"“”').title()
        has_explicit_title = True
        text = text[:title_match.start()] + text[title_match.end():]

    text = re.sub(
        r"^\s*(please\s+)?(can you\s+)?(add|create|schedule|book|set up)\s+(an?\s+)?(calendar\s+)?(event|meeting|appointment|call)?",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    description = None
    description_match = re.search(r"\bdescription\s+(.+)$", text, re.IGNORECASE)
    if description_match:
        description = description_match.group(1).strip()
        text = text[:description_match.start()].strip()

    location = None
    location_match = re.search(r"\blocation\s+(.+)$", text, re.IGNORECASE)
    if location_match:
        location = location_match.group(1).strip()
        text = text[:location_match.start()].strip()

    missing_fields = []

    if not has_explicit_title:
        missing_fields.append("title")

    if not _has_time(text):
        missing_fields.append("time")

    if missing_fields:
        draft = {
            "title": title if has_explicit_title else "",
            "date": datetime.now().date().isoformat(),
            "end_date": "",
            "start_time": "",
            "end_time": "",
            "location": location,
            "description": description,
        }

        try:
            start, end, _ = _parse_event_window(text)
            draft["date"] = start.date().isoformat()
            draft["end_date"] = end.date().isoformat()
            draft["start_time"] = start.strftime("%H:%M")
            draft["end_time"] = end.strftime("%H:%M")
        except ValueError:
            try:
                target_date = _resolve_date_from_text(text)
                draft["date"] = target_date.isoformat()
            except Exception:
                pass

        return _pending_event_response(missing_fields, draft)

    try:
        start, end, _ = _parse_event_window(text)
    except ValueError:
        draft = {
            "title": title if has_explicit_title else "",
            "date": "",
            "end_date": "",
            "start_time": "",
            "end_time": "",
            "location": location,
            "description": description,
        }

        return _pending_event_response(["date", "time"], draft)

    created = create_calendar_event(
        title=title,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        location=location,
        description=description,
    )

    event_payload = {
        "id": created.get("id"),
        "title": created.get("title", title),
        "start": _extract_created_datetime(created, "start", start),
        "end": _extract_created_datetime(created, "end", end),
        "location": location,
        "description": description,
    }

    duration = end - start
    total_minutes = int(duration.total_seconds() / 60)

    if total_minutes % 60 == 0:
        hours = total_minutes // 60
        duration_text = f"{hours} hour{'s' if hours != 1 else ''}"
    else:
        duration_text = f"{total_minutes} minutes"

    return (
        f"Created event: {title}\n"
        f"When: {start.strftime('%A, %B %d at %I:%M %p').replace(' 0', ' ')}\n"
        f"Ends: {end.strftime('%A, %B %d at %I:%M %p').replace(' 0', ' ')}\n"
        f"Duration: {duration_text}\n"
        f"Location: {location or 'None'}\n"
        f"__ALFRED_CALENDAR_EVENT__={json.dumps(event_payload)}"
    )


def handle_calendar_command(command: str) -> str | None:
    text = command.lower().strip()
    today = datetime.now().date()

    create_response = _try_create_event(command)
    if create_response:
        return create_response

    is_calendar_request = any(
        word in text
        for word in [
            "calendar",
            "schedule",
            "event",
            "events",
            "meeting",
            "meetings",
            "plan",
            "today",
            "tomorrow",
            "tommorow",
            "tmrw",
            "tmr",
            "week",
            "month",
            "what's left",
            "whats left",
        ]
    )

    if not is_calendar_request:
        return None

    if "tomorrow" in text or "tommorow" in text or "tmrw" in text or "tmr" in text:
        target = today + timedelta(days=1)

        if "plan" in text:
            plan = generate_daily_plan(target.isoformat())
            recs = "\n".join(f"• {item}" for item in plan["recommendations"])

            blocks = "\n".join(
                f"• {block['start']} - {block['end']}"
                for block in plan["free_focus_blocks"]
            ) or "No clean focus blocks found."

            return (
                "Tomorrow's Plan\n\n"
                f"Recommendations\n{recs}\n\n"
                f"Open Focus Blocks\n{blocks}"
            )

        events = list_events_for_day(target.isoformat())
        return _format_events("tomorrow", events)

    if "today" in text or "what's left" in text or "whats left" in text:
        events = list_events_for_day(today.isoformat())

        if "left" in text:
            now = datetime.now()
            remaining = []

            for event in events:
                try:
                    start = datetime.fromisoformat(
                        event["start"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)

                    if start >= now:
                        remaining.append(event)
                except Exception:
                    remaining.append(event)

            return _format_events("the rest of today", remaining)

        return _format_events("today", events)

    if "week" in text:
        start = _start_of_week(today)
        summary = generate_weekly_summary(start.isoformat())

        week_blocks = []

        for day in summary["days"]:
            event_count = day["event_count"]
            week_blocks.append(
                f"• {day['date']} — {event_count} event{'s' if event_count != 1 else ''}"
            )

            if event_count == 0:
                week_blocks.append("  - No events")
            else:
                for event in day["events"]:
                    week_blocks.append(f"  - {_format_event(event).replace('• ', '')}")

        week_lines = "\n".join(week_blocks)

        filtered_summary = [
            item for item in summary["summary"]
            if not item.startswith("Use lighter days")
        ]

        summary_lines = "\n".join(f"• {item}" for item in filtered_summary)

        return (
            "Weekly Calendar Overview\n\n"
            "This Week\n"
            f"{week_lines}\n\n"
            "Summary\n"
            f"{summary_lines}"
        )

    if "month" in text:
        start = today.replace(day=1)
        next_month = start + relativedelta(months=1)
        days = (next_month - today).days

        events = list_upcoming_events(days=days, max_results=50)
        return _format_events("this month", events)

    if "upcoming" in text or "next" in text:
        events = list_upcoming_events(days=7, max_results=10)
        return _format_events("the next 7 days", events)

    return None