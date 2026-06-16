from pathlib import Path
from datetime import datetime, timedelta
import os
import shutil

SAFE_ROOTS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
]

SCREENSHOT_KEYWORDS = ["screenshot", "screen shot"]
IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp"]


def is_safe_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        return any(resolved.is_relative_to(root.resolve()) for root in SAFE_ROOTS)
    except Exception:
        return False


def search_files(query: str, limit: int = 15):
    query = query.lower().strip()
    matches = []

    for root in SAFE_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if len(matches) >= limit:
                return matches

            if query in path.name.lower():
                matches.append({
                    "name": path.name,
                    "path": str(path),
                    "type": "folder" if path.is_dir() else "file"
                })

    return matches


def open_path(path: str):
    target = Path(path)

    if not target.exists():
        return {"success": False, "message": f"I couldn't find: {path}"}

    if not is_safe_path(target):
        return {"success": False, "message": "That path is outside my allowed folders."}

    os.startfile(target)
    return {"success": True, "message": f"Opening {target.name}."}


def create_folder(folder_path: str):
    target = Path(folder_path)

    if not is_safe_path(target.parent):
        return {"success": False, "message": "That folder location is outside my allowed folders."}

    target.mkdir(parents=True, exist_ok=True)

    return {
        "success": True,
        "message": f"Created folder: {target}"
    }


def preview_screenshot_cleanup(days: int = 7):
    cutoff = datetime.now() - timedelta(days=days)
    desktop = Path.home() / "Desktop"
    downloads = Path.home() / "Downloads"

    files = []

    for root in [desktop, downloads]:
        if not root.exists():
            continue

        for path in root.iterdir():
            if not path.is_file():
                continue

            name = path.name.lower()
            modified = datetime.fromtimestamp(path.stat().st_mtime)

            is_screenshot = (
                any(keyword in name for keyword in SCREENSHOT_KEYWORDS)
                and path.suffix.lower() in IMAGE_EXTENSIONS
                and modified >= cutoff
            )

            if is_screenshot:
                files.append(path)

    destination = desktop / "Screenshots"

    return {
        "files": [str(file) for file in files],
        "destination": str(destination),
        "count": len(files),
    }


def move_files(file_paths: list[str], destination: str):
    destination_path = Path(destination)

    if not is_safe_path(destination_path.parent):
        return {"success": False, "message": "Destination is outside my allowed folders."}

    destination_path.mkdir(parents=True, exist_ok=True)

    moved = []

    for file_path in file_paths:
        source = Path(file_path)

        if not source.exists() or not source.is_file():
            continue

        if not is_safe_path(source):
            continue

        target = destination_path / source.name

        counter = 1
        while target.exists():
            target = destination_path / f"{source.stem} ({counter}){source.suffix}"
            counter += 1

        shutil.move(str(source), str(target))
        moved.append(str(target))

    return {
        "success": True,
        "message": f"Moved {len(moved)} file(s) to {destination_path}.",
        "moved": moved,
    }


def rename_file(path: str, new_name: str):
    source = Path(path)

    if not source.exists():
        return {"success": False, "message": "I couldn't find that file."}

    if not is_safe_path(source):
        return {"success": False, "message": "That file is outside my allowed folders."}

    target = source.with_name(new_name)

    if target.exists():
        return {"success": False, "message": "A file with that name already exists."}

    source.rename(target)

    return {
        "success": True,
        "message": f"Renamed file to {target.name}.",
        "path": str(target),
    }