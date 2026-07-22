import asyncio
import logging
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai.command_router import handle_ai_command
from ai.ollama_client import ollama_health
from calendar_tools.calendar_routes import router as calendar_router
from tools.file_manager import (
    list_folder,
    open_path,
    read_text_file,
    recent_downloads,
    search_files,
)
from tools.project_launcher import list_project_folder, open_project_path


logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

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
    command: str = Field(min_length=1, max_length=20_000)


class ProjectFolderRequest(BaseModel):
    path: str | None = None


class OpenProjectRequest(BaseModel):
    path: str


class SearchFilesRequest(BaseModel):
    query: str
    limit: int = Field(default=25, ge=1, le=100)


class FolderRequest(BaseModel):
    path: str | None = None


class RecentDownloadsRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=365)
    limit: int = Field(default=25, ge=1, le=100)


class ReadFileRequest(BaseModel):
    path: str


class OpenPathRequest(BaseModel):
    path: str


@app.get("/")
def health_check():
    return {
        "status": "ALFRED backend is running",
        "ollama": ollama_health(),
    }


@app.post("/projects/list")
def projects_list(request: ProjectFolderRequest):
    return list_project_folder(request.path)


@app.post("/projects/open")
def projects_open(request: OpenProjectRequest):
    return open_project_path(request.path)


@app.post("/files/search")
def files_search(request: SearchFilesRequest):
    return search_files(request.query, request.limit)


@app.post("/files/list")
def files_list(request: FolderRequest):
    return list_folder(request.path)


@app.post("/files/recent-downloads")
def files_recent_downloads(request: RecentDownloadsRequest):
    return recent_downloads(request.days, request.limit)


@app.post("/files/read")
def files_read(request: ReadFileRequest):
    return read_text_file(request.path)


@app.post("/files/open")
def files_open(request: OpenPathRequest):
    return open_path(request.path)


@app.post("/command")
async def handle_command(request: CommandRequest):
    """Run blocking Ollama/tool work off FastAPI's event loop."""

    command = request.command.strip()
    if not command:
        return {
            "response": "Tell me what you want me to do.",
            "requires_confirmation": False,
            "type": "error",
        }

    try:
        result = await asyncio.to_thread(handle_ai_command, command)
        if result:
            return result
        return {
            "response": "I tried to handle that, but nothing came back.",
            "requires_confirmation": False,
            "type": "error",
        }
    except Exception as exc:
        LOGGER.error("Command failed: %s\n%s", exc, traceback.format_exc())
        return {
            "response": (
                "Something went wrong while handling that request, but "
                "ALFRED is still running."
            ),
            "requires_confirmation": False,
            "type": "error",
            "error": str(exc),
        }
