import threading
from typing import Callable

import AppKit
import Foundation
from PyObjCTools import AppHelper

BG_COLOR = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.051, 0.051, 0.051, 1.0)
FG_COLOR = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.941, 0.941, 0.941, 1.0)
FG_DIM_COLOR = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.533, 0.533, 0.533, 1.0)


class _OverlayWindow(AppKit.NSWindow):
    _dismiss_callback = None

    def canBecomeKeyWindow(self) -> bool:
        return True

    def canBecomeMainWindow(self) -> bool:
        return True

    def skipBreak_(self, sender) -> None:
        if self._dismiss_callback:
            self._dismiss_callback()


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


def _add_content(win: _OverlayWindow) -> None:
    content = win.contentView()
    w = content.frame().size.width
    h = content.frame().size.height
    cx, cy = w / 2, h / 2

    # --- Labels ---
    title = _label("Look away", 52, bold=True)
    subtitle = _label("20 feet away for 20 seconds", 28)

    label_gap = 20.0
    labels_height = title.frame().size.height + label_gap + subtitle.frame().size.height
    skip_gap = 48.0

    # --- Skip button ---
    skip_attrs = {
        AppKit.NSForegroundColorAttributeName: FG_DIM_COLOR,
        AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(13),
        AppKit.NSUnderlineStyleAttributeName: AppKit.NSUnderlineStyleSingle,
    }
    skip_title = Foundation.NSAttributedString.alloc().initWithString_attributes_(
        "press to skip", skip_attrs
    )
    skip_btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, 1, 1))
    skip_btn.setAttributedTitle_(skip_title)
    skip_btn.setBordered_(False)
    skip_btn.setTarget_(win)
    skip_btn.setAction_(b"skipBreak:")
    skip_btn.sizeToFit()

    total_height = labels_height + skip_gap + skip_btn.frame().size.height
    y = cy + total_height / 2

    for field, gap in [
        (title, label_gap),
        (subtitle, skip_gap),
        (skip_btn, 0),
    ]:
        fh = field.frame().size.height
        fw = field.frame().size.width
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
    key_monitor = None

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    app.activateIgnoringOtherApps_(True)

    def dismiss() -> None:
        if dismissed[0]:
            return
        dismissed[0] = True
        # callAfter ensures stopModal runs on the main thread — required by AppKit.
        # Safe from background timer thread, button click, key press, or signal.
        AppHelper.callAfter(app.stopModal)

    for i, screen in enumerate(AppKit.NSScreen.screens()):
        win = _make_overlay_window(screen)
        win._dismiss_callback = dismiss
        if i == 0:
            _add_content(win)
        win.makeKeyAndOrderFront_(None)
        windows.append(win)

    key_monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        AppKit.NSEventMaskKeyDown,
        lambda event: dismiss() or event,
    )

    import eye.overlay as _self
    _self._active_dismiss = dismiss

    auto_timer = threading.Timer(break_seconds, dismiss)
    auto_timer.daemon = True
    auto_timer.start()

    # runModalForWindow_ blocks within the existing event loop (unlike app.run()
    # which would stop the outer NSApplicationMain loop when stopped).
    # stopModal() only ends this modal session — outer loop is unaffected.
    app.runModalForWindow_(windows[0])

    auto_timer.cancel()
    if key_monitor is not None:
        AppKit.NSEvent.removeMonitor_(key_monitor)
    for win in windows:
        win.orderOut_(None)
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    _self._active_dismiss = None

    if on_dismiss:
        on_dismiss()


# Exposed for the signal handler in timer.py
_active_dismiss: Callable[[], None] | None = None
