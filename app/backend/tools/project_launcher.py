import subprocess
from pathlib import Path

PROJECTS = {
    "trailtales": r"C:\Users\alpha\source\react_apps\adventure-logger",
    "portfolio": r"C:\Users\alpha\source\portfolio\portfolio",
    "focus app": r"C:\Users\alpha\source\web_apps\focus-app",
}

def find_project(command: str):
    command = command.lower()

    for project_name, project_path in PROJECTS.items():
        if project_name in command:
            return project_name, Path(project_path)

    return None, None


def open_project(command: str):
    project_name, project_path = find_project(command)

    if not project_path:
        return {
            "success": False,
            "message": "I couldn't find a matching project. Try: TrailTales, portfolio, or focus app."
        }

    if not project_path.exists():
        return {
            "success": False,
            "message": f"I found {project_name}, but the folder path does not exist: {project_path}"
        }

    subprocess.Popen(["code", str(project_path)], shell=True)

    return {
        "success": True,
        "message": f"Opening {project_name} in VS Code."
    }