import json

from calendar_tools.calendar_service import (
    create_calendar_event,
    list_events_for_day,
    list_upcoming_events,
)

from calendar_tools.planning_service import (
    generate_daily_plan,
    generate_weekly_summary,
)


def _format_event(event: dict) -> str:
    title = event.get("title", "Untitled")
    start = event.get("start", "Unknown time")
    location = event.get("location")

    if location:
        return f"- {title} at {start} — {location}"

    return f"- {title} at {start}"


def _format_events(label: str, events: list[dict]) -> str:
    if not events:
        return f"No events found for {label}."

    lines = "\n".join(_format_event(event) for event in events)
    return f"Here’s your calendar for {label}:\n\n{lines}"


def _format_created_event(event: dict) -> str:
    title = event.get("title", "Untitled")
    start = event.get("start")
    end = event.get("end")
    location = event.get("location") or "None"

    return (
        f"Created event: {title}\n"
        f"When: {start}\n"
        f"Ends: {end}\n"
        f"Location: {location}"
    )


def execute_tool_call(tool_name: str, arguments: str) -> dict:
    if isinstance(arguments, str):
        args = json.loads(arguments or "{}")
    else:
        args = arguments or {}

    if tool_name == "create_calendar_event":
        created = create_calendar_event(
            title=args["title"],
            start_time=args["start_datetime"],
            end_time=args["end_datetime"],
            location=args.get("location"),
            description=args.get("description"),
            reminder_minutes=args.get("reminder_minutes") or 10,
        )

        return {
            "response": _format_created_event(created),
            "requires_confirmation": False,
            "type": "calendar_event_created",
            "calendar_event": created,
        }

    if tool_name == "get_calendar_day":
        date = args["date"]
        events = list_events_for_day(date)

        return {
            "response": _format_events(date, events),
            "requires_confirmation": False,
            "type": "calendar_events",
            "calendar_events": events,
        }

    if tool_name == "get_upcoming_calendar_events":
        events = list_upcoming_events(
            days=args["days"],
            max_results=args["max_results"],
        )

        return {
            "response": _format_events(f"the next {args['days']} days", events),
            "requires_confirmation": False,
            "type": "calendar_events",
            "calendar_events": events,
        }

    if tool_name == "plan_calendar_day":
        plan = generate_daily_plan(args["date"])

        recommendations = "\n".join(
            f"- {item}" for item in plan["recommendations"]
        )

        focus_blocks = "\n".join(
            f"- {block['start']} to {block['end']}"
            for block in plan["free_focus_blocks"]
        ) or "- No open focus blocks found."

        return {
            "response": (
                f"Plan for {plan['date']}\n\n"
                f"Recommendations:\n{recommendations}\n\n"
                f"Open focus blocks:\n{focus_blocks}"
            ),
            "requires_confirmation": False,
            "type": "calendar_plan",
            "plan": plan,
        }

    if tool_name == "summarize_calendar_week":
        summary = generate_weekly_summary(args["start_date"])

        days = "\n".join(
            f"- {day['date']}: {day['event_count']} event(s)"
            for day in summary["days"]
        )

        summary_lines = "\n".join(
            f"- {item}" for item in summary["summary"]
        )

        return {
            "response": (
                "Weekly Calendar Overview\n\n"
                f"This week:\n{days}\n\n"
                f"Summary:\n{summary_lines}"
            ),
            "requires_confirmation": False,
            "type": "calendar_week_summary",
            "plan": summary,
        }

    return {
        "response": f"I don’t know how to run the tool: {tool_name}",
        "requires_confirmation": False,
    }