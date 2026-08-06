"""Fast two-stage Ollama router with explicit persistent memory.

Normal chat and tool selection use Ollama. Explicit memory-management commands
are handled deterministically so remembering and forgetting are predictable.
"""

from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ai.alfred_tools import ALFRED_TOOLS
from ai.personality import build_system_prompt
from ai.ollama_client import (
    OllamaConnectionError,
    OllamaError,
    OllamaTimeoutError,
    chat_with_ollama,
)
from ai.tool_executor import execute_tool_call
from context.confirmation_executor import confirmation_choice, execute_pending_action
from context.conversation_context import get_conversation_context
from context.pending_action_store import get_pending_action_store
from context.workflow_store import get_workflow_store
from memory.episodic_service import get_episodic_memory_service
from memory.memory_intent import handle_memory_command, is_memory_command
from memory.memory_service import get_memory_service

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
    "email": {"gmail"},
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
    "gmail",
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

_GREETING_ONLY_PATTERN = re.compile(
    r"^(?:(?:hi|hey|hello|good\s+(?:morning|afternoon|evening))\s+)?"
    r"alfred[,.!?\s]*$|^(?:hi|hey|hello|good\s+(?:morning|afternoon|evening))[,.!?\s]*$",
    re.IGNORECASE,
)


def _daypart(now: datetime) -> str:
    if now.hour < 12:
        return "morning"
    if now.hour < 18:
        return "afternoon"
    return "evening"


def _greeting_response(command: str) -> dict[str, Any] | None:
    """Return a friendly greeting only when the entire request is a greeting."""
    text = re.sub(r"\s+", " ", command.strip())
    if not text or not _GREETING_ONLY_PATTERN.fullmatch(text):
        return None

    now = datetime.now(ZoneInfo(TIMEZONE))
    period = _daypart(now)
    responses = {
        "morning": [
            "Good morning, Kaylee. What are we working on?",
            "Morning, Kaylee. Ready when you are.",
            "Good morning. What can I take care of for you?",
            "Morning. Systems are up and I am at your service.",
        ],
        "afternoon": [
            "Good afternoon, Kaylee. What can I handle for you?",
            "Afternoon, Kaylee. What are we tackling?",
            "Good afternoon. Ready for your next command.",
            "Afternoon. Everything is standing by.",
        ],
        "evening": [
            "Good evening, Kaylee. What can I do for you?",
            "Evening, Kaylee. What are we working on?",
            "Good evening. I am ready when you are.",
            "Evening. Systems are steady and standing by.",
        ],
    }

    return {
        "response": random.choice(responses[period]),
        "requires_confirmation": False,
        "type": "chat",
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
                "Handle Google Calendar requests written in natural language, "
                "including viewing, creating, finding, updating, rescheduling, "
                "renaming, and deleting events. Always pass the user's complete "
                "original calendar command unchanged. Do not guess event IDs, "
                "rewrite dates or times, or perform the update yourself. "
                "Calendar updates and deletions may require ALFRED to show "
                "matching events and ask for confirmation before changes are saved."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "The user's full original calendar request, copied "
                            "exactly without summarizing, rewriting, or resolving "
                            "dates and times."
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


def _system_prompt(
    route: str,
    command: str,
    session_id: str,
) -> str:
    now = datetime.now(ZoneInfo(TIMEZONE))
    memory_context = get_memory_service().build_prompt_context(command)
    conversation_context = (
        get_conversation_context()
        .build_prompt_context(session_id)
    )
    return build_system_prompt(
        route=route,
        now=now,
        timezone=TIMEZONE,
        memory_context=memory_context,
        conversation_context=conversation_context,
    )


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


    if route in {"email", "multi"}:
        # Gmail has one structured command boundary. The Gmail intent layer
        # performs the actual natural-language interpretation, message
        # selection, follow-up resolution, validation, and confirmation flow.
        return "gmail", {"command": command}

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


def _handle_ai_command_core(
    command: str,
    session_id: str,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    greeting = _greeting_response(command)
    if greeting is not None:
        return greeting

    command = _normalize_command(command)

    if is_memory_command(command):
        return handle_memory_command(command)

    if command.startswith("__ALFRED_GMAIL_DRAFT_UPDATE__"):
        result = execute_tool_call("gmail", {"command": command})
        return _return_payload(_result_text(result), [result])

    if not command:
        return {
            "response": "Tell me what you want me to do.",
            "requires_confirmation": False,
            "type": "error",
        }

    try:
        candidate_routes = _candidate_routes(command)

        # Very short follow-ups often omit the tool category: “open the second
        # one”, “move it to Friday”, or “use that version”. Reuse the previous
        # route only when the wording is clearly contextual.
        conversation = get_conversation_context()
        if (
            not candidate_routes
            and conversation.is_contextual_follow_up(command)
        ):
            previous_route = conversation.last_route(session_id)
            if previous_route in TOOL_NAMES_BY_ROUTE:
                candidate_routes = {previous_route}

        # Do not ask the outer routing model to reconstruct Gmail arguments.
        # Every Gmail request is forwarded unchanged to gmail_intent.py, where
        # Ollama performs the Gmail-specific natural-language parsing.
        if candidate_routes == {"email"}:
            LOGGER.info("Forwarding Gmail command to Gmail intent layer: %r", command)
            result = execute_tool_call("gmail", {"command": command})
            return _return_payload(_result_text(result), [result])

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
                "content": _system_prompt(route, command, session_id),
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
                    workflow_store = get_workflow_store()
                    result = (
                        workflow_store.completed_result(
                            workflow_id,
                            fallback_name,
                            fallback_arguments,
                        )
                        if workflow_id
                        else None
                    )
                    if result is None:
                        result = execute_tool_call(fallback_name, fallback_arguments)
                        if workflow_id:
                            workflow_store.record_step(
                                workflow_id=workflow_id,
                                tool_name=fallback_name,
                                arguments=fallback_arguments,
                                result=result,
                            )
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
                if tool_name in {"calendar", "gmail"}:
                    arguments["command"] = command

                try:
                    workflow_store = get_workflow_store()
                    result = (
                        workflow_store.completed_result(
                            workflow_id,
                            tool_name,
                            arguments,
                        )
                        if workflow_id
                        else None
                    )
                    if result is None:
                        result = execute_tool_call(
                            tool_name,
                            arguments,
                        )
                        if workflow_id:
                            workflow_store.record_step(
                                workflow_id=workflow_id,
                                tool_name=tool_name,
                                arguments=arguments,
                                result=result,
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
        

def _infer_route_from_result(result: dict[str, Any]) -> str:
    response_type = str(result.get("type") or "").casefold()
    if response_type.startswith("calendar") or "calendar" in result:
        return "calendar"
    if (
        response_type.startswith("email")
        or response_type.startswith("gmail")
        or any(key in result for key in ("gmail", "email", "emails", "draft", "drafts"))
    ):
        return "email"
    if response_type.startswith("weather") or "weather" in result:
        return "weather"
    if response_type.startswith("project") or "projects" in result:
        return "projects"
    if (
        response_type.startswith("file")
        or response_type in {"folder", "recent_downloads", "path_opened", "path_open_error"}
    ):
        return "files"
    if response_type == "memory":
        return "memory"
    return "chat"


def _record_result(
    *,
    session_id: str,
    original_command: str,
    result: dict[str, Any],
    workflow_id: str | None = None,
) -> dict[str, Any]:
    route = _infer_route_from_result(result)
    response_text = _result_text(result)
    get_conversation_context().add_turn(
        session_id=session_id,
        user_text=original_command,
        assistant_text=response_text,
        route=route,
        response_type=str(result.get("type") or "chat"),
    )

    pending_store = get_pending_action_store()
    if result.get("requires_confirmation"):
        pending_store.capture_from_result(
            session_id=session_id,
            original_command=original_command,
            route=route,
            result=result,
            workflow_id=workflow_id,
        )
    elif route not in {"chat", "memory"}:
        pending_store.clear(session_id)

    response_type = str(result.get("type") or "chat")
    if route != "chat" and response_type != "error":
        get_episodic_memory_service().record(
            session_id=session_id,
            workflow_id=workflow_id,
            route=route,
            event_type=response_type,
            summary=response_text,
            importance=0.75 if result.get("requires_confirmation") else 0.6,
        )

    if workflow_id:
        get_workflow_store().update_status(
            workflow_id,
            "waiting_confirmation" if result.get("requires_confirmation") else "completed",
            route=route,
            final_response=response_text,
        )

    return result


_RESUME_PATTERN = re.compile(
    r"^(?:resume|continue|finish)(?:\s+(?:workflow|task))?(?:\s+([a-f0-9]{8,32}))?[.!]?$",
    re.I,
)


def _resume_requested(command: str) -> str | None | bool:
    match = _RESUME_PATTERN.match(command.strip())
    if not match:
        return False
    return match.group(1) or None

def handle_ai_command(
    command: str,
    session_id: str = "default",
) -> dict[str, Any]:
    """Handle one command with durable memory, workflows, and confirmations."""

    original_command = command.strip()
    workflow_store = get_workflow_store()
    pending_store = get_pending_action_store()

    choice = confirmation_choice(original_command)
    pending = pending_store.get(session_id)
    if choice is not None and pending is not None:
        try:
            result = execute_pending_action(pending, confirmed=choice)
        except Exception as exc:
            LOGGER.exception("Pending action %s failed", pending.action_id)
            result = {
                "response": "I couldn't complete that confirmation. Nothing was changed.",
                "overview": "I couldn't complete that confirmation. Nothing was changed.",
                "type": "confirmation_error",
                "requires_confirmation": False,
                "error": str(exc),
            }

        pending_store.clear(session_id)
        if result.get("requires_confirmation"):
            pending_store.capture_from_result(
                session_id=session_id,
                original_command=pending.original_command,
                route=pending.route,
                result=result,
                workflow_id=pending.workflow_id,
            )
        if pending.workflow_id:
            workflow_store.update_status(
                pending.workflow_id,
                "waiting_confirmation" if result.get("requires_confirmation") else "completed",
                route=pending.route,
                final_response=_result_text(result),
            )
        return _record_result(
            session_id=session_id,
            original_command=original_command,
            result=result,
            workflow_id=pending.workflow_id,
        )

    resume_request = _resume_requested(original_command)
    if resume_request is not False:
        workflow = (
            workflow_store.get(str(resume_request))
            if resume_request
            else workflow_store.latest_resumable(session_id)
        )
        if workflow is None:
            result = {
                "response": "There is no interrupted workflow to resume.",
                "type": "workflow",
                "requires_confirmation": False,
            }
            return _record_result(
                session_id=session_id,
                original_command=original_command,
                result=result,
            )
        workflow_store.update_status(workflow.workflow_id, "active")
        try:
            result = _handle_ai_command_core(
                workflow.original_command,
                session_id,
                workflow.workflow_id,
            )
        except Exception as exc:
            workflow_store.update_status(
                workflow.workflow_id,
                "failed",
                error=str(exc),
            )
            raise
        return _record_result(
            session_id=session_id,
            original_command=original_command,
            result=result,
            workflow_id=workflow.workflow_id,
        )

    workflow = workflow_store.start(
        session_id=session_id,
        original_command=original_command,
    )
    try:
        result = _handle_ai_command_core(
            original_command,
            session_id,
            workflow.workflow_id,
        )
    except Exception as exc:
        workflow_store.update_status(
            workflow.workflow_id,
            "failed",
            error=str(exc),
        )
        raise

    # Learn only clear, durable preferences. Tool results become episodes,
    # not personal facts.
    try:
        learned = get_memory_service().maybe_learn_durable_preference(original_command)
        if learned is not None:
            memory, created = learned
            if created:
                result.setdefault("learned_memory", memory.to_dict())
    except Exception:
        LOGGER.exception("Automatic preference learning failed")

    return _record_result(
        session_id=session_id,
        original_command=original_command,
        result=result,
        workflow_id=workflow.workflow_id,
    )

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
        compact["calendar"] = result.get("calendar")
        compact["requires_confirmation"] = result.get("requires_confirmation", False)

    if tool_name == "weather":
        compact["weather"] = result.get("weather")

    if tool_name == "gmail":
        compact["overview"] = result.get("overview")
        compact["gmail"] = result.get("gmail")
        compact["email"] = result.get("email")
        compact["emails"] = result.get("emails")
        compact["draft"] = result.get("draft")
        compact["drafts"] = result.get("drafts")
        compact["summary"] = result.get("summary")
        compact["confirmation"] = result.get("confirmation")
        compact["requires_confirmation"] = result.get(
            "requires_confirmation",
            False,
        )

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
        "today",
        "tomorrow",
        "this week",
        "rest of today",
        "what's left",
        "whats left",
        "upcoming",
    }

    email_terms = {
        "email",
        "emails",
        "gmail",
        "inbox",
        "unread",
        "message from",
        "reply to",
        "reply",
        "send a message",
        "send an email",
        "draft an email",
        "compose an email",
        "archive that",
        "mark as read",
        "mark as unread",
        "latest mail",
        "newest mail",
        "draft",
        "drafts",
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

    calendar_action = re.search(
        r"\b(move|reschedule|rename|delete|remove|cancel|edit|update|change)\b",
        text,
    )

    if contains_any(calendar_terms) or calendar_action:
        routes.add("calendar")

    email_action = re.search(
        r"\b(read|show|list|find|search|summarize|draft|compose|write|reply|"
        r"send|archive|mark)\b.*\b(email|emails|gmail|inbox|mail|message)\b",
        text,
    )
    email_reference_action = re.search(
        r"\b(reply|archive|mark|send)\b.*\b(that|this|latest|newest)\b",
        text,
    )

    if contains_any(email_terms) or email_action or email_reference_action:
        routes.add("email")

    if contains_any(weather_terms):
        routes.add("weather")

    if contains_any(project_terms):
        routes.add("projects")

    if contains_any(file_terms):
        routes.add("files")

    return routes