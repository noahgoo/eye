import signal
import threading

import eye.overlay as overlay
from eye.pid import remove_pid

WORK_MINUTES = 20
BREAK_SECONDS = 20


def run(test: bool = False) -> None:
    stop_event = threading.Event()

    def handle_sigterm(signum, frame):
        stop_event.set()
        # If an overlay is showing, dismiss it so the main thread unblocks
        if overlay._active_root is not None and overlay._active_dismiss is not None:
            overlay._active_root.after(0, overlay._active_dismiss)

    def handle_sigusr1(signum, frame):
        if overlay._active_root is not None and overlay._active_dismiss is not None:
            overlay._active_root.after(0, overlay._active_dismiss)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGUSR1, handle_sigusr1)

    work_seconds = 10 if test else WORK_MINUTES * 60
    break_seconds = 5 if test else BREAK_SECONDS
    label = "10 seconds" if test else f"{WORK_MINUTES} minutes"

    try:
        first = True
        while not stop_event.is_set():
            if first:
                print(f"[eye] Started. Break in {label}.", flush=True)
                first = False
            else:
                print(f"[eye] Break over. Next break in {label}.", flush=True)

            stop_event.wait(timeout=work_seconds)

            if stop_event.is_set():
                break

            print("[eye] Time for a break!", flush=True)
            overlay.show_overlay(break_seconds=break_seconds)

    finally:
        remove_pid()
        print("[eye] Stopped.", flush=True)
