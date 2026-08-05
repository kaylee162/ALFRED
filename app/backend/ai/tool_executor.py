import logging

from collections import Counter
from datetime import datetime

from calendar_tools.calendar_intent import handle_calendar_command

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

from gmail_tools.gmail_intent import handle_gmail_command


LOGGER = logging.getLogger(__name__)

def _format_event(event: dict) -> str:
    title = event.get("title", "Untitled")
    start = event.get("start", "Unknown time")
    location = str(event.get("location") or "").strip()
    suffix = f" at {location}" if location else ""
    return f"- {title} at {start}{suffix}"


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
        path = arguments.get("path")
        if not path:
            return {
                "response": "Tell me which project you want to open.",
                "type": "project_open_error",
                "requires_confirmation": False,
            }
        result = open_project_path(path)
        summary = (
            "Absolutely, I opened that project for you."
            if result.get("success")
            else "I couldn't open that project."
        )

        return {
            "response": _with_summary(
                summary,
                result.get("message", "Opening project."),
            ),
            "type": "project_opened" if result.get("success") else "project_open_error",
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
        query = str(arguments.get("query") or "").strip()
        if not query:
            return {
                "response": "Tell me what file or folder to search for.",
                "type": "file_search_error",
                "requires_confirmation": False,
            }
        result = search_files(
            query=query,
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
        path = arguments.get("path")
        if not path:
            return {
                "response": "Tell me which text file you want me to read.",
                "type": "file_read_error",
                "requires_confirmation": False,
            }
        result = read_text_file(path)

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
        path = arguments.get("path")
        if not path:
            return {
                "response": "Tell me which file or folder you want to open.",
                "type": "path_open_error",
                "requires_confirmation": False,
            }
        result = open_path(path)
        summary = (
            "Absolutely, I opened that path for you."
            if result.get("success")
            else "I couldn't open that path."
        )

        return {
            "response": _with_summary(
                summary,
                result.get("message", "Opening path."),
            ),
            "type": "path_opened" if result.get("success") else "path_open_error",
            "result": result,
            "requires_confirmation": False,
        }

    # Calendar is a single structured boundary. The intent module owns all
    # interpretation, searching, ambiguity, previews, and confirmation state.
    if tool_name == "calendar":
        command = str(arguments.get("command") or "").strip()
        if not command:
            return {
                "response": "I need a calendar command before I can continue.",
                "overview": "I need a calendar command before I can continue.",
                "type": "calendar_error",
                "requires_confirmation": False,
            }
        try:
            result = handle_calendar_command(command)
        except Exception:
            LOGGER.exception("Calendar command failed: %s", command)
            return {
                "response": "I couldn't safely process that calendar request. No event was changed.",
                "overview": "I couldn't safely process that calendar request. No event was changed.",
                "type": "calendar_error",
                "requires_confirmation": False,
            }
        if result is None:
            return {
                "response": "I couldn't determine which calendar action to take. No event was changed.",
                "overview": "I couldn't determine which calendar action to take. No event was changed.",
                "type": "calendar_error",
                "requires_confirmation": False,
            }
        return result

    # Gmail is a single structured boundary. Ollama passes the original
    # request unchanged; gmail_intent owns parsing, message selection,
    # follow-up context, confirmations, and Gmail API calls.
    if tool_name == "gmail":
        command = str(arguments.get("command") or "").strip()
        if not command:
            return {
                "response": "I need a Gmail command before I can continue.",
                "overview": "I need a Gmail command before I can continue.",
                "type": "email_error",
                "requires_confirmation": False,
            }
        try:
            result = handle_gmail_command(command)
        except Exception:
            LOGGER.exception("Gmail command failed: %s", command)
            return {
                "response": (
                    "I couldn't safely process that Gmail request. "
                    "No email was sent or changed."
                ),
                "overview": (
                    "I couldn't safely process that Gmail request. "
                    "No email was sent or changed."
                ),
                "type": "email_error",
                "requires_confirmation": False,
            }
        if not result:
            return {
                "response": "I couldn't determine which Gmail action to take.",
                "overview": "I couldn't determine which Gmail action to take.",
                "type": "email_error",
                "requires_confirmation": False,
            }
        return result

    # Weather tool
    if tool_name == "weather":
        location = str(arguments.get("location") or "Atlanta").strip()
        period = str(arguments.get("period") or "today").strip().lower()
        detail = str(arguments.get("detail") or "summary").strip().lower()

        valid_periods = {"today", "tomorrow", "week"}
        valid_details = {"summary", "high", "humidity", "rain_chance"}

        if period not in valid_periods:
            period = "today"

        if detail not in valid_details:
            detail = "summary"

        try:
            if detail == "high":
                response = get_high_today(location)
                summary_tool_name = "get_high_today"

            elif detail == "humidity":
                response = get_humidity_today(location)
                summary_tool_name = "get_humidity_today"

            elif detail == "rain_chance":
                if period != "tomorrow":
                    return {
                        "response": (
                            "Right now, ALFRED supports rain chance for "
                            "tomorrow. Try asking for tomorrow's rain chance."
                        ),
                        "requires_confirmation": False,
                        "type": "weather",
                    }

                response = get_rain_chance_tomorrow(location)
                summary_tool_name = "get_rain_chance_tomorrow"

            elif period == "tomorrow":
                response = summarize_tomorrow(location)
                summary_tool_name = "get_weather_tomorrow"

            elif period == "week":
                response = summarize_week(location)
                summary_tool_name = "get_weather_week"

            else:
                response = summarize_today(location)
                summary_tool_name = "get_weather_today"

        except Exception as exc:
            LOGGER.exception("Weather request failed for %s", location)
            return {
                "response": (
                    "I couldn't fetch the weather right now. "
                    f"Error: {exc}"
                ),
                "requires_confirmation": False,
                "type": "weather",
            }

        return {
            "response": _with_summary(
                _summarize_weather(summary_tool_name, location),
                response,
            ),
            "requires_confirmation": False,
            "type": "weather",
            "weather": {
                "location": location,
                "period": period,
                "detail": detail,
            },
        }

    return {
        "response": f"I understood that as a tool request, but `{tool_name}` is not connected yet.",
        "requires_confirmation": False,
    }