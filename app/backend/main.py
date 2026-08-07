import asyncio
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from memory.memory_service import MemoryValidationError, get_memory_service
from context.conversation_context import get_conversation_context
from context.pending_action_store import get_pending_action_store
from context.workflow_store import get_workflow_store
from memory.episodic_service import get_episodic_memory_service

from ai.command_router import handle_ai_command
from ai.ollama_client import ollama_health, warm_ollama
from calendar_tools.calendar_routes import router as calendar_router
from gmail_tools.gmail_intent import handle_gmail_confirmation
from gmail_tools.gmail_service import gmail_health
from startup.startup_briefing_service import build_startup_briefing
from tools.file_manager import (
    list_folder,
    open_path,
    read_text_file,
    recent_downloads,
    search_files,
)
from tools.project_launcher import (
    open_project_path,
    open_project_in_vscode,
    list_project_folder,
)

from routes.voice import router as voice_router
from services.voice_service import voice_service

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    voice_task = asyncio.create_task(
        asyncio.to_thread(voice_service.warm_up)
    )

    yield

    if not voice_task.done():
        voice_task.cancel()
        
app = FastAPI(title="ALFRED Backend", lifespan=lifespan)

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
app.include_router(voice_router)


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=20_000)
    session_id: str = Field(default="default", min_length=1, max_length=100)


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


class MemoryUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    category: str | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    is_pinned: bool | None = None


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    category: str | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    is_pinned: bool = False


class GmailConfirmationRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    confirmed: bool


@app.get("/")
def health_check():
    return {
        "status": "ALFRED backend is running",
        "ollama": ollama_health(),
    }


@app.get("/startup/briefing")
async def startup_briefing():
    try:
        return await asyncio.to_thread(
            build_startup_briefing,
        )
    except Exception as exc:
        LOGGER.error("Startup briefing failed: %s\n%s", exc, traceback.format_exc())
        return {
            "type": "startup_briefing",
            "greeting": "Welcome back",
            "message": (
                "Core systems are online, but I could not complete the full briefing. "
                "You can still use ALFRED normally."
            ),
            "action": None,
            "systems": {
                "backend": {"online": True},
                "calendar": {"online": False},
                "gmail": {"online": False},
                "ollama": {"online": False},
                "voice": {"online": False},
            },
            "error": str(exc),
        }


@app.post("/projects/list")
def projects_list(request: ProjectFolderRequest):
    return list_project_folder(request.path)


@app.post("/projects/open")
def projects_open(request: OpenProjectRequest):
    return open_project_path(request.path)


@app.post("/projects/open-vscode")
def projects_open_vscode(request: OpenProjectRequest):
    return open_project_in_vscode(request.path)


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


@app.get("/memory")
def memory_list(limit: int = 100):
    memories = get_memory_service().list_memories(limit=limit)
    return {
        "memories": [memory.to_dict() for memory in memories],
        "count": len(memories),
    }


@app.post("/memory")
def memory_create(request: MemoryCreateRequest):
    try:
        memory, created = get_memory_service().remember(
            request.content,
            category=request.category,
            importance=request.importance,
            is_pinned=request.is_pinned,
        )
    except MemoryValidationError as exc:
        return {"success": False, "error": str(exc)}
    return {
        "success": True,
        "created": created,
        "memory": memory.to_dict(),
    }


@app.patch("/memory/{memory_id}")
def memory_update(memory_id: int, request: MemoryUpdateRequest):
    try:
        memory = get_memory_service().update(
            memory_id,
            request.content,
            category=request.category,
            importance=request.importance,
            is_pinned=request.is_pinned,
        )
    except MemoryValidationError as exc:
        return {"success": False, "error": str(exc)}
    if memory is None:
        return {"success": False, "error": "Memory not found."}
    return {"success": True, "memory": memory.to_dict()}


@app.delete("/memory/{memory_id}")
def memory_delete(memory_id: int):
    deleted = get_memory_service().forget(memory_id)
    return {"success": deleted}


@app.get("/context")
def context_status(session_id: str = "default"):
    conversation = get_conversation_context().snapshot(session_id)
    pending = get_pending_action_store().snapshot(session_id)
    return {
        "session_id": session_id,
        "conversation": conversation,
        **pending,
    }


@app.delete("/context")
def context_clear(session_id: str = "default"):
    turns_removed = get_conversation_context().clear(session_id)
    pending_removed = get_pending_action_store().clear(session_id)
    return {
        "success": True,
        "session_id": session_id,
        "turns_removed": turns_removed,
        "pending_action_removed": pending_removed,
    }


@app.get("/workflows")
def workflow_list(session_id: str = "default", limit: int = 20):
    workflows = get_workflow_store().list_recent(session_id, limit=limit)
    return {
        "session_id": session_id,
        "workflows": [workflow.to_dict() for workflow in workflows],
        "count": len(workflows),
    }


@app.get("/workflows/{workflow_id}")
def workflow_detail(workflow_id: str):
    workflow = get_workflow_store().get(workflow_id)
    if workflow is None:
        return {"success": False, "error": "Workflow not found."}
    return {
        "success": True,
        "workflow": workflow.to_dict(),
        "steps": get_workflow_store().steps(workflow_id),
    }


@app.get("/episodes")
def episode_list(limit: int = 50):
    episodes = get_episodic_memory_service().list_recent(limit=limit)
    return {"episodes": episodes, "count": len(episodes)}


@app.get("/gmail/health")
async def gmail_health_check():
    return await asyncio.to_thread(gmail_health)


@app.post("/gmail/confirm")
async def gmail_confirm(request: GmailConfirmationRequest):
    return await asyncio.to_thread(
        handle_gmail_confirmation,
        request.token,
        request.confirmed,
    )


@app.post("/command")
async def handle_command(request: CommandRequest):
    command = request.command.strip()
    if not command:
        return {
            "response": "Tell me what you want me to do.",
            "requires_confirmation": False,
            "type": "error",
        }

    try:
        result = await asyncio.to_thread(
            handle_ai_command,
            command,
            request.session_id,
        )
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
