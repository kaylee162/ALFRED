import json
import re
from pathlib import Path

from ai.ollama_client import chat_with_ollama
from tools.file_manager import (
    search_files,
    open_path,
    create_folder,
    preview_screenshot_cleanup,
    move_files,
    rename_file,
)
from tools.project_launcher import (
    list_project_folder,
    open_project_path,
)

pending_action = None


def _ollama(prompt: str) -> str:
    try:
        result = chat_with_ollama(prompt)

        if isinstance(result, dict):
            return result.get("response") or result.get("message") or str(result)

        return str(result)

    except Exception as e:
        return json.dumps({
            "tool": "chat",
            "args": {
                "message": f"I had trouble reaching Ollama: {e}"
            }
        })

def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"tool": "chat", "args": {"message": text}}

    try:
        return json.loads(match.group(0))
    except Exception:
        return {"tool": "chat", "args": {"message": text}}


def _tool_prompt(command: str) -> str:
    return f"""
You are ALFRED or alfred, a local desktop assistant.

Choose exactly one tool for the user's request.

Available tools:
- chat: for greetings or normal conversation
- search_files: find files or folders by name
- open_path: open a file or folder by exact path
- create_folder: create a folder at a path
- preview_screenshot_cleanup: find recent screenshots on Desktop/Downloads before moving them
- move_files: move files to a destination folder, only after confirmation
- rename_file: rename a file, only after confirmation
- list_project_folder: show projects or list a project folder
- open_project_path: open a project folder in VS Code

Return only valid JSON in this format:
{{
  "tool": "tool_name",
  "args": {{
    "query": "",
    "path": "",
    "folder_path": "",
    "days": 7,
    "file_paths": [],
    "destination": "",
    "new_name": "",
    "message": ""
  }}
}}

Rules:
- If the user wants to see projects, use list_project_folder.
- If the user wants to open a project in VS Code and gives a path, use open_project_path.
- If the user asks to find/search/look for something, use search_files.
- If the user asks to clean up screenshots, use preview_screenshot_cleanup.
- If important info is missing, use chat and ask one short follow-up question.
- Do not invent exact file paths.

User request:
{command}
"""


def handle_ai_command(command: str) -> dict:
    global pending_action

    normalized = command.strip().lower()

    if normalized in [
        "show me my projects",
        "show projects",
        "my projects",
        "list projects",
        "open projects",
    ]:
        result = list_project_folder()
        return {
            "response": result["message"],
            "requires_confirmation": False,
            "type": "project_list",
            **result,
        }

    if normalized in ["yes", "confirm", "do it", "yep", "yeah"]:
        if not pending_action:
            return {
                "response": "There is nothing waiting for confirmation.",
                "requires_confirmation": False,
            }

        action = pending_action
        pending_action = None

        if action["tool"] == "move_files":
            result = move_files(action["file_paths"], action["destination"])
            return {
                "response": result["message"],
                "requires_confirmation": False,
                "type": "file_action",
                **result,
            }

        if action["tool"] == "rename_file":
            result = rename_file(action["path"], action["new_name"])
            return {
                "response": result["message"],
                "requires_confirmation": False,
                "type": "file_action",
                **result,
            }

    if normalized in ["no", "cancel", "never mind", "stop"]:
        pending_action = None
        return {
            "response": "Canceled.",
            "requires_confirmation": False,
        }

    decision = _extract_json(_ollama(_tool_prompt(command)))
    tool = decision.get("tool", "chat")
    args = decision.get("args", {}) or {}

    if tool == "chat":
        message = args.get("message") or _ollama(command)
        return {
            "response": message,
            "requires_confirmation": False,
            "type": "chat",
        }

    if tool == "search_files":
        query = args.get("query") or command
        matches = search_files(query)

        if not matches:
            return {
                "response": f"I couldn't find anything matching '{query}'.",
                "requires_confirmation": False,
                "type": "file_search",
                "files": [],
            }

        return {
            "response": f"I found {len(matches)} result(s) for '{query}'.",
            "requires_confirmation": False,
            "type": "file_search",
            "files": matches,
        }

    if tool == "open_path":
        path = args.get("path")
        if not path:
            return {
                "response": "Which file or folder should I open?",
                "requires_confirmation": False,
            }

        result = open_path(path)
        return {
            "response": result["message"],
            "requires_confirmation": False,
            "type": "file_action",
            **result,
        }

    if tool == "create_folder":
        folder_path = args.get("folder_path") or args.get("path")
        if not folder_path:
            return {
                "response": "Where should I create the folder?",
                "requires_confirmation": False,
            }

        result = create_folder(folder_path)
        return {
            "response": result["message"],
            "requires_confirmation": False,
            "type": "file_action",
            **result,
        }

    if tool == "preview_screenshot_cleanup":
        days = int(args.get("days") or 7)
        preview = preview_screenshot_cleanup(days)

        if preview["count"] == 0:
            return {
                "response": f"I didn't find any recent screenshots from the last {days} day(s).",
                "requires_confirmation": False,
                "type": "screenshot_cleanup",
                **preview,
            }

        pending_action = {
            "tool": "move_files",
            "file_paths": preview["files"],
            "destination": preview["destination"],
        }

        return {
            "response": (
                f"I found {preview['count']} screenshot(s). "
                f"Move them to {preview['destination']}?"
            ),
            "requires_confirmation": True,
            "type": "screenshot_cleanup",
            **preview,
        }

    if tool == "move_files":
        file_paths = args.get("file_paths") or []
        destination = args.get("destination")

        if not file_paths or not destination:
            return {
                "response": "I need the files and destination before I can move anything.",
                "requires_confirmation": False,
            }

        pending_action = {
            "tool": "move_files",
            "file_paths": file_paths,
            "destination": destination,
        }

        return {
            "response": f"Move {len(file_paths)} file(s) to {destination}?",
            "requires_confirmation": True,
            "type": "file_action",
        }

    if tool == "rename_file":
        path = args.get("path")
        new_name = args.get("new_name")

        if not path or not new_name:
            return {
                "response": "I need the file path and the new name.",
                "requires_confirmation": False,
            }

        pending_action = {
            "tool": "rename_file",
            "path": path,
            "new_name": new_name,
        }

        return {
            "response": f"Rename this file to {new_name}?",
            "requires_confirmation": True,
            "type": "file_action",
        }

    if tool == "list_project_folder":
        path = args.get("path") or None
        result = list_project_folder(path)

        return {
            "response": result["message"],
            "requires_confirmation": False,
            "type": "project_list",
            **result,
        }

    if tool == "open_project_path":
        path = args.get("path")
        if not path:
            return {
                "response": "Which project folder should I open?",
                "requires_confirmation": False,
            }

        result = open_project_path(path)
        return {
            "response": result["message"],
            "requires_confirmation": False,
            "type": "project_action",
            **result,
        }

    return {
        "response": "I understood the request, but I don't know which ALFRED tool to use yet.",
        "requires_confirmation": False,
    }