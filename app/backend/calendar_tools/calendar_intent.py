# app/backend/calendar_tools/calendar_intent.py

from __future__ import annotations

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from .calendar_service import list_events_for_day, list_upcoming_events
from .planning_service import generate_daily_plan, generate_weekly_summary
from dateutil import parser
from .calendar_service import list_events_for_day, list_upcoming_events, create_calendar_event

import json

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

import json
import re
from datetime import datetime, timedelta, time
from dateutil import parser

CREATE_RE = re.compile(
    r"\b(add|create|schedule|book|set up)\b.*\b(event|meeting|appointment|call)\b",
    re.IGNORECASE,
)

TIME_RE = re.compile(
    r"(?:\bat\s+|@)?\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)

TITLE_RE = re.compile(
    r'\b(?:title|titled|called|named)\s+["“]?(.+?)["”]?(?=\s+(?:for|on|at|from|to|tomorrow|today|tmr|tmrw|description|location)\b|$)',
    re.IGNORECASE,
)


def _default_title(text: str) -> str:
    lowered = text.lower()

    if "meeting" in lowered:
        return "Meeting"
    if "appointment" in lowered:
        return "Appointment"
    if "call" in lowered:
        return "Call"

    return "New Event"


def _resolve_date(text: str) -> datetime.date:
    lowered = text.lower()
    today = datetime.now().date()

    if any(word in lowered for word in ["tomorrow", "tommorow", "tmrw", "tmr"]):
        return today + timedelta(days=1)

    if "today" in lowered:
        return today

    try:
        return parser.parse(text, fuzzy=True).date()
    except Exception:
        return today

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

RANGE_RE = re.compile(
    r"\bfrom\s+(.+?)\s+(?:to|until|through)\s+(.+?)(?=\s+(?:location|description)\b|$)",
    re.IGNORECASE,
)

COMPACT_RANGE_RE = re.compile(
    r"\bfrom\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)(?=\s|$)",
    re.IGNORECASE,
)


def _next_weekday(target_weekday: int, base_date: datetime.date) -> datetime.date:
    days_ahead = (target_weekday - base_date.weekday()) % 7
    return base_date + timedelta(days=days_ahead)


def _resolve_date_from_text(text: str, fallback_text: str = "") -> datetime.date:
    lowered = f"{text} {fallback_text}".lower()
    today = datetime.now().date()

    if any(word in lowered for word in ["tomorrow", "tommorow", "tmrw", "tmr"]):
        return today + timedelta(days=1)

    if "today" in lowered:
        return today

    for name, index in WEEKDAYS.items():
        if name in lowered:
            return _next_weekday(index, today)

    try:
        return parser.parse(lowered, fuzzy=True).date()
    except Exception:
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


def _parse_event_window(text: str) -> tuple[datetime, datetime, str]:
    compact_match = COMPACT_RANGE_RE.search(text)
    full_match = RANGE_RE.search(text)

    if compact_match:
        start_part = compact_match.group(1)
        end_part = compact_match.group(2)

        end_meridiem = _meridiem_from_text(end_part)
        start_date = _resolve_date_from_text(text)

        start = datetime.combine(start_date, _parse_clock(start_part, end_meridiem))
        end = datetime.combine(start_date, _parse_clock(end_part))

        if end <= start:
            end += timedelta(days=1)

        cleaned_text = text[:compact_match.start()] + text[compact_match.end():]
        return start, end, cleaned_text.strip()

    if full_match:
        start_part = full_match.group(1)
        end_part = full_match.group(2)

        start_date = _resolve_date_from_text(start_part, text)
        end_date = _resolve_date_from_text(end_part, text)

        start = datetime.combine(start_date, _parse_clock(start_part))
        end = datetime.combine(end_date, _parse_clock(end_part))

        if end <= start:
            end += timedelta(days=1)

        cleaned_text = text[:full_match.start()] + text[full_match.end():]
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

    if not has_explicit_title:
        return 'Add a title. Try: create an event title "Dentist" for tomorrow at 5:30pm'

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

    try:
        start, end, date_text = _parse_event_window(text)
    except ValueError:
        return (
            "I can create that event, but I need a time. "
            'Try: create an event for tmrw called "test 2" from 9-11pm'
        )

    location_match = re.search(r"\b(?:location)\s+(.+)$", date_text, re.IGNORECASE)
    location = None

    if location_match:
        location = location_match.group(1).strip()
        date_text = date_text[:location_match.start()].strip()

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
        "start": created.get("start", start.isoformat()),
        "end": created.get("end", end.isoformat()),
        "location": created.get("location") or location,
        "description": created.get("description") or description,
    }

    duration = end - start
    duration_hours = duration.total_seconds() / 3600

    duration_text = (
        f"{int(duration_hours)} hour{'s' if duration_hours != 1 else ''}"
        if duration_hours.is_integer()
        else f"{int(duration.total_seconds() / 60)} minutes"
    )

    return (
        f"Created event: {created['title']}\n"
        f"When: {start.strftime('%A, %B %d at %I:%M %p').replace(' 0', ' ')}\n"
        f"Ends: {end.strftime('%A, %B %d at %I:%M %p').replace(' 0', ' ')}\n"
        f"Duration: {duration_text}\n"
        f"Location: {location or 'None'}\n"
        f"__ALFRED_CALENDAR_EVENT__={json.dumps(created)}"
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

    # TOMORROW must come before upcoming/next logic
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
                f"Tomorrow's Plan\n\n"
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