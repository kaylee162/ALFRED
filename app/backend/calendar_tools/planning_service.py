from __future__ import annotations

from datetime import datetime, timedelta
from dateutil import parser

from .calendar_service import list_events_for_day


FOCUS_BLOCKS = [
    ("09:00", "10:30"),
    ("10:45", "12:00"),
    ("13:30", "15:00"),
    ("15:30", "17:00"),
    ("19:00", "20:30"),
]


def _time_overlaps(block_start, block_end, event_start, event_end) -> bool:
    return block_start < event_end and event_start < block_end


def generate_daily_plan(date_string: str) -> dict:
    events = list_events_for_day(date_string)

    target_date = parser.parse(date_string).date()
    busy_events = []

    for event in events:
        try:
            start = parser.parse(event["start"])
            end = parser.parse(event["end"])
            busy_events.append((start, end, event["title"]))
        except Exception:
            continue

    free_focus_blocks = []

    for start_text, end_text in FOCUS_BLOCKS:
        block_start = datetime.combine(
            target_date,
            parser.parse(start_text).time(),
        )
        block_end = datetime.combine(
            target_date,
            parser.parse(end_text).time(),
        )

        has_conflict = any(
            _time_overlaps(block_start, block_end, event_start.replace(tzinfo=None), event_end.replace(tzinfo=None))
            for event_start, event_end, _ in busy_events
        )

        if not has_conflict:
            free_focus_blocks.append(
                {
                    "start": block_start.strftime("%I:%M %p"),
                    "end": block_end.strftime("%I:%M %p"),
                }
            )

    recommendations = []

    if free_focus_blocks:
        recommendations.append(
            f"Use your first open block, {free_focus_blocks[0]['start']} - {free_focus_blocks[0]['end']}, for deep work."
        )
    else:
        recommendations.append("Tomorrow looks packed. Keep your focus list short and prioritize maintenance tasks.")

    if len(events) >= 4:
        recommendations.append("Avoid overloading the day. Pick 1 major task and 2 smaller tasks.")
    else:
        recommendations.append("You have enough room for one bigger focus task and a few lighter tasks.")

    return {
        "date": str(target_date),
        "events": events,
        "free_focus_blocks": free_focus_blocks,
        "recommendations": recommendations,
        "suggested_plan": [
            "Review calendar and deadlines.",
            "Pick one main priority.",
            "Use the best free block for deep work.",
            "Leave a small buffer before scheduled events.",
            "End the day with a quick reset and tomorrow prep.",
        ],
    }


def generate_weekly_summary(start_date_string: str) -> dict:
    start_date = parser.parse(start_date_string).date()
    days = []

    for i in range(7):
        day = start_date + timedelta(days=i)
        plan = generate_daily_plan(day.isoformat())
        days.append(
            {
                "date": day.isoformat(),
                "event_count": len(plan["events"]),
                "free_focus_blocks": plan["free_focus_blocks"],
                "top_recommendation": plan["recommendations"][0],
            }
        )

    busiest_day = max(days, key=lambda d: d["event_count"])
    lightest_day = min(days, key=lambda d: d["event_count"])

    return {
        "week_start": start_date.isoformat(),
        "days": days,
        "summary": [
            f"Busiest day: {busiest_day['date']} with {busiest_day['event_count']} events.",
            f"Lightest day: {lightest_day['date']} with {lightest_day['event_count']} events.",
            "Use lighter days for deep work and heavier days for admin or smaller tasks.",
        ],
    }