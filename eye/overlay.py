import threading
from typing import Callable

import AppKit
import Foundation
from PyObjCTools import AppHelper

BG_COLOR = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.051, 0.051, 0.051, 1.0)
FG_COLOR = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.941, 0.941, 0.941, 1.0)
FG_DIM_COLOR = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.533, 0.533, 0.533, 1.0)


class _OverlayWindow(AppKit.NSWindow):
    """Borderless window that can accept keyboard focus."""

    def canBecomeKeyWindow(self) -> bool:
        return True

    def canBecomeMainWindow(self) -> bool:
        return True


def _label(text: str, size: float, bold: bool = False, color=None) -> AppKit.NSTextField:
    if color is None:
        color = FG_COLOR
    field = AppKit.NSTextField.labelWithString_(text)
    font = AppKit.NSFont.boldSystemFontOfSize_(size) if bold else AppKit.NSFont.systemFontOfSize_(size)
    field.setFont_(font)
    field.setTextColor_(color)
    field.setBezeled_(False)
    field.setEditable_(False)
    field.setSelectable_(False)
    field.setDrawsBackground_(False)
    field.sizeToFit()
    return field


def _add_labels(win: AppKit.NSWindow) -> None:
    content = win.contentView()
    w = content.frame().size.width
    h = content.frame().size.height
    cx, cy = w / 2, h / 2

    items = [
        _label("Look away", 52, bold=True),
        _label("20 feet away for 20 seconds", 28),
        _label("Press Space or Esc to dismiss early, or run `eye skip`", 13, color=FG_DIM_COLOR),
    ]

    gap = 20.0
    total_height = sum(f.frame().size.height for f in items) + gap * (len(items) - 1)
    y = cy + total_height / 2

    for field in items:
        fw = field.frame().size.width
        fh = field.frame().size.height
        y -= fh
        field.setFrame_(Foundation.NSMakeRect(cx - fw / 2, y, fw, fh))
        content.addSubview_(field)
        y -= gap


def _make_overlay_window(screen: AppKit.NSScreen) -> _OverlayWindow:
    win = _OverlayWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        screen.frame(),
        AppKit.NSWindowStyleMaskBorderless,
        AppKit.NSBackingStoreBuffered,
        False,
    )
    win.setBackgroundColor_(BG_COLOR)
    win.setLevel_(AppKit.NSScreenSaverWindowLevel)
    win.setCollectionBehavior_(
        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | AppKit.NSWindowCollectionBehaviorStationary
        | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
    )
    win.setAnimationBehavior_(AppKit.NSWindowAnimationBehaviorNone)
    win.setOpaque_(True)
    win.setReleasedWhenClosed_(False)
    return win


def show_overlay(on_dismiss: Callable[[], None] | None = None, break_seconds: int = 20) -> None:
    """Show a full-screen break overlay on all monitors. Blocks until dismissed."""
    dismissed = [False]
    windows: list[_OverlayWindow] = []
    monitor_ref: list = [None]

    app = AppKit.NSApplication.sharedApplication()
    # Accessory: no Dock icon but can receive keyboard events
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    def dismiss() -> None:
        """
        Thread-safe dismiss: only calls AppHelper.stopEventLoop() which is safe
        from any thread. All AppKit cleanup happens on the main thread after
        runConsoleEventLoop() returns.
        """
        if dismissed[0]:
            return
        dismissed[0] = True
        AppHelper.stopEventLoop()

    for i, screen in enumerate(AppKit.NSScreen.screens()):
        win = _make_overlay_window(screen)
        if i == 0:
            _add_labels(win)
        win.makeKeyAndOrderFront_(None)
        windows.append(win)

    def _key_handler(event):
        if event.keyCode() in (49, 53):  # 49=space, 53=escape
            dismiss()
            return None
        return event

    monitor_ref[0] = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        AppKit.NSEventMaskKeyDown,
        _key_handler,
    )

    app.activateIgnoringOtherApps_(True)
    windows[0].makeKeyAndOrderFront_(None)

    # Expose for SIGUSR1 handler in timer.py
    import eye.overlay as _self
    _self._active_dismiss = dismiss

    auto_timer = threading.Timer(break_seconds, dismiss)
    auto_timer.daemon = True
    auto_timer.start()

    # runConsoleEventLoop is designed for CLI Python scripts that need Cocoa GUI.
    # installInterrupt=False so we don't clobber the SIGINT handler in timer.py.
    AppHelper.runConsoleEventLoop(installInterrupt=False)

    # --- Back on main thread; safe to do all AppKit cleanup here ---
    auto_timer.cancel()
    if monitor_ref[0] is not None:
        AppKit.NSEvent.removeMonitor_(monitor_ref[0])
        monitor_ref[0] = None
    for win in windows:
        win.orderOut_(None)

    _self._active_dismiss = None

    if on_dismiss:
        on_dismiss()


# Exposed for the signal handler in timer.py
_active_dismiss: Callable[[], None] | None = None
