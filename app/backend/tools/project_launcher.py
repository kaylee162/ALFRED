from __future__ import annotations

from pathlib import Path
import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess

PROJECT_ROOTS = [
    Path.home() / "src",
    Path.home() / "source",
]

ROOT_ALIASES = {"src", "source", "projects", "project", "project root"}


def get_project_roots() -> list[Path]:
    return [root for root in PROJECT_ROOTS if root.exists() and root.is_dir()]


def get_default_project_root() -> Path:
    roots = get_project_roots()
    if not roots:
        return PROJECT_ROOTS[0]

    for root in roots:
        try:
            if any(root.iterdir()):
                return root
        except OSError:
            continue
    return roots[0]


def is_safe_project_path(path: Path) -> bool:
    try:
        resolved = path.expanduser().resolve()
        return any(
            resolved == root.resolve() or resolved.is_relative_to(root.resolve())
            for root in get_project_roots()
        )
    except (OSError, RuntimeError):
        return False


def resolve_project_path(path: str | None) -> Path:
    """Resolve an absolute path, root alias, relative path, or project name."""
    if path is None or not str(path).strip():
        return get_default_project_root()

    raw = str(path).strip().strip('"').strip("'")
    candidate = Path(raw).expanduser()

    if candidate.is_absolute():
        return candidate

    lowered = raw.lower().replace("\\", "/").strip("/")
    if lowered in ROOT_ALIASES:
        return get_default_project_root()

    parts = Path(raw.replace("/", "\\")).parts
    if parts and parts[0].lower() in {"src", "source"}:
        matching_root = next(
            (root for root in PROJECT_ROOTS if root.name.lower() == parts[0].lower()),
            get_default_project_root(),
        )
        return matching_root.joinpath(*parts[1:])

    direct_matches = [root / raw for root in get_project_roots()]
    for match in direct_matches:
        if match.exists():
            return match

    # Case-insensitive project-name lookup, useful for Ollama-generated names.
    for root in get_project_roots():
        try:
            for child in root.iterdir():
                if child.is_dir() and child.name.lower() == lowered:
                    return child
        except OSError:
            continue

    return get_default_project_root() / raw


def list_project_folder(path: str | None = None):
    target = resolve_project_path(path)

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

    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        return {"success": False, "message": f"I couldn't read that project folder: {exc}", "items": []}

    items = []
    for child in children:
        if child.name.startswith("."):
            continue
        items.append({
            "name": child.name,
            "path": str(child),
            "type": "folder" if child.is_dir() else "file",
            "can_open": True,
        })

    roots = get_project_roots()
    default_root = get_default_project_root()
    return {
        "success": True,
        "message": f"Showing {target.name}",
        "root": str(default_root),
        "roots": [str(root) for root in roots],
        "current_path": str(target),
        "parent_path": str(target.parent) if is_safe_project_path(target.parent) else None,
        "items": items,
    }


def _is_allowed_open_path(path: Path) -> bool:
    """Allow opening items only inside ALFRED's approved user folders."""
    allowed_roots = [
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "Documents",
        Path.home() / "src",
        Path.home() / "source",
    ]

    try:
        resolved = path.expanduser().resolve()
        return any(
            root.exists()
            and (resolved == root.resolve() or resolved.is_relative_to(root.resolve()))
            for root in allowed_roots
        )
    except (OSError, RuntimeError):
        return False


def open_project_path(path: str):
    """Open a folder in Explorer or show Windows Open With for a file.

    The function name is retained so the existing /projects/open endpoint does
    not need to change.
    """
    target = Path(str(path or "").strip().strip('"').strip("'")).expanduser()

    if not target.is_absolute():
        target = resolve_project_path(str(path))

    if not target.exists():
        return {"success": False, "message": f"Path does not exist: {target}"}
    if not _is_allowed_open_path(target):
        return {"success": False, "message": "That item is outside ALFRED's allowed folders."}
    if os.name != "nt":
        return {"success": False, "message": "Windows Open With is only available on Windows."}

    try:
        if target.is_dir():
            subprocess.Popen(
                ["explorer.exe", str(target)],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"success": True, "message": f"Opening {target.name} in File Explorer."}

        class OPENASINFO(ctypes.Structure):
            _fields_ = [
                ("pcszFile", wintypes.LPCWSTR),
                ("pcszClass", wintypes.LPCWSTR),
                ("oaifInFlags", wintypes.DWORD),
            ]

        # Use Windows' dedicated Open With API instead of ShellExecute's
        # unreliable `openas` verb. OAIF_EXEC opens the selected application
        # after the user chooses it.
        OAIF_EXEC = 0x00000004

        open_as_info = OPENASINFO(
            pcszFile=str(target),
            pcszClass=None,
            oaifInFlags=OAIF_EXEC,
        )

        sh_open_with_dialog = ctypes.windll.shell32.SHOpenWithDialog
        sh_open_with_dialog.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(OPENASINFO),
        ]
        sh_open_with_dialog.restype = ctypes.c_long

        hresult = sh_open_with_dialog(None, ctypes.byref(open_as_info))

        if hresult != 0:
            # Keep a practical fallback for unusual Windows shell setups.
            subprocess.Popen(
                [
                    "rundll32.exe",
                    "shell32.dll,OpenAs_RunDLL",
                    str(target),
                ],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        return {
            "success": True,
            "message": f"Choose an application to open {target.name}.",
        }
    except OSError as exc:
        return {"success": False, "message": f"I couldn't open {target.name}: {exc}"}



def open_project_in_vscode(path: str):
    """Open a project folder under src/source in Visual Studio Code."""
    target = resolve_project_path(path)

    if not target.exists():
        return {"success": False, "message": f"Project folder does not exist: {target}"}

    if not target.is_dir():
        return {"success": False, "message": "Only project folders can be opened in VS Code."}

    if not is_safe_project_path(target):
        return {
            "success": False,
            "message": "VS Code is only available for folders inside your src or source project directory.",
        }

    code_command = shutil.which("code") or shutil.which("code.cmd")

    if not code_command:
        return {
            "success": False,
            "message": (
                "VS Code's 'code' command is not available. "
                "In VS Code, run 'Shell Command: Install code command in PATH', "
                "then restart ALFRED."
            ),
        }

    try:
        subprocess.Popen(
            [code_command, str(target)],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "success": True,
            "message": f"Opening {target.name} in VS Code.",
        }
    except OSError as exc:
        return {
            "success": False,
            "message": f"I couldn't open {target.name} in VS Code: {exc}",
        }



def open_project(command: str):
    command = command.lower().strip()
    if any(phrase in command for phrase in ("show me my projects", "show projects", "my projects", "project explorer")):
        return list_project_folder()
    return {"success": False, "message": 'Try saying: "show me my projects"'}