import threading
from typing import Callable

import AppKit
import Foundation
from PyObjCTools import AppHelper

BG_COLOR = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.051, 0.051, 0.051, 1.0)


class _OverlayWindow(AppKit.NSWindow):
    _dismiss_callback = None

    def canBecomeKeyWindow(self) -> bool:
        return True

    def canBecomeMainWindow(self) -> bool:
        return True

    def skipBreak_(self, sender) -> None:
        if self._dismiss_callback:
            self._dismiss_callback()


def _rounded_font(size: float, weight: float) -> AppKit.NSFont:
    base = AppKit.NSFont.systemFontOfSize_weight_(size, weight)
    desc = base.fontDescriptor().fontDescriptorWithDesign_(
        AppKit.NSFontDescriptorSystemDesignRounded
    )
    font = AppKit.NSFont.fontWithDescriptor_size_(desc, size)
    return font if font is not None else base


def _attributed_label(attr: Foundation.NSAttributedString) -> AppKit.NSTextField:
    field = AppKit.NSTextField.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, 1, 1))
    field.setAttributedStringValue_(attr)
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

    title_color = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.90, 0.89, 0.86, 1.0)
    subtitle_color = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.62, 0.62, 0.60, 1.0)
    skip_color = AppKit.NSColor.colorWithRed_green_blue_alpha_(0.48, 0.48, 0.46, 1.0)

    title_font = _rounded_font(50.0, AppKit.NSFontWeightMedium)
    subtitle_font = _rounded_font(24.0, AppKit.NSFontWeightRegular)
    skip_font = _rounded_font(13.0, AppKit.NSFontWeightRegular)

    title_attr = Foundation.NSMutableAttributedString.alloc().initWithString_attributes_(
        "Look away",
        {
            AppKit.NSFontAttributeName: title_font,
            AppKit.NSForegroundColorAttributeName: title_color,
        },
    )
    title = _attributed_label(title_attr)

    subtitle_attr = Foundation.NSMutableAttributedString.alloc().initWithString_attributes_(
        "20 feet away for 20 seconds",
        {
            AppKit.NSFontAttributeName: subtitle_font,
            AppKit.NSForegroundColorAttributeName: subtitle_color,
            AppKit.NSKernAttributeName: 0.45,
        },
    )
    subtitle = _attributed_label(subtitle_attr)

    label_gap = 22.0
    subtitle_to_skip_gap = 56.0

    skip_attrs = {
        AppKit.NSForegroundColorAttributeName: skip_color,
        AppKit.NSFontAttributeName: skip_font,
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

    labels_height = title.frame().size.height + label_gap + subtitle.frame().size.height
    total_height = labels_height + subtitle_to_skip_gap + skip_btn.frame().size.height
    y = cy + total_height / 2

    for field, gap in [
        (title, label_gap),
        (subtitle, subtitle_to_skip_gap),
        (skip_btn, 0.0),
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
    # CanJoinAllSpaces: render in every Space.
    # FullScreenAuxiliary: required to appear inside another app's fullscreen Space;
    # CanJoinAllSpaces alone skips fullscreen Spaces owned by other apps.
    win.setCollectionBehavior_(
        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        | AppKit.NSWindowCollectionBehaviorIgnoresCycle
    )
    win.setAnimationBehavior_(AppKit.NSWindowAnimationBehaviorNone)
    win.setOpaque_(True)
    win.setReleasedWhenClosed_(False)
    return win


def show_overlay(on_dismiss: Callable[[], None] | None = None, break_seconds: int = 20) -> None:
    """Show a full-screen break overlay on all monitors. Returns immediately;
    cleanup and on_dismiss() fire when the overlay is dismissed."""
    dismissed = [False]
    windows: list[_OverlayWindow] = []
    auto_timer: list[threading.Timer | None] = [None]

    import eye.overlay as _self

    def dismiss() -> None:
        if dismissed[0]:
            return
        dismissed[0] = True
        if auto_timer[0]:
            auto_timer[0].cancel()
        for win in windows:
            win.orderOut_(None)
        _self._active_dismiss = None
        if on_dismiss:
            on_dismiss()

    for screen in AppKit.NSScreen.screens():
        win = _make_overlay_window(screen)
        win._dismiss_callback = dismiss
        _add_content(win)
        win.orderFrontRegardless()
        windows.append(win)

    _self._active_dismiss = dismiss

    auto_timer[0] = threading.Timer(break_seconds, lambda: AppHelper.callAfter(dismiss))
    auto_timer[0].daemon = True
    auto_timer[0].start()


# Exposed for the signal handler in timer.py
_active_dismiss: Callable[[], None] | None = None
