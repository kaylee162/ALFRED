from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tools.project_launcher import open_project
from tools.project_launcher import (
    open_project,
    list_project_folder,
    open_project_path,
)

from tools.file_manager import (
    search_files,
    open_path,
    create_folder,
    preview_screenshot_cleanup,
    move_files,
    rename_file,
)

from calendar_tools.calendar_routes import router as calendar_router
from calendar_tools.calendar_intent import handle_calendar_command


app = FastAPI(title="ALFRED Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calendar_router)

pending_action = None


class CommandRequest(BaseModel):
    command: str

class ProjectFolderRequest(BaseModel):
    path: str | None = None


class OpenProjectRequest(BaseModel):
    path: str

@app.get("/")
def health_check():
    return {"status": "ALFRED backend is running"}

@app.post("/projects/list")
def projects_list(request: ProjectFolderRequest):
    return list_project_folder(request.path)


@app.post("/projects/open")
def projects_open(request: OpenProjectRequest):
    return open_project_path(request.path)

@app.post("/command")
def handle_command(request: CommandRequest):
    global pending_action

    raw_command = request.command.strip()
    command = raw_command.lower()

    # Calendar/chat intelligence
    calendar_response = handle_calendar_command(raw_command)
    if calendar_response:
        return {
            "response": calendar_response,
            "requires_confirmation": False,
        }

    if command in ["yes", "confirm", "do it"]:
        if not pending_action:
            return {
                "response": "There is nothing waiting for confirmation.",
                "requires_confirmation": False,
            }

        action = pending_action
        pending_action = None

        if action["type"] == "move_files":
            result = move_files(action["files"], action["destination"])
            return {
                "response": result["message"],
                "requires_confirmation": False,
            }

    if command in ["no", "cancel", "never mind"]:
        pending_action = None
        return {
            "response": "Canceled.",
            "requires_confirmation": False,
        }

    if command.startswith("find ") or command.startswith("search "):
        query = command.replace("find ", "", 1).replace("search ", "", 1).strip()
        matches = search_files(query)

        if not matches:
            return {
                "response": f"I couldn't find anything matching '{query}'.",
                "requires_confirmation": False,
            }

        response = "I found:\n\n" + "\n".join(
            f"- {item['name']} ({item['type']})\n  {item['path']}"
            for item in matches
        )

        return {
            "response": response,
            "requires_confirmation": False,
        }

    if command.startswith("open file "):
        path = raw_command.replace("open file ", "", 1).strip()
        result = open_path(path)

        return {
            "response": result["message"],
            "requires_confirmation": False,
        }

    if command.startswith("create folder "):
        folder_path = raw_command.replace("create folder ", "", 1).strip()
        result = create_folder(folder_path)

        return {
            "response": result["message"],
            "requires_confirmation": False,
        }

    if command.startswith("rename file "):
        try:
            content = raw_command.replace("rename file ", "", 1)
            old_path, new_name = content.split(" to ", 1)

            result = rename_file(old_path.strip(), new_name.strip())

            return {
                "response": result["message"],
                "requires_confirmation": False,
            }
        except ValueError:
            return {
                "response": "Use this format: rename file C:\\path\\file.png to new-name.png",
                "requires_confirmation": False,
            }

    if "organize screenshots" in command or "move screenshots" in command:
        preview = preview_screenshot_cleanup(days=7)

        if preview["count"] == 0:
            return {
                "response": "I didn't find any screenshots from the last 7 days on your Desktop or Downloads folder.",
                "requires_confirmation": False,
            }

        pending_action = {
            "type": "move_files",
            "files": preview["files"],
            "destination": preview["destination"],
        }

        file_list = "\n".join(f"- {file}" for file in preview["files"])

        return {
            "response": (
                f"I found {preview['count']} screenshot(s) from the last 7 days.\n\n"
                f"They will be moved to:\n{preview['destination']}\n\n"
                f"{file_list}\n\n"
                "Type yes to confirm or cancel to stop."
            ),
            "requires_confirmation": True,
        }
    
    if (
        "show me my projects" in command
        or "show projects" in command
        or "my projects" in command
    ):
        result = list_project_folder()

        return {
            "response": result["message"],
            "requires_confirmation": False,
            "type": "project_explorer",
            "project_data": result,
        }

    if "open" in command:
        result = open_project(command)
        return {
            "response": result["message"],
            "requires_confirmation": False,
        }

    return {
        "response": (
            "I can search files, open files, create folders, rename files, "
            "organize screenshots, and help with your calendar. Try asking: "
            "\"what's on my calendar today?\""
        ),
        "requires_confirmation": False,
    }