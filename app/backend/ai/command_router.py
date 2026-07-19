from datetime import datetime
from zoneinfo import ZoneInfo
import re

from ai.ollama_client import chat_with_ollama
from ai.tool_executor import execute_tool_call
from ai.alfred_tools import ALFRED_TOOLS

TIMEZONE = "America/New_York"


def _normalize_command(command: str) -> str:
    text = command.strip()

    # Remove wake word at the beginning.
    text = re.sub(
        r"^(?:(?:hi|hey|hello|ok|okay)\s+)?alfred[:,!\s]*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove polite prefixes.
    text = re.sub(
        r"^(?:can you|could you|would you|will you|please)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()

def _extract_weather_location(command: str) -> str:
    text = command.strip()

    patterns = [
        r"\bin\s+(.+)$",
        r"\bfor\s+(.+)$",
        r"\bat\s+(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            location = match.group(1).strip()

            # Clean common trailing forecast words
            location = re.sub(
                r"\b(today|tomorrow|tmrw|this week|weekly|right now|now)\b",
                "",
                location,
                flags=re.IGNORECASE,
            ).strip()

            if location:
                return location

    return "Atlanta"

def _extract_email_address(command: str) -> str | None:
    match = re.search(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        command,
        flags=re.IGNORECASE,
    )

    return match.group(0) if match else None


def _extract_email_subject(command: str) -> str | None:
    patterns = [
        r"\bwith (?:the )?subject\s+[\"'](.+?)[\"']"
        r"(?:\s+(?:and|that|saying|says|body)\b|$)",

        r"\bwith (?:the )?subject\s+(.+?)"
        r"(?:\s+(?:and say|and saying|saying|that says|with body)\b|$)",

        r"\bsubject\s*:\s*(.+?)"
        r"(?:\s+(?:body\s*:|message\s*:)|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, command, flags=re.IGNORECASE)

        if match:
            subject = match.group(1).strip(" .,\"'")
            if subject:
                return subject

    return None


def _extract_email_body(command: str) -> str | None:
    patterns = [
        r"\b(?:and say|and saying|that says|saying)\s+[\"']?(.+?)[\"']?$",
        r"\b(?:with body|body\s*:|message\s*:)\s+[\"']?(.+?)[\"']?$",
    ]

    for pattern in patterns:
        match = re.search(pattern, command, flags=re.IGNORECASE)

        if match:
            body = match.group(1).strip(" \"'")
            if body:
                return body

    return None


def _parse_email_composition(command: str) -> dict | None:
    text = command.lower()

    is_draft = any(
        phrase in text
        for phrase in [
            "draft an email",
            "draft email",
            "create an email draft",
            "compose an email",
            "write an email",
        ]
    )

    is_send = any(
        phrase in text
        for phrase in [
            "send an email",
            "send email",
            "email ",
        ]
    ) and not is_draft

    if not is_draft and not is_send:
        return None

    recipient = _extract_email_address(command)
    subject = _extract_email_subject(command)
    body = _extract_email_body(command)

    missing_fields = []

    if not recipient:
        missing_fields.append("recipient email address")

    if not subject:
        missing_fields.append("subject")

    if not body:
        missing_fields.append("message")

    if missing_fields:
        return {
            "mode": "missing_email_fields",
            "missing_fields": missing_fields,
        }

    return {
        "mode": "tool",
        "tool": "create_email_draft" if is_draft else "send_email",
        "arguments": {
            "to": recipient,
            "subject": subject,
            "body": body,
        },
    }

def _extract_requested_count(
    text: str,
    default: int = 10,
    maximum: int = 50,
) -> int:
    """
    Extract a requested result count from commands such as:
    - show my 5 newest emails
    - list 10 unread emails
    """
    match = re.search(r"\b(\d{1,2})\b", text)

    if not match:
        return default

    return max(1, min(int(match.group(1)), maximum))


def _extract_email_address(text: str) -> str | None:
    match = re.search(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        text,
        flags=re.IGNORECASE,
    )

    return match.group(0) if match else None


def _extract_sender_phrase(command: str) -> str | None:
    """
    Extract a sender from phrases such as:
    - emails from John
    - latest email from jane@example.com
    """
    match = re.search(
        r"\bfrom\s+(.+?)(?:\s+about\b|\s+with\b|\s+that\b|$)",
        command,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    sender = match.group(1).strip(" .?!")

    return sender or None


def _extract_email_topic(command: str) -> str | None:
    """
    Extract search text from phrases such as:
    - emails about my timecard
    - find emails regarding payroll
    """
    match = re.search(
        r"\b(?:about|regarding|related to)\s+(.+)$",
        command,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    topic = match.group(1).strip(" .?!")

    return topic or None

TOOL_KEYWORDS = [
    "project",
    "projects",
    "source",
    "src",
    "folder",
    "folders",
    "open",
    "launch",
    "calendar",
    "event",
    "meeting",
    "appointment",
    "schedule",
    "email",
    "emails",
    "inbox",
    "summarize my emails",
    "files",
    "file",
    "downloads",
    "desktop",
    "documents",
    "move",
    "rename",
    "delete",
    "weather",
    "forecast",
    "temperature",
    "temp",
    "humidity",
    "rain",
    "precipitation",
    "high temp",
    "low temp",
]


CHAT_KEYWORDS = [
    "hello",
    "hi",
    "hey",
    "what is",
    "what are",
    "explain",
    "define",
    "tell me about",
    "how does",
    "why does",
]


def _system_prompt() -> str:
    now = datetime.now(ZoneInfo(TIMEZONE))

    return f"""
You are ALFRED, a local desktop assistant.

Today's date is {now.date().isoformat()}.
The user's timezone is {TIMEZONE}.

Your job is to understand the user's natural language command and either:
1. call the correct tool, or
2. ask for missing information.

You have two modes:

1. CHAT MODE
Use this for normal AI assistant conversations, explanations, questions, brainstorming, coding help, and casual conversation.
Examples:
- hello
- what is dark matter?
- explain recursion
- help me think through this project idea
- write a quick paragraph about APIs

2. TOOL MODE
Use this only when the user wants ALFRED to act on local tools or connected services.
Examples:
- show me my projects
- open my portfolio project
- create an event tomorrow at 5pm called meeting
- show my calendar
- summarize my emails
- find screenshots
- move files
- rename a file

Available tools:
{ALFRED_TOOLS}

Decide whether the user needs a tool or normal chat.

If a tool is needed, respond ONLY as JSON:
{{
  "mode": "tool",
  "tool": "tool_name",
  "arguments": {{
    "key": "value"
  }}
}}

If no tool is needed, respond ONLY as JSON:
{{
  "mode": "chat"
}}

Calendar rules:
- Today's date is {now.date().isoformat()}.
- The user's timezone is {TIMEZONE}.
- If a calendar request has no date, assume today.
- If a date has no month, assume the current month.
- If a date has no year, assume the current year.
- Support multi-day events.

Weather rules:
- Use weather tools for weather, forecast, temperature, humidity, rain, precipitation, highs, and lows.
- If no location is given, assume Atlanta.
- Understand "tmrw" and "tomorrow" as tomorrow.
- Understand "this week" as the next 7 days.
- For "weather today", call get_weather_today.
- For "weather tomorrow", call get_weather_tomorrow.
- For "weather this week", call get_weather_week.
- For "high temp today", call get_high_today.
- For "humidity today", call get_humidity_today.
- For "chance of rain tomorrow", call get_rain_chance_tomorrow.

Tool rules:
- When a user asks to do something ALFRED can do, call the correct tool.
- Do not say you are showing or opening something unless a tool was actually called.

Gmail rules:
- Use list_unread_emails to show unread inbox messages.
- Use list_recent_emails to show recent inbox messages.
- Use search_emails to find emails by sender, subject, keyword, date, or Gmail query.
- Use read_latest_email when the user asks to read their latest or newest email.
- Use read_email when a Gmail message ID is already known.
- Use summarize_email to summarize one known Gmail message.
- Use summarize_emails for an inbox briefing or several matching emails.
- Use create_email_draft when the user says draft, write, compose, or prepare.
- Do not send an email merely because the user asked to draft it.
- Use send_email only when the user explicitly asks to send it now.
- Use create_reply_draft when the user asks to draft a reply.
- Use send_email_draft only when the user explicitly confirms sending a saved draft.
- Use mark_email_read and mark_email_unread only when a Gmail message ID is known.
- Use archive_email only when a Gmail message ID is known.
- Gmail searches should use Gmail syntax such as:
  in:inbox
  is:unread
  from:person@example.com
  subject:timecard
  newer_than:7d
"""


def _chat_prompt(command: str) -> str:
    return f"""
You are ALFRED, a helpful local AI assistant.

Respond naturally and clearly. Keep answers useful but not overly long unless the user asks for detail.

User: {command}
"""


def _looks_like_tool_request(command: str) -> bool:
    text = command.lower()

    return any(keyword in text for keyword in TOOL_KEYWORDS)


def _looks_like_chat_request(command: str) -> bool:
    text = command.lower()

    return any(text.startswith(keyword) for keyword in CHAT_KEYWORDS)


def _classify_command(command: str) -> dict:
    """
    First use lightweight deterministic checks.
    Then fall back to Ollama JSON classification.
    """

    command = _normalize_command(command)
    text = command.lower()
    location = _extract_weather_location(command)

    email_composition = _parse_email_composition(command)

    if email_composition:
        return email_composition

    # Strong tool shortcuts
    if "show me my projects" in text or "list my projects" in text:
        return {
            "mode": "tool",
            "tool": "list_projects",
            "arguments": {},
        }

    if text.startswith("open project ") or text.startswith("launch project "):
        project_name = (
            text.replace("open project", "", 1)
            .replace("launch project", "", 1)
            .strip()
        )
        return {
            "mode": "tool",
            "tool": "open_project",
            "arguments": {
                "name": project_name,
            },
        }

    if any(
        phrase in text
        for phrase in [
            "calendar",
            "event",
            "events",
            "meeting",
            "meetings",
            "appointment",
            "appointments",
            "schedule",
            "create event",
            "create an event",
            "add event",
            "add an event",
            "delete event",
            "delete the event",
            "remove event",
            "cancel event",
            "update event",
            "update the event",
            "edit event",
            "change event",
            "move event",
            "reschedule",
        ]
    ):
        return {
            "mode": "tool",
            "tool": "calendar",
            "arguments": {
                "command": command,
            },
        }
    
    is_email_request = any(
        phrase in text
        for phrase in [
            "email",
            "emails",
            "inbox",
            "gmail",
        ]
    )

    if is_email_request:
        max_results = _extract_requested_count(text, default=10)

        if "summarize" in text or "briefing" in text:
            query_parts = ["in:inbox"]

            if "unread" in text:
                query_parts.append("is:unread")

            sender = _extract_sender_phrase(command)
            topic = _extract_email_topic(command)

            if sender:
                query_parts.append(f'from:"{sender}"')

            if topic:
                query_parts.append(f'"{topic}"')

            return {
                "mode": "tool",
                "tool": "summarize_emails",
                "arguments": {
                    "query": " ".join(query_parts),
                    "max_results": min(max_results, 10),
                },
            }

        if (
            ("read" in text or "open" in text)
            and any(
                phrase in text
                for phrase in [
                    "latest email",
                    "newest email",
                    "most recent email",
                    "last email",
                ]
            )
        ):
            query_parts = ["in:inbox"]
            sender = _extract_sender_phrase(command)

            if sender:
                query_parts.append(f'from:"{sender}"')

            return {
                "mode": "tool",
                "tool": "read_latest_email",
                "arguments": {
                    "query": " ".join(query_parts),
                    "mark_as_read": True,
                },
            }

        if "unread" in text and any(
            word in text
            for word in [
                "show",
                "list",
                "find",
                "newest",
                "recent",
                "latest",
                "inbox",
                "emails",
            ]
        ):
            return {
                "mode": "tool",
                "tool": "list_unread_emails",
                "arguments": {
                    "max_results": max_results,
                },
            }
        
        if any(word in text for word in ["find", "search", "look for"]):
            query_parts = ["in:inbox"]
            sender = _extract_sender_phrase(command)
            topic = _extract_email_topic(command)
            email_address = _extract_email_address(command)

            if email_address:
                query_parts.append(f"from:{email_address}")
            elif sender:
                query_parts.append(f'from:"{sender}"')

            if topic:
                query_parts.append(f'"{topic}"')

            return {
                "mode": "tool",
                "tool": "search_emails",
                "arguments": {
                    "query": " ".join(query_parts),
                    "max_results": max_results,
                },
            }
        
        if any(
            phrase in text
            for phrase in [
                "show my inbox",
                "show me my inbox",
                "list my emails",
                "show my emails",
                "recent emails",
                "newest emails",
                "latest emails",
            ]
        ):
            return {
                "mode": "tool",
                "tool": "list_recent_emails",
                "arguments": {
                    "max_results": max_results,
                },
            }
    
    if any(
        phrase in text
        for phrase in [
            "weather",
            "forecast",
            "temperature",
            "temp",
            "humidity",
            "rain",
            "precipitation",
            "chance of rain",
            "high temp",
            "low temp",
        ]
    ):
        location = _extract_weather_location(command)

        if "humidity" in text:
            return {
                "mode": "tool",
                "tool": "get_humidity_today",
                "arguments": {"location": location},
            }

        if "chance of rain" in text or "rain chance" in text or "precipitation" in text:
            if "tomorrow" in text or "tmrw" in text:
                return {
                    "mode": "tool",
                    "tool": "get_rain_chance_tomorrow",
                    "arguments": {"location": location},
                }

        if "high" in text:
            return {
                "mode": "tool",
                "tool": "get_high_today",
                "arguments": {"location": location},
            }

        if "tomorrow" in text or "tmrw" in text:
            return {
                "mode": "tool",
                "tool": "get_weather_tomorrow",
                "arguments": {"location": location},
            }

        if "week" in text or "weekly" in text or "7 day" in text:
            return {
                "mode": "tool",
                "tool": "get_weather_week",
                "arguments": {"location": location},
            }

        return {
            "mode": "tool",
            "tool": "get_weather_today",
            "arguments": {"location": location},
        }
    
    # Strong chat shortcuts
    if _looks_like_chat_request(command) and not _looks_like_tool_request(command):
        return {
            "mode": "chat",
        }

    # Fall back to Ollama classification
    raw = chat_with_ollama(
        f"{_system_prompt()}\n\nUser command:\n{command}"
    )

    try:
        import json
        return json.loads(raw)
    except Exception:
        return {
            "mode": "chat",
        }

def _special_response(command: str) -> str | None:
    normalized = command.strip().lower()

    responses = {
        "hey alfred":
            "hey kaylee, what's poppin?",

        "good morning alfred":
            "good morning, kaylee. Early bird gets the worm right :P systems are online and i'm ready whenever you are.",

        "good night alfred":
            "good night, kaylee. don't stay up too late scrolling reels",

        "thanks alfred":
            "fo sizzle :)",

        "thank you alfred":
            "no problemo kaylee",

        "who are you":
            "i'm ALFRED, your local AI assistant. i can manage your projects, calendar, emails, files, weather, and help solve problems or answer questions",

        "who are you alfred":
            "i'm ALFRED, your personal AI assistant. built to keep your projects organized, automate repetitive work, and make your day a little easier :)",

        "how are you alfred":
            "everythings running smoothly, so never better",

        "status report":
            "backend online. calendar synchronized. project tools ready. all systems a go",

        "are you awake":
            "always :/",

        "you there":
            "yup, where else would i be",

        "you there?":
            "when am i not",

        "what's up":
            "the ceiling duh",

        "whats up":
            "the ceiling duh",

        "good job alfred":
            "thanks means a lot kaylee :)",

        "nice work":
            "i'll take that as a successful execution.",

        "im back":
            "barely missed you",

        "miss me":
            "no i appreciated the silence",

        "coffee":
            "nope, you drink enough caffeine for the both of us",

        "coffee?":
            "nope, you drink enough caffeine for the both of us",

        "tell me a joke":
            "there are only 10 kinds of people. those who understand binary, and those who don't.",

        "goodbye alfred":
            "see you later alligator",

        "bye alfred":
            "see you later alligator",

        "see you later alfred":
            "see you later alligator",

        "good afternoon alfred":
            "good afternoon, kaylee. Ready to get some work done?",

        "good evening alfred":
            "good evening, kaylee. Everything is online and ready whenever you are."
    }

    return responses.get(normalized)

def handle_ai_command(command: str) -> dict:
    special = _special_response(command)

    if special:
        return {
            "response": special,
            "requires_confirmation": False,
            "type": "chat",
        }

    command = _normalize_command(command)

    try:
        decision = _classify_command(command)

        if decision.get("mode") == "missing_email_fields":
            missing = decision.get("missing_fields", [])

            if len(missing) == 1:
                missing_text = missing[0]
            else:
                missing_text = (
                    ", ".join(missing[:-1])
                    + f", and {missing[-1]}"
                )

            return {
                "response": (
                    "I can prepare that email, but I still need the "
                    f"{missing_text}."
                ),
                "requires_confirmation": False,
                "type": "email_missing_fields",
            }
    except TimeoutError:
        return {
            "response": "That took too long to process. Try asking again with a different command.",
            "requires_confirmation": False,
            "type": "error",
        }
    except ConnectionError:
        return {
            "response": "I couldn’t connect to Ollama. Make sure Ollama is running, then try again.",
            "requires_confirmation": False,
            "type": "error",
        }
    except Exception as e:
        print("Command classification failed:", e)
        decision = {"mode": "chat"}

    if decision.get("mode") == "tool":
        tool_name = decision.get("tool")
        arguments = decision.get("arguments", {})

        if not tool_name:
            return {
                "response": "I understood this needs a tool, but I couldn’t figure out which one. Try rewording it.",
                "requires_confirmation": False,
                "type": "error",
            }

        try:
            result = execute_tool_call(tool_name, arguments)

            if not result:
                return {
                    "response": f"I tried to run the {tool_name} tool, but it did not return anything.",
                    "requires_confirmation": False,
                    "type": "error",
                }

            return result

        except FileNotFoundError as exc:
            print(f"Tool configuration failed: {tool_name}", exc)

            return {
                "response": (
                    "Gmail is not fully configured yet. "
                    f"{exc}"
                ),
                "requires_confirmation": False,
                "type": "error",
            }

        except PermissionError as exc:
            print(f"Tool permission failed: {tool_name}", exc)

            return {
                "response": (
                    "Google did not allow that action. "
                    "Delete token.json, reconnect your Google account, "
                    "and approve the requested Gmail permissions."
                ),
                "requires_confirmation": False,
                "type": "error",
            }

        except TimeoutError:
            return {
                "response": (
                    f"The {tool_name} request took too long. "
                    "ALFRED is still running, so you can try the request again."
                ),
                "requires_confirmation": False,
                "type": "error",
            }

        except ValueError as exc:
            print(f"Invalid tool request: {tool_name}", exc)

            return {
                "response": str(exc),
                "requires_confirmation": False,
                "type": "error",
            }

        except Exception as exc:
            print(
                f"Tool failed: {tool_name}: "
                f"{type(exc).__name__}: {exc}"
            )

            error_text = str(exc).strip()

            return {
                "response": (
                    f"I understood the request, but the {tool_name} tool "
                    "could not complete it. "
                    + (
                        f"Details: {error_text}"
                        if error_text
                        else "Check that the connected service is available."
                    )
                ),
                "requires_confirmation": False,
                "type": "error",
            }

    try:
        response = chat_with_ollama(
            f"""
You are ALFRED, a helpful AI assistant.

Start with one quick helpful summary sentence, then give the answer. Keep answers useful but not overly long unless the user asks for detail.

User:
{command}
"""
        )

        return {
            "response": response,
            "requires_confirmation": False,
            "type": "chat",
        }

    except TimeoutError:
        return {
            "response": "That took too long to answer. Try asking again with a shorter prompt.",
            "requires_confirmation": False,
            "type": "error",
        }
    except ConnectionError:
        return {
            "response": "I couldn’t connect to Ollama. Make sure Ollama is running, then try again.",
            "requires_confirmation": False,
            "type": "error",
        }
    except Exception as e:
        print("Chat response failed:", e)

        return {
            "response": "I had trouble generating that response, but ALFRED is still running.",
            "requires_confirmation": False,
            "type": "error",
        }