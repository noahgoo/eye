"""Entry point for Eye.app bundle. Menu bar icon controls the 20/20/20 timer."""
import signal
import sys
import threading
import time

import AppKit  # type: ignore[attr-defined]
import Foundation  # type: ignore[attr-defined]
import Quartz  # type: ignore[attr-defined]
from PyObjCTools import AppHelper

import eye.overlay as overlay
from eye.pid import read_pid, write_pid, remove_pid

IDLE_THRESHOLD = 5 * 60  # seconds of inactivity before pausing timer


def _idle_seconds() -> float:
    return Quartz.CGEventSourceSecondsSinceLastEventType(
        Quartz.kCGEventSourceStateCombinedSessionState,
        Quartz.kCGAnyInputEventType,
    )


# Module-level callbacks avoid PyObjC BadPrototypeError on NSObject subclass methods
# with extra positional args.
def _on_pause_cb(delegate) -> None:
    delegate._paused_status = "Paused (inactive)"


def _on_resume_cb(delegate) -> None:
    delegate._paused_status = None


def _run_timer(
    stop_event: threading.Event,
    sleep_event: threading.Event,
    reset_event: threading.Event,
    test: bool,
    on_cycle_start,
    on_pause,
    on_resume,
    on_done,
    remaining_ref: list,
) -> None:
    """Break loop — runs on a background thread. Pauses during sleep or inactivity."""
    work_seconds = 15 if test else 20 * 60
    break_seconds = 10 if test else 20
    label = "15 seconds" if test else "20 minutes"

    first = True
    while not stop_event.is_set():
        AppHelper.callAfter(on_cycle_start)
        if first:
            print(f"[eye] Started. Break in {label}.", flush=True)
            first = False
        else:
            print(f"[eye] Break over. Next break in {label}.", flush=True)

        remaining = float(work_seconds)
        remaining_ref[0] = remaining
        was_paused = False
        while remaining > 0 and not stop_event.is_set():
            if reset_event.is_set():
                reset_event.clear()
                remaining = float(work_seconds)
                remaining_ref[0] = remaining
                was_paused = False
                AppHelper.callAfter(on_cycle_start)
                print(f"[eye] Woke from sleep — timer reset. Break in {label}.", flush=True)
            paused = sleep_event.is_set() or _idle_seconds() >= IDLE_THRESHOLD
            if paused and not was_paused:
                was_paused = True
                AppHelper.callAfter(on_pause)
                print("[eye] Paused (inactive).", flush=True)
            elif not paused and was_paused:
                was_paused = False
                AppHelper.callAfter(on_resume)
                print(f"[eye] Resumed. {int(remaining)}s remaining.", flush=True)
            stop_event.wait(timeout=1.0)
            if not paused:
                remaining -= 1.0
                remaining_ref[0] = remaining

        if stop_event.is_set():
            break

        remaining_ref[0] = None  # on break
        print("[eye] Time for a break!", flush=True)
        done = threading.Event()
        AppHelper.callAfter(overlay.show_overlay, done.set, break_seconds)
        done.wait()

    remaining_ref[0] = None
    print("[eye] Stopped.", flush=True)
    AppHelper.callAfter(on_done)


def _start_timer(delegate, test: bool) -> None:
    if delegate._timer_thread and delegate._timer_thread.is_alive():
        return
    delegate._stop_event = threading.Event()
    delegate._sleep_event = threading.Event()
    delegate._reset_event = threading.Event()
    delegate._remaining_ref = [None]
    delegate._timer_thread = threading.Thread(
        target=_run_timer,
        args=(
            delegate._stop_event,
            delegate._sleep_event,
            delegate._reset_event,
            test,
            delegate._on_cycle_start,
            lambda: _on_pause_cb(delegate),
            lambda: _on_resume_cb(delegate),
            lambda: delegate._update_menu(running=False),
            delegate._remaining_ref,
        ),
        daemon=True,
    )
    delegate._timer_thread.start()
    delegate._tick_timer = Foundation.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0, delegate, b"tickCountdown:", None, True
    )
    Foundation.NSRunLoop.mainRunLoop().addTimer_forMode_(
        delegate._tick_timer, Foundation.NSRunLoopCommonModes
    )
    delegate._update_menu(running=True)


class _EyeDelegate(AppKit.NSObject):  # type: ignore[attr-defined]
    _stop_event = None
    _sleep_event = None
    _reset_event = None
    _timer_thread = None
    _tick_timer = None
    _remaining_ref = None  # [float|None] written by timer thread, read by main thread
    _work_seconds = None
    _paused_status = None

    def applicationDidFinishLaunching_(self, notification):
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        self._setup_menubar()

        ws = AppKit.NSWorkspace.sharedWorkspace()
        nc = ws.notificationCenter()
        nc.addObserver_selector_name_object_(
            self, b"onSleep:", AppKit.NSWorkspaceWillSleepNotification, None
        )
        nc.addObserver_selector_name_object_(
            self, b"onWake:", AppKit.NSWorkspaceDidWakeNotification, None
        )

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return False

    # ------------------------------------------------------------------
    # Sleep / wake handlers
    # ------------------------------------------------------------------

    def onSleep_(self, notification) -> None:
        if self._sleep_event:
            self._sleep_event.set()

    def onWake_(self, notification) -> None:
        if self._sleep_event:
            self._sleep_event.clear()
        if self._reset_event:
            self._reset_event.set()

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

        self._countdown_label = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "", None, ""
        )
        self._countdown_label.setEnabled_(False)
        self._countdown_label.setHidden_(True)
        menu.addItem_(self._countdown_label)

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
        symbol = "eye" if running else "eye.half.closed"
        image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, "Eye")
        image.setTemplate_(True)
        self._status_item.button().setImage_(image)
        self._status_label.setTitle_("Eye: Running" if running else "Eye: Stopped")
        self._countdown_label.setHidden_(not running)
        self._start_item.setEnabled_(not running)
        self._start_test_item.setEnabled_(not running)
        self._stop_item.setEnabled_(running)
        if not running:
            if self._tick_timer:
                self._tick_timer.invalidate()
                self._tick_timer = None
            self._paused_status = None

    # ------------------------------------------------------------------
    # Countdown tick (called by NSTimer every second on main thread)
    # ------------------------------------------------------------------

    def tickCountdown_(self, timer) -> None:
        if overlay._active_dismiss is not None:
            self._countdown_label.setTitle_("On break...")
            return
        if self._paused_status is not None:
            self._countdown_label.setTitle_(self._paused_status)
            return
        remaining = self._remaining_ref[0] if self._remaining_ref else None
        if remaining is None:
            return
        mins = int(remaining) // 60
        secs = int(remaining) % 60
        self._countdown_label.setTitle_(f"Next break in {mins}:{secs:02d}")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_cycle_start(self) -> None:
        self._paused_status = None

    def startTimer_(self, sender) -> None:
        _start_timer(self, test=False)

    def startTimerTest_(self, sender) -> None:
        _start_timer(self, test=True)

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
