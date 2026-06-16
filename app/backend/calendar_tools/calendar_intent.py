# app/backend/calendar_tools/calendar_intent.py

from __future__ import annotations

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from .calendar_service import list_events_for_day, list_upcoming_events
from .planning_service import generate_daily_plan, generate_weekly_summary


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

def handle_calendar_command(command: str) -> str | None:
    text = command.lower().strip()
    today = datetime.now().date()

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