import subprocess
from pathlib import Path

SOURCE_ROOT = Path.home() / "src"


def is_safe_project_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        return resolved == SOURCE_ROOT.resolve() or resolved.is_relative_to(SOURCE_ROOT.resolve())
    except Exception:
        return False


def list_project_folder(path: str | None = None):
    target = Path(path) if path else SOURCE_ROOT

    if not target.exists():
        return {
            "success": False,
            "message": f"Source folder not found: {target}",
            "items": [],
        }

    if not target.is_dir() or not is_safe_project_path(target):
        return {
            "success": False,
            "message": "That folder is outside the allowed project directory.",
            "items": [],
        }

    items = []

    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name.startswith("."):
            continue

        items.append({
            "name": child.name,
            "path": str(child),
            "type": "folder" if child.is_dir() else "file",
            "can_open": child.is_dir(),
        })

    return {
        "success": True,
        "message": f"Showing {target.name if target != SOURCE_ROOT else 'source'}",
        "root": str(SOURCE_ROOT),
        "current_path": str(target),
        "parent_path": str(target.parent) if target != SOURCE_ROOT else None,
        "items": items,
    }


def open_project_path(path: str):
    project_path = Path(path)

    if not project_path.exists():
        return {"success": False, "message": f"Folder does not exist: {project_path}"}

    if not project_path.is_dir():
        return {"success": False, "message": "Only folders can be opened as projects."}

    if not is_safe_project_path(project_path):
        return {"success": False, "message": "That folder is outside the source directory."}

    subprocess.Popen(["code", str(project_path)], shell=True)

    return {
        "success": True,
        "message": f"Opening {project_path.name} in VS Code.",
    }


def open_project(command: str):
    command = command.lower()

    if "show me my projects" in command or "show projects" in command or "my projects" in command:
        return list_project_folder()

    return {
        "success": False,
        "message": 'Try saying: "show me my projects"',
    }