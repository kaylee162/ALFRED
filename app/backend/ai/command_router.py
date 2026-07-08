from datetime import datetime
from zoneinfo import ZoneInfo

from ai.ollama_client import chat_with_ollama
from ai.tool_executor import execute_tool_call
from ai.alfred_tools import ALFRED_TOOLS

TIMEZONE = "America/New_York"

import re


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

    if any(phrase in text for phrase in ["my emails", "my inbox", "summarize emails", "summarize my emails"]):
        return {
            "mode": "tool",
            "tool": "email",
            "arguments": {
                "command": command,
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

    decision = _classify_command(command)

    if decision.get("mode") == "tool":
        tool_name = decision.get("tool")
        arguments = decision.get("arguments", {})

        return execute_tool_call(tool_name, arguments)

    response = chat_with_ollama(
        f"""
You are ALFRED, a helpful AI assistant.

Respond naturally and clearly. Keep answers useful but not overly long unless the user asks for detail.

User:
{command}
"""
    )

    return {
        "response": response,
        "requires_confirmation": False,
        "type": "chat",
    }