import os
import signal
import sys

from eye.pid import read_pid, remove_pid, write_pid


def cmd_start(test: bool = False) -> None:
    if read_pid() is not None:
        print("[eye] Already running. Use `eye stop` to stop it.", file=sys.stderr)
        sys.exit(1)

    write_pid()
    try:
        from eye.timer import run
        run(test=test)
    except SystemExit:
        raise
    finally:
        remove_pid()


def cmd_stop() -> None:
    pid = read_pid()
    if pid is None:
        print("[eye] Not running.", file=sys.stderr)
        sys.exit(1)

    os.kill(pid, signal.SIGTERM)
    remove_pid()
    print("[eye] Stopped.")


def cmd_skip() -> None:
    pid = read_pid()
    if pid is None:
        print("[eye] Not running.")
        sys.exit(0)

    os.kill(pid, signal.SIGUSR1)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else None

    if cmd == "start":
        cmd_start(test="--test" in sys.argv)
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "skip":
        cmd_skip()
    else:
        print("Usage: eye <start|stop|skip>", file=sys.stderr)
        sys.exit(1)
