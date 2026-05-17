from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> None:
    project_root = _project_root()
    python_candidates = [
        project_root / ".venv" / "Scripts" / "pythonw.exe",
        project_root / ".venv" / "Scripts" / "python.exe",
    ]

    python_executable = next((candidate for candidate in python_candidates if candidate.exists()), None)
    if python_executable is None:
        raise SystemExit("Trackerblox launcher could not find .venv\\Scripts\\pythonw.exe or python.exe")

    startup_info = None
    creation_flags = 0
    if sys.platform == "win32":
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creation_flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    subprocess.Popen(
        [str(python_executable), "-m", "trackerblox"],
        cwd=project_root,
        startupinfo=startup_info,
        creationflags=creation_flags,
    )


if __name__ == "__main__":
    main()
