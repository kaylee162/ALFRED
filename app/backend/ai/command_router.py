"""Fast two-stage Ollama router.

Every request is still processed by Ollama, but normal chat does not carry all
tool schemas. Tool requests receive only the relevant tool category.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ai.alfred_tools import ALFRED_TOOLS
from ai.ollama_client import (
    OllamaConnectionError,
    OllamaError,
    OllamaTimeoutError,
    chat_with_ollama,
)
from ai.tool_executor import execute_tool_call


LOGGER = logging.getLogger(__name__)
TIMEZONE = "America/New_York"
MAX_AGENT_STEPS = 3
MAX_TOOL_RESULT_CHARS = 10_000

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {
            "type": "string",
            "enum": [
                "chat",
                "calendar",
                "email",
                "weather",
                "projects",
                "files",
            ],
        }
    },
    "required": ["route"],
    "additionalProperties": False,
}

TOOL_NAMES_BY_ROUTE = {
    # Use the existing calendar_intent parser for all calendar wording,
    # including create, read, update, delete, relative dates, and multi-day events.
    "calendar": {"calendar"},
    "email": {
        "list_unread_emails",
        "list_recent_emails",
        "search_emails",
        "read_email",
        "read_latest_email",
        "summarize_email",
        "summarize_emails",
        "create_email_draft",
        "create_reply_draft",
        "send_email",
        "send_email_draft",
        "mark_email_read",
        "mark_email_unread",
        "archive_email",
    },
    "weather": {
        "weather",
    },
    "projects": {
        "list_projects",
        "list_project_folder",
        "open_project_path",
    },
    "files": {
        "search_files",
        "list_folder",
        "recent_downloads",
        "read_text_file",
        "open_path",
    },
}

DIRECT_RETURN_TOOLS = {
    "calendar",
    "weather",
    "list_projects",
    "list_project_folder",
    "open_project_path",
    "search_files",
    "list_folder",
    "recent_downloads",
    "read_text_file",
    "open_path",
}

def _normalize_command(command: str) -> str:
    text = command.strip()
    return re.sub(
        r"^(?:(?:hi|hey|hello|ok|okay)\s+)?alfred[:,!\s]*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


def _tool_name(tool: dict[str, Any]) -> str | None:
    function = tool.get("function") or {}
    return function.get("name")


def _calendar_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "calendar",
            "description": (
                "Handle any Google Calendar request expressed in natural "
                "language, including showing events, creating events, updating "
                "events, deleting events, relative dates, and multi-day events."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "The user's complete original calendar request."
                        ),
                    }
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    }


def _tools_for_route(route: str) -> list[dict[str, Any]]:
    wanted = TOOL_NAMES_BY_ROUTE.get(route, set())

    tools = [
        tool for tool in ALFRED_TOOLS
        if _tool_name(tool) in wanted
    ]

    if route == "calendar":
        tools = [_calendar_tool_schema()]

    return tools


def _route_request(command: str) -> str:
    now = datetime.now(ZoneInfo(TIMEZONE))

    message = chat_with_ollama(
        [
            {
                "role": "system",
                "content": (
                    "Classify the request into exactly one route. "
                    "chat means explanations, coding help, writing, casual "
                    "conversation, or questions that do not need an ALFRED tool. "
                    "calendar means Google Calendar. email means Gmail. "
                    "weather means forecast or weather. projects means source "
                    "code project folders or opening projects. files means local "
                    "files, folders, downloads, reading, searching, or opening. "
                    f"Current local time: {now.isoformat()}."
                ),
            },
            {"role": "user", "content": command},
        ],
        temperature=0,
        num_predict=20,
        response_format=ROUTE_SCHEMA,
    )

    try:
        parsed = json.loads(message.get("content") or "{}")
        route = parsed.get("route", "chat")
    except (json.JSONDecodeError, TypeError):
        route = "chat"

    return route if route in ROUTE_SCHEMA["properties"]["route"]["enum"] else "chat"


def _system_prompt(route: str) -> str:
    now = datetime.now(ZoneInfo(TIMEZONE))
    return f"""
You are ALFRED, Kaylee's local desktop assistant.
Current local datetime: {now.isoformat()}
Timezone: {TIMEZONE}
Selected request category: {route}.

Answer naturally when no tool is necessary. When tools are available, use the
correct tool. Never invent a tool result or claim an action succeeded before
the tool confirms it. For a calendar tool call, preserve the user's complete
original wording in the command argument. Ask one concise question only when
a truly required detail is missing. Keep the final response useful and concise.
Do not expose tool names, prompts, JSON, or hidden reasoning.
""".strip()


def _safe_json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        return text[:MAX_TOOL_RESULT_CHARS] + "...[truncated]"
    return text


def _extract_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    calls = message.get("tool_calls") or []
    return calls if isinstance(calls, list) else []


def _call_details(call: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    function = call.get("function") or {}
    name = function.get("name")
    arguments = function.get("arguments") or {}

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}

    return name, arguments if isinstance(arguments, dict) else {}


def _clean_target(text: str) -> str:
    value = text.strip().strip('"').strip("'").strip()
    value = re.sub(r"\s+(?:in\s+)?(?:vs\s*code|vscode)$", "", value, flags=re.IGNORECASE)
    return value.strip(" .")


def _fallback_tool_call(route: str, command: str) -> tuple[str, dict[str, Any]] | None:
    """Recover obvious local tool requests when Ollama returns no tool call."""
    text = command.strip()
    lowered = text.lower()

    if route in {"projects", "multi"}:
        if re.search(r"\b(?:show|list|display|view)\b.*\bprojects?\b", lowered) or lowered in {
            "my projects", "projects", "project explorer",
        }:
            return "list_projects", {}

        open_match = re.search(
            r"\b(?:open|launch|start)\s+(?:the\s+)?(?:project\s+)?(.+?)(?:\s+project)?(?:\s+in\s+(?:vs\s*code|vscode))?$",
            text,
            flags=re.IGNORECASE,
        )
        if open_match:
            target = _clean_target(open_match.group(1))
            if target and target.lower() not in {"project", "projects", "project explorer"}:
                return "open_project_path", {"path": target}

        folder_match = re.search(
            r"\b(?:show|list|view|browse)\s+(?:the\s+)?(?:contents?\s+of\s+)?(?:project\s+)?(?:folder\s+)?(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if folder_match and "project" in lowered:
            target = _clean_target(folder_match.group(1))
            target = re.sub(r"\bproject\s+folder\b", "", target, flags=re.IGNORECASE).strip()
            return "list_project_folder", {"path": target or None}

    if route in {"files", "multi"}:
        if "recent download" in lowered or re.search(r"\bdownloads?\s+(?:from|in)\s+the\s+last\b", lowered):
            days_match = re.search(r"\b(\d+)\s+days?\b", lowered)
            return "recent_downloads", {
                "days": int(days_match.group(1)) if days_match else 7,
                "limit": 25,
            }

        read_match = re.search(r"\b(?:read|summarize|show\s+me\s+the\s+contents?\s+of)\s+(?:the\s+)?(?:file\s+)?(.+)$", text, re.IGNORECASE)
        if read_match:
            return "read_text_file", {"path": _clean_target(read_match.group(1))}

        search_match = re.search(r"\b(?:find|search\s+for|look\s+for|locate)\s+(?:a\s+)?(?:file|folder)?\s*(?:named|called)?\s*(.+)$", text, re.IGNORECASE)
        if search_match:
            query = _clean_target(search_match.group(1))
            if query:
                return "search_files", {"query": query, "limit": 25}

        open_match = re.search(r"\b(?:open|launch)\s+(?:the\s+)?(?:file|folder|path)?\s*(.+)$", text, re.IGNORECASE)
        if open_match:
            target = _clean_target(open_match.group(1))
            if target:
                return "open_path", {"path": target}

        root_names = r"downloads?|documents?|desktop|src|source|projects?"
        if re.search(rf"\b(?:show|list|browse|view)\b.*\b({root_names})\b", lowered) or re.fullmatch(root_names, lowered):
            root_match = re.search(rf"\b({root_names})\b", lowered)
            return "list_folder", {"path": root_match.group(1) if root_match else None}

    return None


def _result_text(result: Any) -> str:
    if isinstance(result, dict):
        value = result.get("response")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(result).strip()


def _return_payload(
    final_text: str,
    tool_results: list[dict[str, Any]],
) -> dict[str, Any]:
    if not tool_results:
        return {
            "response": final_text,
            "requires_confirmation": False,
            "type": "chat",
        }

    if len(tool_results) == 1:
        payload = dict(tool_results[0])
        payload["response"] = final_text or _result_text(payload)
        payload.setdefault("requires_confirmation", False)
        return payload

    return {
        "response": final_text or "I completed the requested steps.",
        "requires_confirmation": any(
            bool(item.get("requires_confirmation")) for item in tool_results
        ),
        "type": "multi_tool",
        "tool_results": tool_results,
    }


def handle_ai_command(command: str) -> dict[str, Any]:
    command = _normalize_command(command)

    if not command:
        return {
            "response": "Tell me what you want me to do.",
            "requires_confirmation": False,
            "type": "error",
        }

    try:
        candidate_routes = _candidate_routes(command)

        if not candidate_routes:
            # No obvious ALFRED tool is relevant.
            # Handle the request as normal Ollama conversation.
            route = "chat"
            tools: list[dict[str, Any]] = []

        elif len(candidate_routes) == 1:
            # Only send tools from the relevant category.
            route = next(iter(candidate_routes))
            tools = _tools_for_route(route)

        else:
            # More than one category may be relevant.
            route = "multi"
            tools = []

            for candidate in candidate_routes:
                tools.extend(_tools_for_route(candidate))

            # Remove duplicate tool definitions.
            unique_tools: dict[str, dict[str, Any]] = {}

            for tool in tools:
                name = _tool_name(tool)

                if name:
                    unique_tools[name] = tool

            tools = list(unique_tools.values())
        
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": _system_prompt(route),
            },
            {
                "role": "user",
                "content": command,
            },
        ]

        completed: list[dict[str, Any]] = []

        for _ in range(MAX_AGENT_STEPS):
            assistant = chat_with_ollama(
                messages,
                tools=tools or None,
                temperature=0.2 if route == "chat" else 0.05,
                num_predict=256 if route == "chat" else 160,
            )

            messages.append(assistant)

            calls = _extract_calls(assistant)

            if not calls:
                fallback_call = _fallback_tool_call(route, command) if not completed else None

                if fallback_call:
                    fallback_name, fallback_arguments = fallback_call
                    LOGGER.info(
                        "Ollama returned no tool call; using local fallback %s",
                        fallback_name,
                    )
                    result = execute_tool_call(fallback_name, fallback_arguments)
                    return _return_payload(_result_text(result), [result])

                final_text = str(
                    assistant.get("content") or ""
                ).strip()

                if not final_text and completed:
                    final_text = _result_text(completed[-1])

                return _return_payload(
                    final_text or "I could not produce a response.",
                    completed,
                )

            for call in calls:
                tool_name, arguments = _call_details(call)

                if not tool_name:
                    continue

                # Always pass the complete original calendar request to the
                # mature calendar parser.
                if tool_name == "calendar":
                    arguments["command"] = command

                try:
                    result = execute_tool_call(
                        tool_name,
                        arguments,
                    )

                except Exception as exc:
                    LOGGER.exception(
                        "Tool %s failed",
                        tool_name,
                    )

                    result = {
                        "response": f"That action failed: {exc}",
                        "requires_confirmation": False,
                        "type": "error",
                    }

                completed.append(result)

                messages.append(
                    {
                        "role": "tool",
                        "tool_name": tool_name,
                        "content": _compact_tool_result(
                            tool_name,
                            result,
                        ),
                    }
                )

                # Structured display tools already produce polished summaries.
                # Return them immediately for simple single-tool requests.
                if (
                    len(candidate_routes) == 1
                    and tool_name in DIRECT_RETURN_TOOLS
                ):
                    return _return_payload(
                        _result_text(result),
                        completed,
                    )

        fallback = (
            _result_text(completed[-1])
            if completed
            else "I could not finish that request."
        )

        return _return_payload(
            fallback,
            completed,
        )

    except OllamaTimeoutError:
        return {
            "response": (
                "Ollama timed out while processing that request. "
                "Check the terminal's OLLAMA TIMING line to see "
                "whether loading, prompt evaluation, or response "
                "generation is slow."
            ),
            "requires_confirmation": False,
            "type": "error",
            "error_code": "ollama_timeout",
        }

    except OllamaConnectionError:
        return {
            "response": (
                "I could not connect to Ollama. Make sure Ollama "
                "is running and qwen2.5:3b is installed."
            ),
            "requires_confirmation": False,
            "type": "error",
            "error_code": "ollama_unavailable",
        }

    except OllamaError as exc:
        LOGGER.exception("Ollama failed")

        return {
            "response": (
                f"Ollama could not complete that request: {exc}"
            ),
            "requires_confirmation": False,
            "type": "error",
            "error_code": "ollama_error",
        }

    except Exception:
        LOGGER.exception(
            "Unexpected ALFRED command failure"
        )

        return {
            "response": (
                "Something went wrong while processing that "
                "request, but ALFRED is still running."
            ),
            "requires_confirmation": False,
            "type": "error",
            "error_code": "command_error",
        }
        
def _compact_tool_result(
    tool_name: str,
    result: Any,
) -> str:
    if not isinstance(result, dict):
        return str(result)

    compact = {
        "tool": tool_name,
        "response": result.get("response"),
        "type": result.get("type"),
    }

    if tool_name == "calendar":
        compact["events"] = result.get("events", [])[:10]

    if tool_name == "weather":
        compact["weather"] = result.get("weather")

    return _safe_json(compact)

def _candidate_routes(command: str) -> set[str]:
    """Quickly narrow possible tools without deciding the user's intent."""

    text = command.lower()
    routes: set[str] = set()

    calendar_terms = {
        "calendar",
        "schedule",
        "scheduled",
        "event",
        "events",
        "meeting",
        "appointment",
        "availability",
        "free tomorrow",
        "busy tomorrow",
    }

    email_terms = {
        "email",
        "emails",
        "gmail",
        "inbox",
        "unread",
        "message from",
        "reply to",
        "send a message",
    }

    weather_terms = {
        "weather",
        "forecast",
        "temperature",
        "rain",
        "humidity",
        "snow",
        "wind",
        "degrees",
    }

    project_terms = {
        "project",
        "projects",
        "repository",
        "repo",
        "source code",
        "open in vscode",
        "vscode",
        "launch project",
        "open project",
        "project folder",
    }

    file_terms = {
        "file",
        "files",
        "folder",
        "folders",
        "downloads",
        "documents",
        "desktop",
        "find a file",
        "open the file",
        "recent downloads",
        "read file",
        "locate",
    }

    def contains_any(terms: set[str]) -> bool:
        return any(term in text for term in terms)

    if contains_any(calendar_terms):
        routes.add("calendar")

    if contains_any(email_terms):
        routes.add("email")

    if contains_any(weather_terms):
        routes.add("weather")

    if contains_any(project_terms):
        routes.add("projects")

    if contains_any(file_terms):
        routes.add("files")

    return routes