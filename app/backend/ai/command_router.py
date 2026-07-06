from datetime import datetime
from zoneinfo import ZoneInfo

from ai.alfred_tools import ALFRED_TOOLS
from ai.ollama_client import chat_with_ollama
from ai.tool_executor import execute_tool_call


TIMEZONE = "America/New_York"


def _system_prompt() -> str:
    now = datetime.now(ZoneInfo(TIMEZONE))
    today = now.date().isoformat()
    month = now.strftime("%B")
    year = now.year

    return f"""
You are ALFRED, a local desktop assistant.

Your job is to understand the user's natural language command and either:
1. call the correct tool, or
2. ask for missing information.

Calendar rules:
- Today's date is {today}.
- The user's timezone is {TIMEZONE}.
- The current month is {month}.
- The current year is {year}.
- If a calendar request has no date, assume today.
- If a date has no month, assume the current month.
- If a date has no year, assume the current year.
- Support multi-day events.
- If the user wants to create a calendar event but does not provide a title, ask for the title.
- If the user provides a start time but no end time, make the event 1 hour long.
- Use ISO datetime strings for start_datetime and end_datetime.
- Do not create, update, or delete anything unless the user clearly asked for it.
- For calendar week summaries, weeks should run Sunday through Saturday.

Response style:
- Be brief and natural.
- Do not mention internal tool names.
"""


def route_command(command: str) -> dict:
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": command},
    ]

    return chat_with_ollama(messages, tools=ALFRED_TOOLS)

def handle_ai_command(command: str) -> dict:
    simple = command.strip().lower()

    quick_responses = {
        "hi": "Hey! What can I help with?",
        "hello": "Hey! What can I help with?",
        "hey": "Hey! What can I help with?",
        "yo": "Hey! What can I help with?",
        "thanks": "No problem.",
        "thank you": "No problem.",
    }

    if simple in quick_responses:
        return {
            "response": quick_responses[simple],
            "requires_confirmation": False,
        }

    response = route_command(command)
    message = response.get("message", {})

    tool_calls = message.get("tool_calls", [])

    if tool_calls:
        tool_call = tool_calls[0]
        function = tool_call.get("function", {})

        tool_name = function.get("name")
        arguments = function.get("arguments", {})

        return execute_tool_call(tool_name, arguments)

    content = message.get("content")

    return {
        "response": content or "I’m not sure how to help with that yet.",
        "requires_confirmation": False,
    }