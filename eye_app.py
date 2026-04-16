"""Entry point for Eye.app bundle. Menu bar icon controls the 20/20/20 timer."""
import signal
import sys
import threading

import AppKit  # type: ignore[attr-defined]
from PyObjCTools import AppHelper

import eye.overlay as overlay
from eye.pid import read_pid, write_pid, remove_pid


def _run_timer(stop_event: threading.Event, test: bool, on_done) -> None:
    """Break loop — runs on a background thread. Calls on_done() when it exits."""
    work_seconds = 15 if test else 20 * 60
    break_seconds = 10 if test else 20
    label = "15 seconds" if test else "20 minutes"

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
        done = threading.Event()
        AppHelper.callAfter(overlay.show_overlay, done.set, break_seconds)
        done.wait()

    print("[eye] Stopped.", flush=True)
    AppHelper.callAfter(on_done)


class _EyeDelegate(AppKit.NSObject):  # type: ignore[attr-defined]
    _stop_event = None
    _timer_thread = None

    def applicationDidFinishLaunching_(self, notification):
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        self._setup_menubar()

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return False

    # ------------------------------------------------------------------
    # Menu bar setup
    # ------------------------------------------------------------------

    def _setup_menubar(self):
        self._status_item = (
            AppKit.NSStatusBar.systemStatusBar()
            .statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        )
        image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "eye.half.closed", "Eye"
        )
        image.setTemplate_(True)  # adapts to light/dark menu bar
        self._status_item.button().setImage_(image)

        menu = AppKit.NSMenu.alloc().init()

        self._status_label = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Eye: Stopped", None, ""
        )
        self._status_label.setEnabled_(False)
        menu.addItem_(self._status_label)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        self._start_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Start", b"startTimer:", ""
        )
        self._start_item.setTarget_(self)
        menu.addItem_(self._start_item)

        self._start_test_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Start (Test Mode)", b"startTimerTest:", ""
        )
        self._start_test_item.setTarget_(self)
        menu.addItem_(self._start_test_item)

        self._stop_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Stop", b"stopTimer:", ""
        )
        self._stop_item.setTarget_(self)
        menu.addItem_(self._stop_item)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", b"quitApp:", "q"
        )
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        self._status_item.setMenu_(menu)
        self._update_menu(running=False)

    def _update_menu(self, running: bool) -> None:
        self._status_label.setTitle_("Eye: Running" if running else "Eye: Stopped")
        self._start_item.setEnabled_(not running)
        self._start_test_item.setEnabled_(not running)
        self._stop_item.setEnabled_(running)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def startTimer_(self, sender) -> None:
        if self._timer_thread and self._timer_thread.is_alive():
            return
        self._stop_event = threading.Event()
        self._timer_thread = threading.Thread(
            target=_run_timer,
            args=(self._stop_event, False, lambda: self._update_menu(running=False)),
            daemon=True,
        )
        self._timer_thread.start()
        self._update_menu(running=True)

    def startTimerTest_(self, sender) -> None:
        if self._timer_thread and self._timer_thread.is_alive():
            return
        self._stop_event = threading.Event()
        self._timer_thread = threading.Thread(
            target=_run_timer,
            args=(self._stop_event, True, lambda: self._update_menu(running=False)),
            daemon=True,
        )
        self._timer_thread.start()
        self._update_menu(running=True)

    def stopTimer_(self, sender) -> None:
        if self._stop_event:
            self._stop_event.set()
        if overlay._active_dismiss:
            overlay._active_dismiss()
        self._update_menu(running=False)

    def quitApp_(self, sender) -> None:
        if self._stop_event:
            self._stop_event.set()
        if overlay._active_dismiss:
            overlay._active_dismiss()
        AppHelper.stopEventLoop()


def main() -> None:
    if read_pid() is not None:
        sys.exit(0)  # Another instance already running

    write_pid()
    try:
        app = AppKit.NSApplication.sharedApplication()  # type: ignore[attr-defined]

        delegate = _EyeDelegate.alloc().init()
        app.setDelegate_(delegate)

        def _stop(signum, frame):
            if overlay._active_dismiss:
                overlay._active_dismiss()
            AppHelper.stopEventLoop()

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        AppHelper.runEventLoop()
    finally:
        remove_pid()


if __name__ == "__main__":
    main()
