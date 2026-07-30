from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from dateutil import parser

from .calendar_service import LOCAL_TZ, list_events_for_day

FOCUS_BLOCKS = [("09:00", "10:30"), ("10:45", "12:00"), ("13:30", "15:00"), ("15:30", "17:00"), ("19:00", "20:30")]


def _local_datetime(value: str) -> datetime:
    parsed = parser.parse(value)
    return parsed.replace(tzinfo=LOCAL_TZ) if parsed.tzinfo is None else parsed.astimezone(LOCAL_TZ)


def _overlaps(start: datetime, end: datetime, event_start: datetime, event_end: datetime) -> bool:
    return start < event_end and event_start < end


def generate_daily_plan(date_string: str) -> dict[str, Any]:
    target_date = parser.parse(date_string).date()
    events = list_events_for_day(target_date)
    busy: list[tuple[datetime, datetime, str]] = []

    for event in events:
        if event.get("all_day"):
            day_start = datetime.combine(target_date, time.min, tzinfo=LOCAL_TZ)
            busy.append((day_start, day_start + timedelta(days=1), event.get("title", "Untitled")))
            continue
        try:
            busy.append((_local_datetime(event["start"]), _local_datetime(event["end"]), event.get("title", "Untitled")))
        except (KeyError, ValueError, TypeError):
            continue

    free_blocks = []
    for start_text, end_text in FOCUS_BLOCKS:
        block_start = datetime.combine(target_date, parser.parse(start_text).time(), tzinfo=LOCAL_TZ)
        block_end = datetime.combine(target_date, parser.parse(end_text).time(), tzinfo=LOCAL_TZ)
        if not any(_overlaps(block_start, block_end, event_start, event_end) for event_start, event_end, _ in busy):
            free_blocks.append({"start": block_start.isoformat(), "end": block_end.isoformat()})

    recommendations = []
    if free_blocks:
        recommendations.append("Use your first open focus block for deep work.")
    else:
        recommendations.append("The day is packed. Keep the focus list short.")
    recommendations.append("Pick one major task and two smaller tasks." if len(events) >= 4 else "There is room for one larger focus task and a few lighter tasks.")

    return {
        "date": target_date.isoformat(),
        "events": events,
        "free_focus_blocks": free_blocks,
        "recommendations": recommendations,
    }


def generate_weekly_summary(start_date_string: str) -> dict[str, Any]:
    start_date = parser.parse(start_date_string).date()
    days = []
    for offset in range(7):
        day = start_date + timedelta(days=offset)
        plan = generate_daily_plan(day.isoformat())
        days.append({
            "date": day.isoformat(),
            "event_count": len(plan["events"]),
            "events": plan["events"],
            "free_focus_blocks": plan["free_focus_blocks"],
            "top_recommendation": plan["recommendations"][0],
        })
    busiest = max(days, key=lambda item: item["event_count"])
    lightest = min(days, key=lambda item: item["event_count"])
    return {
        "week_start": start_date.isoformat(),
        "days": days,
        "summary": {
            "busiest": busiest,
            "lightest": lightest,
        },
    }
