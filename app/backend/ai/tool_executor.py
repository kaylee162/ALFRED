import json

from calendar_tools.calendar_intent import handle_calendar_command
from calendar_tools.calendar_service import (
    create_calendar_event,
    list_events_for_day,
    list_upcoming_events,
)

from calendar_tools.planning_service import (
    generate_daily_plan,
    generate_weekly_summary,
)

from tools.project_launcher import (
    list_project_folder,
    open_project_path,
)

from tools.file_manager import (
    search_files,
    list_folder,
    recent_downloads,
    read_text_file,
    open_path,
)

from weather_tools.weather_service import (
    summarize_today,
    summarize_tomorrow,
    summarize_week,
    get_high_today,
    get_humidity_today,
    get_rain_chance_tomorrow,
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


def _format_items(result: dict, empty_message: str = "No files or folders found.") -> str:
    items = result.get("items", [])

    if not items:
        return empty_message

    lines = []

    for item in items:
        icon = "📁" if item.get("type") == "folder" else "📄"
        lines.append(f"- {icon} {item.get('name')}\n  {item.get('path')}")

    return "\n".join(lines)


def execute_tool_call(tool_name: str, arguments: dict | None = None):
    arguments = arguments or {}

    # Project tools
    if tool_name == "list_projects":
        projects = list_project_folder()
        return {
            "response": projects.get("message", "Showing projects."),
            "type": "projects",
            "projects": projects,
            "requires_confirmation": False,
        }

    if tool_name == "list_project_folder":
        projects = list_project_folder(arguments.get("path"))
        return {
            "response": projects.get("message", "Showing project folder."),
            "type": "projects",
            "projects": projects,
            "requires_confirmation": False,
        }

    if tool_name == "open_project_path":
        result = open_project_path(arguments["path"])
        return {
            "response": result.get("message", "Opening project."),
            "type": "project_opened",
            "result": result,
            "requires_confirmation": False,
        }

    # Legacy fallback
    if tool_name == "open_project":
        result = open_project_path(arguments["path"])
        return {
            "response": result.get("message", "Opening project."),
            "type": "project_opened",
            "result": result,
            "requires_confirmation": False,
        }

    # File manager tools
    if tool_name == "search_files":
        result = search_files(
            query=arguments["query"],
            limit=arguments.get("limit", 25),
        )
        return {
            "response": _format_items(result),
            "type": "file_search",
            "results": result,
            "requires_confirmation": False,
        }

    if tool_name == "list_folder":
        result = list_folder(arguments.get("path"))
        return {
            "response": result.get("message", "Showing folder."),
            "type": "folder",
            "folder": result,
            "requires_confirmation": False,
        }

    if tool_name == "recent_downloads":
        result = recent_downloads(
            days=arguments.get("days", 7),
            limit=arguments.get("limit", 25),
        )
        return {
            "response": _format_items(result, "No recent downloads found."),
            "type": "recent_downloads",
            "downloads": result,
            "requires_confirmation": False,
        }

    if tool_name == "read_text_file":
        result = read_text_file(arguments["path"])

        if not result.get("success"):
            return {
                "response": result.get("message", "Could not read that file."),
                "type": "file_read_error",
                "result": result,
                "requires_confirmation": False,
            }

        return {
            "response": result.get("content", ""),
            "type": "file_content",
            "file": result,
            "requires_confirmation": False,
        }

    if tool_name == "open_path":
        result = open_path(arguments["path"])
        return {
            "response": result.get("message", "Opening path."),
            "type": "path_opened",
            "result": result,
            "requires_confirmation": False,
        }

    # Calendar tools
    if tool_name == "calendar":
        response = handle_calendar_command(arguments.get("command", ""))
        return {
            "response": response,
            "requires_confirmation": False,
        }

    if tool_name == "create_calendar_event":
        created = create_calendar_event(
            title=arguments["title"],
            start_time=arguments["start_datetime"],
            end_time=arguments["end_datetime"],
            location=arguments.get("location"),
            description=arguments.get("description"),
            reminder_minutes=arguments.get("reminder_minutes") or 10,
        )

        return {
            "response": f"Created event: {created.get('title', arguments['title'])}",
            "requires_confirmation": False,
            "type": "calendar_event",
            "event": created,
        }

    if tool_name == "get_calendar_day":
        events = list_events_for_day(arguments["date"])
        return {
            "response": _format_events(arguments["date"], events),
            "requires_confirmation": False,
            "type": "calendar_events",
            "events": events,
        }

    if tool_name == "get_upcoming_calendar_events":
        events = list_upcoming_events(
            days=arguments.get("days", 7),
            max_results=arguments.get("max_results", 10),
        )
        return {
            "response": _format_events("upcoming events", events),
            "requires_confirmation": False,
            "type": "calendar_events",
            "events": events,
        }

    if tool_name == "plan_calendar_day":
        plan = generate_daily_plan(arguments["date"])
        return {
            "response": json.dumps(plan, indent=2),
            "requires_confirmation": False,
            "type": "calendar_plan",
            "plan": plan,
        }

    if tool_name == "summarize_calendar_week":
        summary = generate_weekly_summary(arguments["start_date"])
        return {
            "response": json.dumps(summary, indent=2),
            "requires_confirmation": False,
            "type": "calendar_week",
            "summary": summary,
        }

    if tool_name == "email":
        return {
            "response": "Email tools are not connected yet.",
            "requires_confirmation": False,
        }
    
    if tool_name == "get_weather_today":
        try:
            response = summarize_today(arguments.get("location", "Atlanta"))
        except Exception as e:
            response = f"I couldn't fetch the weather right now. Error: {e}"

        return {
            "response": response,
            "requires_confirmation": False,
            "type": "weather",
        }

    if tool_name == "get_weather_tomorrow":
        try:
            response = summarize_tomorrow(arguments.get("location", "Atlanta"))
        except Exception as e:
            response = f"I couldn't fetch tomorrow's weather right now. Error: {e}"

        return {
            "response": response,
            "requires_confirmation": False,
            "type": "weather",
        }

    if tool_name == "get_weather_week":
        try:
            response = summarize_week(arguments.get("location", "Atlanta"))
        except Exception as e:
            response = f"I couldn't fetch this week's weather right now. Error: {e}"

        return {
            "response": response,
            "requires_confirmation": False,
            "type": "weather",
        }

    if tool_name == "get_high_today":
        try:
            response = get_high_today(arguments.get("location", "Atlanta"))
        except Exception as e:
            response = f"I couldn't fetch today's high temperature right now. Error: {e}"

        return {
            "response": response,
            "requires_confirmation": False,
            "type": "weather",
        }

    if tool_name == "get_humidity_today":
        try:
            response = get_humidity_today(arguments.get("location", "Atlanta"))
        except Exception as e:
            response = f"I couldn't fetch today's humidity right now. Error: {e}"

        return {
            "response": response,
            "requires_confirmation": False,
            "type": "weather",
        }

    if tool_name == "get_rain_chance_tomorrow":
        try:
            response = get_rain_chance_tomorrow(arguments.get("location", "Atlanta"))
        except Exception as e:
            response = f"I couldn't fetch tomorrow's rain chance right now. Error: {e}"

        return {
            "response": response,
            "requires_confirmation": False,
            "type": "weather",
        }    

    return {
        "response": f"I understood that as a tool request, but `{tool_name}` is not connected yet.",
        "requires_confirmation": False,
    }