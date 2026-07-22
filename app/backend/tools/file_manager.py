from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
from typing import Iterable

SAFE_ROOTS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "src",
    Path.home() / "source",
]

TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx",
    ".json", ".csv", ".html", ".css", ".yml", ".yaml", ".toml",
}

ROOT_ALIASES = {
    "desktop": Path.home() / "Desktop",
    "downloads": Path.home() / "Downloads",
    "download": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "document": Path.home() / "Documents",
    "src": Path.home() / "src",
    "source": Path.home() / "source",
    "projects": Path.home() / "src",
    "project": Path.home() / "src",
}


def existing_safe_roots() -> list[Path]:
    return [root for root in SAFE_ROOTS if root.exists() and root.is_dir()]


def is_safe_path(path: Path) -> bool:
    try:
        resolved = path.expanduser().resolve()
        return any(
            resolved == root.resolve() or resolved.is_relative_to(root.resolve())
            for root in existing_safe_roots()
        )
    except (OSError, RuntimeError):
        return False


def _first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def resolve_safe_path(path: str | None, *, default: Path | None = None) -> Path:
    """Resolve friendly names and relative paths inside ALFRED's safe roots."""
    if path is None or not str(path).strip():
        return default or Path.home() / "Downloads"

    raw = str(path).strip().strip('"').strip("'")
    normalized = raw.replace("/", os.sep).replace("\\", os.sep)
    alias_key = normalized.lower().strip(os.sep)

    if alias_key in ROOT_ALIASES:
        return ROOT_ALIASES[alias_key]

    candidate = Path(normalized).expanduser()
    if candidate.is_absolute():
        return candidate

    parts = candidate.parts
    if parts and parts[0].lower() in ROOT_ALIASES:
        return ROOT_ALIASES[parts[0].lower()].joinpath(*parts[1:])

    matches = [root / candidate for root in existing_safe_roots()]
    return _first_existing(matches) or ((default or Path.home() / "Downloads") / candidate)


def _item_payload(path: Path) -> dict:
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        modified = None

    return {
        "name": path.name,
        "path": str(path),
        "type": "folder" if path.is_dir() else "file",
        "modified": modified,
    }


def search_files(query: str, limit: int = 25, include_folders: bool = True):
    query = str(query or "").strip().lower()
    limit = max(1, min(int(limit or 25), 100))

    if not query:
        return {"success": False, "message": "Tell me what file or folder to search for.", "items": []}

    matches: list[dict] = []
    seen: set[str] = set()

    for root in existing_safe_roots():
        try:
            iterator = root.rglob("*")
            for path in iterator:
                if len(matches) >= limit:
                    return {"success": True, "message": f"Found {len(matches)} item(s).", "items": matches}
                try:
                    if not include_folders and path.is_dir():
                        continue
                    if query not in path.name.lower():
                        continue
                    key = str(path.resolve()).lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    matches.append(_item_payload(path))
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            continue

    return {
        "success": True,
        "message": f"Found {len(matches)} item(s).",
        "items": matches,
    }


def list_folder(path: str | None = None):
    target = resolve_safe_path(path, default=Path.home() / "Downloads")

    if not target.exists():
        return {"success": False, "message": f"I couldn't find: {target}", "items": []}
    if not target.is_dir():
        return {"success": False, "message": "That path is not a folder.", "items": []}
    if not is_safe_path(target):
        return {"success": False, "message": "That folder is outside my allowed folders.", "items": []}

    items = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except (OSError, PermissionError) as exc:
        return {"success": False, "message": f"I couldn't read that folder: {exc}", "items": []}

    for child in children:
        if child.name.startswith("."):
            continue
        items.append(_item_payload(child))

    return {
        "success": True,
        "message": f"Showing {target.name or target}",
        "current_path": str(target),
        "parent_path": str(target.parent) if is_safe_path(target.parent) else None,
        "items": items,
    }


def recent_downloads(days: int = 7, limit: int = 25):
    downloads = Path.home() / "Downloads"
    days = max(1, int(days or 7))
    limit = max(1, min(int(limit or 25), 100))
    cutoff = datetime.now() - timedelta(days=days)

    if not downloads.exists():
        return {"success": False, "message": "Downloads folder not found.", "items": []}

    files = []
    try:
        for path in downloads.iterdir():
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime)
                if modified >= cutoff:
                    files.append(_item_payload(path))
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError) as exc:
        return {"success": False, "message": f"I couldn't read Downloads: {exc}", "items": []}

    files.sort(key=lambda item: item.get("modified") or "", reverse=True)
    items = files[:limit]
    return {"success": True, "message": f"Found {len(items)} recent download(s).", "items": items}


def read_text_file(path: str, max_chars: int = 6000):
    target = resolve_safe_path(path)

    if not target.exists():
        return {"success": False, "message": f"I couldn't find: {target}"}
    if not target.is_file():
        return {"success": False, "message": "That is not a file."}
    if not is_safe_path(target):
        return {"success": False, "message": "That file is outside my allowed folders."}
    if target.suffix.lower() not in TEXT_EXTENSIONS:
        return {"success": False, "message": "I can only read text-based files right now."}

    try:
        text = target.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except OSError as exc:
        return {"success": False, "message": f"I couldn't read that file: {exc}"}

    return {"success": True, "name": target.name, "path": str(target), "content": text}


def open_path(path: str):
    target = resolve_safe_path(path)

    if not target.exists():
        return {"success": False, "message": f"I couldn't find: {target}"}
    if not is_safe_path(target):
        return {"success": False, "message": "That path is outside my allowed folders."}

    try:
        os.startfile(str(target))
    except OSError as exc:
        return {"success": False, "message": f"I couldn't open {target.name}: {exc}"}

    return {"success": True, "message": f"Opening {target.name}."}