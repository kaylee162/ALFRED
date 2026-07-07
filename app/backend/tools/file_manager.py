from pathlib import Path
from datetime import datetime, timedelta
import os
import shutil

SAFE_ROOTS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "src",
    Path.home() / "source",
]

TEXT_EXTENSIONS = [".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".csv", ".html", ".css"]
IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp"]
SCREENSHOT_KEYWORDS = ["screenshot", "screen shot"]


def existing_safe_roots():
    return [root for root in SAFE_ROOTS if root.exists() and root.is_dir()]


def is_safe_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        return any(
            resolved == root.resolve() or resolved.is_relative_to(root.resolve())
            for root in existing_safe_roots()
        )
    except Exception:
        return False


def search_files(query: str, limit: int = 25, include_folders: bool = True):
    query = query.lower().strip()
    matches = []

    for root in existing_safe_roots():
        for path in root.rglob("*"):
            if len(matches) >= limit:
                return {"success": True, "items": matches}

            if not include_folders and path.is_dir():
                continue

            if query in path.name.lower():
                matches.append({
                    "name": path.name,
                    "path": str(path),
                    "type": "folder" if path.is_dir() else "file",
                    "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                })

    return {"success": True, "items": matches}


def list_folder(path: str | None = None):
    target = Path(path) if path else Path.home() / "Downloads"

    if not target.exists():
        return {"success": False, "message": f"I couldn't find: {target}", "items": []}

    if not target.is_dir():
        return {"success": False, "message": "That path is not a folder.", "items": []}

    if not is_safe_path(target):
        return {"success": False, "message": "That folder is outside my allowed folders.", "items": []}

    items = []

    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name.startswith("."):
            continue

        items.append({
            "name": child.name,
            "path": str(child),
            "type": "folder" if child.is_dir() else "file",
            "modified": datetime.fromtimestamp(child.stat().st_mtime).isoformat(),
        })

    return {
        "success": True,
        "message": f"Showing {target.name}",
        "current_path": str(target),
        "parent_path": str(target.parent) if is_safe_path(target.parent) else None,
        "items": items,
    }


def recent_downloads(days: int = 7, limit: int = 25):
    downloads = Path.home() / "Downloads"
    cutoff = datetime.now() - timedelta(days=days)

    if not downloads.exists():
        return {"success": False, "message": "Downloads folder not found.", "items": []}

    files = []

    for path in downloads.iterdir():
        modified = datetime.fromtimestamp(path.stat().st_mtime)

        if modified >= cutoff:
            files.append({
                "name": path.name,
                "path": str(path),
                "type": "folder" if path.is_dir() else "file",
                "modified": modified.isoformat(),
            })

    files.sort(key=lambda item: item["modified"], reverse=True)

    return {
        "success": True,
        "message": f"Found {len(files[:limit])} recent download(s).",
        "items": files[:limit],
    }


def read_text_file(path: str, max_chars: int = 6000):
    target = Path(path)

    if not target.exists():
        return {"success": False, "message": "I couldn't find that file."}

    if not target.is_file():
        return {"success": False, "message": "That is not a file."}

    if not is_safe_path(target):
        return {"success": False, "message": "That file is outside my allowed folders."}

    if target.suffix.lower() not in TEXT_EXTENSIONS:
        return {"success": False, "message": "I can only read text-based files right now."}

    text = target.read_text(errors="ignore")[:max_chars]

    return {
        "success": True,
        "name": target.name,
        "path": str(target),
        "content": text,
    }


def open_path(path: str):
    target = Path(path)

    if not target.exists():
        return {"success": False, "message": f"I couldn't find: {path}"}

    if not is_safe_path(target):
        return {"success": False, "message": "That path is outside my allowed folders."}

    os.startfile(target)

    return {"success": True, "message": f"Opening {target.name}."}