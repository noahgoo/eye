import threading
import time
from dataclasses import dataclass
from typing import Callable

import AppKit
import Foundation
from PyObjCTools import AppHelper


def _rgb(r: float, g: float, b: float) -> AppKit.NSColor:
    return AppKit.NSColor.colorWithRed_green_blue_alpha_(r, g, b, 1.0)


@dataclass(frozen=True)
class OverlayTheme:
    bg: AppKit.NSColor
    title: str
    subtitle: str
    title_color: AppKit.NSColor
    subtitle_color: AppKit.NSColor
    skip_color: AppKit.NSColor
    show_countdown: bool = False


EYE_THEME = OverlayTheme(
    bg=_rgb(0.051, 0.051, 0.051),
    title="Look away",
    subtitle="20 feet away for 20 seconds",
    title_color=_rgb(0.90, 0.89, 0.86),
    subtitle_color=_rgb(0.62, 0.62, 0.60),
    skip_color=_rgb(0.48, 0.48, 0.46),
)

POMODORO_THEME = OverlayTheme(
    bg=_rgb(0.059, 0.165, 0.114),  # ~#0F2A1D dark green
    title="Take a break",
    subtitle="Step away, stretch, grab some water",
    title_color=_rgb(0.90, 0.93, 0.88),
    subtitle_color=_rgb(0.62, 0.72, 0.64),
    skip_color=_rgb(0.45, 0.55, 0.48),
    show_countdown=True,
)


class _OverlayWindow(AppKit.NSWindow):
    _dismiss_callback = None

    def canBecomeKeyWindow(self) -> bool:
        return True

    def canBecomeMainWindow(self) -> bool:
        return True

    def skipBreak_(self, sender) -> None:
        if self._dismiss_callback:
            self._dismiss_callback()


class _CountdownTicker(AppKit.NSObject):
    """NSTimer target. Calls `_callback` once per tick on the main thread."""

    _callback = None

    def tick_(self, timer) -> None:
        if self._callback:
            self._callback()


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


def _format_countdown(seconds: float) -> str:
    s = max(0, int(seconds + 0.999))  # round up so "0:00" only shows at the very end
    return f"{s // 60}:{s % 60:02d}"


def _countdown_attr(text: str, theme: OverlayTheme) -> Foundation.NSAttributedString:
    font = AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(
        96.0, AppKit.NSFontWeightLight
    )
    para = AppKit.NSMutableParagraphStyle.alloc().init()
    para.setAlignment_(AppKit.NSTextAlignmentCenter)
    return Foundation.NSAttributedString.alloc().initWithString_attributes_(
        text,
        {
            AppKit.NSFontAttributeName: font,
            AppKit.NSForegroundColorAttributeName: theme.title_color,
            AppKit.NSParagraphStyleAttributeName: para,
        },
    )


def _add_content(
    win: _OverlayWindow, theme: OverlayTheme, break_seconds: int
) -> AppKit.NSTextField | None:
    """Lay out the overlay content. Returns the countdown label, if the theme has one."""
    content = win.contentView()
    w = content.frame().size.width
    h = content.frame().size.height
    cx, cy = w / 2, h / 2

    title_font = _rounded_font(50.0, AppKit.NSFontWeightMedium)
    subtitle_font = _rounded_font(24.0, AppKit.NSFontWeightRegular)
    skip_font = _rounded_font(13.0, AppKit.NSFontWeightRegular)

    title = _attributed_label(
        Foundation.NSMutableAttributedString.alloc().initWithString_attributes_(
            theme.title,
            {
                AppKit.NSFontAttributeName: title_font,
                AppKit.NSForegroundColorAttributeName: theme.title_color,
            },
        )
    )
    subtitle = _attributed_label(
        Foundation.NSMutableAttributedString.alloc().initWithString_attributes_(
            theme.subtitle,
            {
                AppKit.NSFontAttributeName: subtitle_font,
                AppKit.NSForegroundColorAttributeName: theme.subtitle_color,
                AppKit.NSKernAttributeName: 0.45,
            },
        )
    )

    countdown = None
    if theme.show_countdown:
        countdown = _attributed_label(
            _countdown_attr(_format_countdown(break_seconds), theme)
        )
        # Fixed width so changing digits never shift the layout.
        cf = countdown.frame()
        countdown.setFrame_(Foundation.NSMakeRect(0, 0, 420.0, cf.size.height))

    skip_title = Foundation.NSAttributedString.alloc().initWithString_attributes_(
        "press to skip",
        {
            AppKit.NSForegroundColorAttributeName: theme.skip_color,
            AppKit.NSFontAttributeName: skip_font,
            AppKit.NSUnderlineStyleAttributeName: AppKit.NSUnderlineStyleSingle,
        },
    )
    skip_btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, 1, 1))
    skip_btn.setAttributedTitle_(skip_title)
    skip_btn.setBordered_(False)
    skip_btn.setTarget_(win)
    skip_btn.setAction_(b"skipBreak:")
    skip_btn.sizeToFit()

    # (view, gap below it), top to bottom
    stack: list[tuple[AppKit.NSView, float]] = [(title, 22.0)]
    if countdown is not None:
        stack += [(subtitle, 36.0), (countdown, 56.0)]
    else:
        stack += [(subtitle, 56.0)]
    stack.append((skip_btn, 0.0))

    total_height = sum(v.frame().size.height + gap for v, gap in stack) - stack[-1][1]
    y = cy + total_height / 2

    for view, gap in stack:
        fh = view.frame().size.height
        fw = view.frame().size.width
        y -= fh
        view.setFrame_(Foundation.NSMakeRect(cx - fw / 2, y, fw, fh))
        content.addSubview_(view)
        y -= gap

    return countdown


def _make_overlay_window(screen: AppKit.NSScreen, theme: OverlayTheme) -> _OverlayWindow:
    win = _OverlayWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        screen.frame(),
        AppKit.NSWindowStyleMaskBorderless,
        AppKit.NSBackingStoreBuffered,
        False,
    )
    win.setBackgroundColor_(theme.bg)
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


def show_overlay(
    on_dismiss: Callable[[], None] | None = None,
    break_seconds: int = 20,
    theme: OverlayTheme = EYE_THEME,
) -> None:
    """Show a full-screen break overlay on all monitors. Returns immediately;
    cleanup and on_dismiss() fire when the overlay is dismissed."""
    dismissed = [False]
    windows: list[_OverlayWindow] = []
    countdowns: list[AppKit.NSTextField] = []
    auto_timer: list[threading.Timer | None] = [None]
    tick_timer: list[Foundation.NSTimer | None] = [None]

    import eye.overlay as _self

    def dismiss() -> None:
        if dismissed[0]:
            return
        dismissed[0] = True
        if auto_timer[0]:
            auto_timer[0].cancel()
        if tick_timer[0]:
            tick_timer[0].invalidate()
            tick_timer[0] = None
        for win in windows:
            win.orderOut_(None)
        _self._active_dismiss = None
        if on_dismiss:
            on_dismiss()

    for screen in AppKit.NSScreen.screens():
        win = _make_overlay_window(screen, theme)
        win._dismiss_callback = dismiss
        countdown = _add_content(win, theme, break_seconds)
        if countdown is not None:
            countdowns.append(countdown)
        win.orderFrontRegardless()
        windows.append(win)

    _self._active_dismiss = dismiss

    if countdowns:
        deadline = time.monotonic() + break_seconds

        def update_countdown() -> None:
            text = _format_countdown(deadline - time.monotonic())
            for label in countdowns:
                label.setAttributedStringValue_(_countdown_attr(text, theme))

        ticker = _CountdownTicker.alloc().init()
        ticker._callback = update_countdown
        # CommonModes so it keeps firing during event tracking (see CLAUDE.md).
        timer = Foundation.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, ticker, b"tick:", None, True
        )
        Foundation.NSRunLoop.mainRunLoop().addTimer_forMode_(
            timer, Foundation.NSRunLoopCommonModes
        )
        tick_timer[0] = timer

    auto_timer[0] = threading.Timer(break_seconds, lambda: AppHelper.callAfter(dismiss))
    auto_timer[0].daemon = True
    auto_timer[0].start()


# Exposed for the signal handler in timer.py
_active_dismiss: Callable[[], None] | None = None
