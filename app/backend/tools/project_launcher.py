import subprocess
from pathlib import Path

PROJECT_ROOTS = [
    Path.home() / "src",
    Path.home() / "source",
]


def get_project_roots():
    return [root for root in PROJECT_ROOTS if root.exists() and root.is_dir()]


def get_default_project_root():
    roots = get_project_roots()

    if not roots:
        return PROJECT_ROOTS[0]

    roots_with_items = [root for root in roots if any(root.iterdir())]
    return roots_with_items[0] if roots_with_items else roots[0]


def is_safe_project_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        return any(
            resolved == root.resolve() or resolved.is_relative_to(root.resolve())
            for root in get_project_roots()
        )
    except Exception:
        return False


def list_project_folder(path: str | None = None):
    target = Path(path) if path else get_default_project_root()

    if not target.exists():
        return {
            "success": False,
            "message": f"Project folder not found: {target}",
            "items": [],
            "roots": [str(root) for root in PROJECT_ROOTS],
        }

    if not target.is_dir() or not is_safe_project_path(target):
        return {
            "success": False,
            "message": "That folder is outside the allowed project directories.",
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
        "message": f"Showing {target.name}",
        "root": str(get_default_project_root()),
        "roots": [str(root) for root in get_project_roots()],
        "current_path": str(target),
        "parent_path": str(target.parent) if target != get_default_project_root() else None,
        "items": items,
    }


def open_project_path(path: str):
    project_path = Path(path)

    if not project_path.exists():
        return {"success": False, "message": f"Folder does not exist: {project_path}"}

    if not project_path.is_dir():
        return {"success": False, "message": "Only folders can be opened as projects."}

    if not is_safe_project_path(project_path):
        return {"success": False, "message": "That folder is outside the allowed project directories."}

    subprocess.Popen(["code", str(project_path)], shell=True)

    return {
        "success": True,
        "message": f"Opening {project_path.name} in VS Code.",
    }


def open_project(command: str):
    command = command.lower()

    if any(phrase in command for phrase in ["show me my projects", "show projects", "my projects", "project explorer"]):
        return list_project_folder()

    return {
        "success": False,
        "message": 'Try saying: "show me my projects"',
    }