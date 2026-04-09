import os
from pathlib import Path

PID_FILE = Path.home() / ".eye.pid"


def write_pid(path: Path = PID_FILE) -> None:
    path.write_text(str(os.getpid()))


def read_pid(path: Path = PID_FILE) -> int | None:
    try:
        pid = int(path.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None

    try:
        os.kill(pid, 0)  # check process exists
        return pid
    except ProcessLookupError:
        path.unlink(missing_ok=True)
        return None
    except PermissionError:
        return pid  # process exists but owned by another user


def remove_pid(path: Path = PID_FILE) -> None:
    path.unlink(missing_ok=True)
