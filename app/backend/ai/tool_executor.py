import json

from collections import Counter
from datetime import datetime

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
        return _summarize_calendar_events(label, events)

    lines = "\n".join(_format_event(event) for event in events)
    body = f"Here’s your calendar for {label}:\n\n{lines}"

    return _with_summary(_summarize_calendar_events(label, events), body)

def _format_items(result: dict, empty_message: str = "No files or folders found.") -> str:
    items = result.get("items", [])

    if not items:
        return _with_summary(
            "Absolutely, I checked that for you. Nothing showed up.",
            empty_message,
        )

    lines = []

    for item in items:
        icon = "📁" if item.get("type") == "folder" else "📄"
        lines.append(f"- {icon} {item.get('name')}\n  {item.get('path')}")

    return _with_summary(
        _summarize_items("that folder", items),
        "\n".join(lines),
    )

def _parse_event_datetime(value: str | None):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None

def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"

def _with_summary(summary: str, body: str) -> str:
    body = (body or "").strip()

    if not body:
        return summary

    return f"{summary}\n\n{body}"


def _summarize_calendar_events(label: str, events: list[dict]) -> str:
    if not events:
        return f"Absolutely, here's your calendar for {label}. Looks clear, no events found."

    day_counts = Counter()

    for event in events:
        start = _parse_event_datetime(event.get("start"))
        if start:
            day_counts[start.strftime("%A")] += 1

    total = len(events)

    if total <= 2:
        vibe = "looks pretty light"
    elif total <= 5:
        vibe = "you've got a moderate schedule"
    else:
        vibe = "looks like a busy stretch"

    if not day_counts:
        return f"Absolutely, here's your calendar for {label}. {vibe}, with {_plural(total, 'event')}."

    day_summary = ", ".join(
        f"{count} on {day}" for day, count in day_counts.most_common()
    )

    return f"Absolutely, here's your calendar for {label}. {vibe}, with {day_summary}."


def _summarize_items(label: str, items: list[dict]) -> str:
    if not items:
        return f"Absolutely, I checked {label}. Nothing showed up."

    folders = sum(1 for item in items if item.get("type") == "folder")
    files = sum(1 for item in items if item.get("type") == "file")

    parts = []

    if folders:
        parts.append(_plural(folders, "folder"))

    if files:
        parts.append(_plural(files, "file"))

    item_summary = " and ".join(parts) if parts else _plural(len(items), "item")

    return f"Absolutely, here's what I found in {label}. I found {item_summary}."


def _summarize_weather(tool_name: str, location: str) -> str:
    if tool_name == "get_weather_today":
        return f"Absolutely, here's today's weather for {location}."

    if tool_name == "get_weather_tomorrow":
        return f"Absolutely, here's tomorrow's forecast for {location}."

    if tool_name == "get_weather_week":
        return f"Absolutely, here's the week forecast for {location}."

    if tool_name == "get_high_today":
        return f"Absolutely, here's today's high for {location}."

    if tool_name == "get_humidity_today":
        return f"Absolutely, here's today's humidity for {location}."

    if tool_name == "get_rain_chance_tomorrow":
        return f"Absolutely, here's tomorrow's rain chance for {location}."

    return f"Absolutely, here's the weather update for {location}."

def _with_summary(summary: str, body: str) -> str:
    body = body.strip()

    if not body:
        return summary

    return f"{summary}\n\n{body}"

def execute_tool_call(tool_name: str, arguments: dict | None = None):
    arguments = arguments or {}

    # Project tools
    if tool_name == "list_projects":
        projects = list_project_folder()
        items = projects.get("items", [])

        return {
            "response": _with_summary(
                _summarize_items("your projects", items),
                projects.get("message", "Showing projects."),
            ),
            "type": "projects",
            "projects": projects,
            "requires_confirmation": False,
        }

    if tool_name == "list_project_folder":
        projects = list_project_folder(arguments.get("path"))
        items = projects.get("items", [])

        return {
            "response": _with_summary(
                _summarize_items("this project folder", items),
                projects.get("message", "Showing project folder."),
            ),
            "type": "projects",
            "projects": projects,
            "requires_confirmation": False,
        }

    if tool_name == "open_project_path":
        result = open_project_path(arguments["path"])

        return {
            "response": _with_summary(
                "Absolutely, I opened that project for you.",
                result.get("message", "Opening project."),
            ),
            "type": "project_opened",
            "result": result,
            "requires_confirmation": False,
        }

    # Legacy fallback
    if tool_name == "open_project":
        result = open_project_path(arguments["path"])

        return {
            "response": _with_summary(
                "Absolutely, I opened that project for you.",
                result.get("message", "Opening project."),
            ),
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
            "response": _with_summary(
                _summarize_items("that folder", result.get("items", [])),
                result.get("message", "Showing folder."),
            ),
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
            "response": _with_summary(
                "Here is the content of that file.",
                result.get("content", ""),
            ),
            "type": "file_content",
            "file": result,
            "requires_confirmation": False,
        }

    if tool_name == "open_path":
        result = open_path(arguments["path"])

        return {
            "response": _with_summary(
                "Absolutely, I opened that path for you.",
                result.get("message", "Opening path."),
            ),
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
            "response": _with_summary(
                f"Absolutely, I created {created.get('title', arguments['title'])}.",
                f"Created event: {created.get('title', arguments['title'])}",
            ),
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

    if tool_name == "email":
        return {
            "response": "Email tools are not connected yet.",
            "requires_confirmation": False,
        }
    
    if tool_name == "get_weather_today":
        location = arguments.get("location", "Atlanta")

        try:
            response = summarize_today(location)
        except Exception as e:
            response = f"I couldn't fetch the weather right now. Error: {e}"

        return {
            "response": _with_summary(
                _summarize_weather(tool_name, location),
                response,
            ),
            "requires_confirmation": False,
            "type": "weather",
        }

    if tool_name == "get_weather_tomorrow":
        location = arguments.get("location", "Atlanta")

        try:
            response = summarize_tomorrow(location)
        except Exception as e:
            response = f"I couldn't fetch tomorrow's weather right now. Error: {e}"

        return {
            "response": _with_summary(
                _summarize_weather(tool_name, location),
                response,
            ),
            "requires_confirmation": False,
            "type": "weather",
        }

    if tool_name == "get_weather_week":
        location = arguments.get("location", "Atlanta")

        try:
            response = summarize_week(location)
        except Exception as e:
            response = f"I couldn't fetch this week's weather right now. Error: {e}"

        return {
            "response": _with_summary(
                _summarize_weather(tool_name, location),
                response,
            ),
            "requires_confirmation": False,
            "type": "weather",
        }

    if tool_name == "get_high_today":
        location = arguments.get("location", "Atlanta")

        try:
            response = get_high_today(location)
        except Exception as e:
            response = f"I couldn't fetch today's high temperature right now. Error: {e}"

        return {
            "response": _with_summary(
                _summarize_weather(tool_name, location),
                response,
            ),
            "requires_confirmation": False,
            "type": "weather",
        }

    if tool_name == "get_humidity_today":
        location = arguments.get("location", "Atlanta")

        try:
            response = get_humidity_today(location)
        except Exception as e:
            response = f"I couldn't fetch today's humidity right now. Error: {e}"

        return {
            "response": _with_summary(
                _summarize_weather(tool_name, location),
                response,
            ),
            "requires_confirmation": False,
            "type": "weather",
        }

    if tool_name == "get_rain_chance_tomorrow":
        location = arguments.get("location", "Atlanta")

        try:
            response = get_rain_chance_tomorrow(location)
        except Exception as e:
            response = f"I couldn't fetch tomorrow's rain chance right now. Error: {e}"

        return {
            "response": _with_summary(
                _summarize_weather(tool_name, location),
                response,
            ),
            "requires_confirmation": False,
            "type": "weather",
        }

    return {
        "response": f"I understood that as a tool request, but `{tool_name}` is not connected yet.",
        "requires_confirmation": False,
    }