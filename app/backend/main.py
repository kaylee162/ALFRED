from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai.command_router import handle_ai_command
from calendar_tools.calendar_routes import router as calendar_router

from tools.project_launcher import (
    open_project_path,
    list_project_folder,
)

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
    command = request.command.strip()

    if not command:
        return {
            "response": "Tell me what you want me to do.",
            "requires_confirmation": False,
        }

    return handle_ai_command(command)