import tkinter as tk
from typing import Callable

BG = "#0d0d0d"
FG = "#f0f0f0"
FG_DIM = "#888888"


def _get_screen_geometries() -> list[tuple[int, int, int, int]]:
    """Return (x, y, width, height) for each connected monitor."""
    try:
        from AppKit import NSScreen  # type: ignore[import]
        screens = []
        for screen in NSScreen.screens():
            f = screen.frame()
            screens.append((
                int(f.origin.x),
                int(f.origin.y),
                int(f.size.width),
                int(f.size.height),
            ))
        return screens
    except ImportError:
        return None


def _activate_app() -> None:
    """Bring the tkinter app to the foreground so it can receive key events."""
    try:
        from AppKit import NSApplication  # type: ignore[import]
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except ImportError:
        pass


def _make_overlay_window(parent, x: int, y: int, w: int, h: int) -> tk.BaseWidget:
    if parent is None:
        win = tk.Tk()
    else:
        win = tk.Toplevel(parent)

    win.configure(bg=BG)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.geometry(f"{w}x{h}+{x}+{y}")

    frame = tk.Frame(win, bg=BG)
    frame.place(relx=0.5, rely=0.5, anchor="center")

    tk.Label(frame, text="Look away",
             font=("SF Pro Display", 52, "bold"), bg=BG, fg=FG).pack(pady=(0, 4))
    tk.Label(frame, text="20 feet away for 20 seconds",
             font=("SF Pro Display", 28), bg=BG, fg=FG).pack(pady=(0, 40))
    tk.Label(frame, text="Press Space or Esc to dismiss early, or run `eye skip`",
             font=("SF Pro Mono", 13), bg=BG, fg=FG_DIM).pack()

    return win


def show_overlay(on_dismiss: Callable[[], None] | None = None, break_seconds: int = 20) -> None:
    """Show a full-screen break overlay on all monitors. Blocks until dismissed."""
    geometries = _get_screen_geometries()

    # Build all windows; root is the Tk() instance on the first screen
    root: tk.Tk | None = None
    extra_wins: list[tk.Toplevel] = []

    if geometries:
        for i, (x, y, w, h) in enumerate(geometries):
            if i == 0:
                root = _make_overlay_window(None, x, y, w, h)
            else:
                extra_wins.append(_make_overlay_window(root, x, y, w, h))
    else:
        root = _make_overlay_window(None, 0, 0, 0, 0)
        root.attributes("-fullscreen", True)

    dismissed = False

    def dismiss() -> None:
        nonlocal dismissed
        if dismissed:
            return
        dismissed = True
        for win in extra_wins:
            win.destroy()
        root.destroy()
        if on_dismiss:
            on_dismiss()

    root.bind_all("<space>", lambda _e: dismiss())
    root.bind_all("<Escape>", lambda _e: dismiss())

    root.after(break_seconds * 1000, dismiss)

    # Activate the app and grab focus after windows are drawn
    root.after(50, _activate_app)
    root.after(100, root.focus_force)

    # Expose for SIGUSR1 handler in timer.py
    import eye.overlay as _self
    _self._active_root = root
    _self._active_dismiss = dismiss

    root.mainloop()

    import eye.overlay as _self
    _self._active_root = None
    _self._active_dismiss = None


# Set during an active overlay so timer.py's signal handler can reach them
_active_root: tk.Tk | None = None
_active_dismiss: Callable[[], None] | None = None
