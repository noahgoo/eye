import tkinter as tk
from typing import Callable


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
        return None  # fallback handled by caller


def show_overlay(on_dismiss: Callable[[], None] | None = None, break_seconds: int = 20) -> None:
    """Show a full-screen break overlay on all monitors.

    Blocks until the overlay is dismissed (by timer, keypress, or SIGUSR1).
    Calls on_dismiss() after dismissal.
    """
    root = tk.Tk()
    root.withdraw()  # hide root; we'll use Toplevels for each screen

    geometries = _get_screen_geometries()
    if geometries is None:
        # AppKit unavailable — fall back to primary screen via root window
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        geometries = [(0, 0, w, h)]

    windows: list[tk.Toplevel] = []
    dismissed = False

    def dismiss() -> None:
        nonlocal dismissed
        if dismissed:
            return
        dismissed = True
        for win in windows:
            win.destroy()
        root.destroy()
        if on_dismiss:
            on_dismiss()

    BG = "#0d0d0d"
    FG = "#f0f0f0"
    FG_DIM = "#888888"

    for (x, y, w, h) in geometries:
        win = tk.Toplevel(root)
        win.configure(bg=BG)
        win.overrideredirect(True)          # no title bar
        win.attributes("-topmost", True)
        win.geometry(f"{w}x{h}+{x}+{y}")

        # Center content with a frame
        frame = tk.Frame(win, bg=BG)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            frame,
            text="Look away",
            font=("SF Pro Display", 52, "bold"),
            bg=BG, fg=FG,
        ).pack(pady=(0, 4))

        tk.Label(
            frame,
            text="20 feet away for 20 seconds",
            font=("SF Pro Display", 28),
            bg=BG, fg=FG,
        ).pack(pady=(0, 40))

        tk.Label(
            frame,
            text='Press Space or Esc to dismiss early, or run `eye skip`',
            font=("SF Pro Mono", 13),
            bg=BG, fg=FG_DIM,
        ).pack()

        win.bind("<space>", lambda _e: dismiss())
        win.bind("<Escape>", lambda _e: dismiss())
        win.focus_force()

        windows.append(win)

    root.after(break_seconds * 1000, dismiss)

    # Expose dismiss so timer.py can call it from a signal handler
    root._eye_dismiss = dismiss  # type: ignore[attr-defined]

    # Store root globally so SIGUSR1 handler in timer.py can reach it
    import eye.overlay as _self
    _self._active_root = root
    _self._active_dismiss = dismiss

    root.mainloop()

    import eye.overlay as _self
    _self._active_root = None
    _self._active_dismiss = None


# Module-level refs set during an active overlay (used by timer.py signal handler)
_active_root: tk.Tk | None = None
_active_dismiss: Callable[[], None] | None = None
