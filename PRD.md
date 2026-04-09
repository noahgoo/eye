# PRD: `eye` — 20/20/20 Vision Rule CLI Tool

## Overview

`eye` is a macOS command-line tool that enforces the 20/20/20 vision rule: every 20 minutes, the user looks at something 20 feet away for 20 seconds. It does this by blocking the screen with a full-screen overlay, dismissible only after 20 seconds (or immediately via a skip command).

---

## Goals

- Simple, no-config start/stop via CLI
- Hard-to-ignore screen block (full-screen, always-on-top overlay)
- Skippable for when the user genuinely cannot pause
- No daemon or background service in v1 — runs as a foreground process

---

## Non-Goals (v1)

- Running as a launchd daemon or system service
- Configuration file or persistent settings
- Notifications (macOS notification center)
- Menu bar integration
- Cross-platform support (macOS only for now)

---

## Commands

| Command | Description |
|---|---|
| `eye start` | Start the timer loop in the foreground |
| `eye stop` | Stop a running `eye start` process (sends signal to kill it) |
| `eye skip` | Dismiss the current 20-second overlay early (if one is showing) |

### `eye start`

- Starts a loop: wait 20 minutes → show overlay for 20 seconds → repeat
- Prints status to stdout (e.g. `[eye] Next break in 20:00`, countdown updates)
- The process stays in foreground; Ctrl+C also stops it
- Writes its PID to a lockfile (e.g. `~/.eye.pid`) so `eye stop` and `eye skip` can find it

### `eye stop`

- Reads PID from `~/.eye.pid`
- Sends SIGTERM to that process
- Removes the lockfile
- Errors gracefully if no process is running

### `eye skip`

- Reads PID from `~/.eye.pid`
- Sends SIGUSR1 to the running process, which dismisses the overlay immediately
- No-ops if no overlay is currently showing

---

## Overlay Behavior

- Full-screen, always-on-top window covering all displays
- Dark background with centered text:
  - Large: "Look away — 20 feet for 20 seconds"
  - Countdown timer (20 → 0)
  - Small: "Run `eye skip` to dismiss early"
- The overlay is non-interactive (no buttons, no keyboard shortcuts within the window itself — skip is CLI-only)
- After 20 seconds, overlay dismisses automatically and the next 20-minute countdown begins

---

## Architecture

### Language & Runtime

- Python 3 (no external dependencies for core logic)
- Overlay UI: **tkinter** (ships with macOS Python) for full-screen window

### File Structure

```
eye/
├── eye.py          # Entry point; parses commands, dispatches to modules
├── timer.py        # 20-minute countdown loop, signal handling
├── overlay.py      # tkinter full-screen overlay window
└── pid.py          # PID file read/write/cleanup helpers
```

### Signal Protocol

| Signal | Meaning |
|---|---|
| SIGTERM | Stop the process cleanly (from `eye stop` or Ctrl+C) |
| SIGUSR1 | Dismiss the current overlay early (from `eye skip`) |

### PID File

- Location: `~/.eye.pid`
- Written on `eye start`, removed on clean exit
- Stale PID detection: if PID in file is not a running process, treat as not running

---

## CLI Entry Point

Installed as `eye` via a simple shebang script or `pip install -e .` with a `pyproject.toml` entry point:

```
[project.scripts]
eye = "eye:main"
```

---

## User Flow

```
$ eye start
[eye] Starting. Break in 20:00...
[eye] Break in 19:45...
...
[eye] Time for a break! (20s)
[eye] Break dismissed. Next break in 20:00...
```

In another terminal:
```
$ eye skip     # dismisses overlay if showing, else no-op
$ eye stop     # kills the eye start process
```

---

## Error Cases

| Scenario | Behavior |
|---|---|
| `eye start` when already running | Print error, exit 1 |
| `eye stop` with no running process | Print error, exit 1 |
| `eye skip` with no overlay showing | Print message, exit 0 |
| Stale PID file (process died) | Auto-clean and treat as not running |

---

## Installation

```bash
# From project root
pip install -e .
```

Requires Python 3.9+ and tkinter (included with standard macOS Python 3 installations).

---

## Future Enhancements (Post-v1)

- `eye daemon` — run as a launchd service that survives logout
- Configurable intervals (`eye start --interval 25 --break 30`)
- macOS notification before break
- Menu bar icon via `rumps`
- `eye status` command
- Sound/haptic cue at break start
