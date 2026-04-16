"""Entry point for Eye.app bundle. Auto-starts the 20-min timer on launch."""
import signal
import sys
import threading

import AppKit  # type: ignore[attr-defined]
from PyObjCTools import AppHelper

import eye.overlay as overlay
from eye.pid import read_pid, write_pid, remove_pid


class _EyeDelegate(AppKit.NSObject):  # type: ignore[attr-defined]
    def applicationDidFinishLaunching_(self, notification):
        t = threading.Thread(target=_timer_thread, daemon=True)
        t.start()

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return False


def _timer_thread() -> None:
    """20-min break loop — runs on a background thread."""
    test = "--test" in sys.argv
    work_seconds = 15 if test else 20 * 60
    break_seconds = 10 if test else 20
    label = "15 seconds" if test else "20 minutes"

    stop = threading.Event()

    first = True
    while not stop.is_set():
        if first:
            print(f"[eye] Started. Break in {label}.", flush=True)
            first = False
        else:
            print(f"[eye] Break over. Next break in {label}.", flush=True)

        stop.wait(timeout=work_seconds)
        if stop.is_set():
            break

        print("[eye] Time for a break!", flush=True)
        done = threading.Event()
        # Dispatch show_overlay to the main thread (AppKit must run on main thread).
        # callAfter is thread-safe; done.wait() blocks until on_dismiss fires.
        AppHelper.callAfter(overlay.show_overlay, done.set, break_seconds)
        done.wait()

    print("[eye] Stopped.", flush=True)


def main() -> None:
    if read_pid() is not None:
        sys.exit(0)  # Another instance already running

    write_pid()
    try:
        app = AppKit.NSApplication.sharedApplication()  # type: ignore[attr-defined]
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)  # type: ignore[attr-defined]

        delegate = _EyeDelegate.alloc().init()
        app.setDelegate_(delegate)

        # Signal handlers must be set on the main thread.
        def _stop(signum, frame):
            if overlay._active_dismiss:
                overlay._active_dismiss()
            AppHelper.stopEventLoop()

        def _skip(signum, frame):
            if overlay._active_dismiss:
                overlay._active_dismiss()

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGUSR1, _skip)

        # runEventLoop calls NSApplicationMain → finishLaunching → NSApp.run().
        # Properly initialises the full AppKit event loop.
        AppHelper.runEventLoop()
    finally:
        remove_pid()


if __name__ == "__main__":
    main()
