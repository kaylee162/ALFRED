from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from tools.project_launcher import open_project

app = FastAPI(title="ALFRED Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CommandRequest(BaseModel):
    command: str

@app.get("/")
def health_check():
    return {"status": "ALFRED backend is running"}

@app.post("/command")
def handle_command(request: CommandRequest):
    command = request.command.lower()

    if "open" in command:
        result = open_project(command)
        return {
            "response": result["message"],
            "requires_confirmation": False
        }

    return {
        "response": "I can help with that soon. Right now, I can open saved projects in VS Code.",
        "requires_confirmation": False
    }