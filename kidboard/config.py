"""Tunables. Environment variables override, so you can experiment without edits:

    KIDBOARD_FPS=20 KIDBOARD_BRIGHTNESS=40 python3 -m kidboard.main
"""
import os


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# Frame rate for the software effects. 30 is smooth; the DBus round trip per
# frame is the ceiling, so tools/bench.py tells you what is actually achievable.
FPS = _int("KIDBOARD_FPS", 30)

# Hardware brightness cap, 0-100. She is close to it on a lap; full blast is a
# lot of light in the face.
BRIGHTNESS = _int("KIDBOARD_BRIGHTNESS", 70)

# Only grab input devices whose name contains this (case-insensitive).
DEVICE_MATCH = os.environ.get("KIDBOARD_DEVICE_MATCH", "razer")

# This keyboard chatters: a single physical press registers several times. It is
# a known fault of the V3 Mini, not something software caused, so suppress
# repeat presses of the same key within this many milliseconds. Chatter is
# typically under 30 ms; a deliberate double-tap of one key is well over 100 ms,
# even from a toddler. Set 0 to disable and see the raw stream.
DEBOUNCE_MS = _int("KIDBOARD_DEBOUNCE_MS", 60)

# Seconds of no keypresses before the slow breathing sleep effect takes over.
IDLE_SECONDS = _float("KIDBOARD_IDLE_SECONDS", 300.0)

# Adult-only effect switch: hold these two together for CHORD_HOLD seconds.
# Chosen far apart on the board (top-left and mid-right) and behind a long hold,
# so a two-handed palm slap will not trip it.
CHORD_KEYS = ("KEY_ESC", "KEY_ENTER")
CHORD_HOLD = _float("KIDBOARD_CHORD_HOLD", 3.0)

# Where map_keys.py writes and main.py reads the key -> matrix mapping.
LAYOUT_PATH = os.environ.get("KIDBOARD_LAYOUT", "layouts/blackwidow_v3.json")

# Effect rotation. Layout-free effects work before you have mapped anything.
DEFAULT_EFFECTS = ("flash", "splash", "ripple", "paint", "rainbow")
