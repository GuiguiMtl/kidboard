"""Entry point.  python3 -m kidboard.main"""
import argparse
import logging
import signal
import sys
import time

from . import config, effects as fx_registry, layout as layout_mod
from .device import Keyboard, NoDeviceError
from .engine import Engine
from .keyboard_input import KeyStream
from .modes import ChordWatcher

log = logging.getLogger("kidboard")


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="kidboard", description=__doc__)
    p.add_argument("--effect", help="start with this effect instead of the first")
    p.add_argument("--effects", help="comma-separated rotation order")
    p.add_argument("--fps", type=int, default=config.FPS)
    p.add_argument("--brightness", type=int, default=config.BRIGHTNESS,
                   help="0-100 hardware cap")
    p.add_argument("--layout", default=config.LAYOUT_PATH)
    p.add_argument("--idle", type=float, default=config.IDLE_SECONDS,
                   help="seconds before sleeping; 0 disables")
    p.add_argument("--list", action="store_true", help="list usable effects and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def connect_keyboard(brightness, attempts=30, delay=2.0):
    """openrazer-daemon may still be starting when we are. Wait for it rather
    than dying and leaning on systemd to retry."""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return Keyboard(brightness=brightness)
        except NoDeviceError as exc:
            last = exc
            log.warning("attempt %d/%d: %s", attempt, attempts, exc)
            time.sleep(delay)
    raise last


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    # A missing layout is the normal state before mapping, not an error. The
    # layout-free effects still run, so the toy works from day one.
    layout = None
    try:
        layout = layout_mod.load_or_none(args.layout)
    except Exception as exc:
        log.error("could not load layout %s: %s", args.layout, exc)
    if layout is None:
        log.warning("no key mapping at %s - running layout-free effects only. "
                    "Run tools/map_keys.py to unlock splash/ripple/paint.", args.layout)
    else:
        log.info("layout %s: %d keys mapped", layout.name, len(layout.key_to_cell))

    usable = fx_registry.available(layout)
    if args.list:
        print("\n".join(usable))
        return 0

    if args.effects:
        rotation = [n.strip() for n in args.effects.split(",") if n.strip()]
        unusable = [n for n in rotation if n not in usable]
        if unusable:
            log.error("not usable right now: %s (have: %s)",
                      ", ".join(unusable), ", ".join(usable))
            return 2
    else:
        rotation = [n for n in config.DEFAULT_EFFECTS if n in usable]

    if args.effect:
        if args.effect not in usable:
            log.error("effect %r not usable (have: %s)", args.effect, ", ".join(usable))
            return 2
        rotation = [args.effect] + [n for n in rotation if n != args.effect]

    keyboard = connect_keyboard(args.brightness)
    keystream = KeyStream(match=config.DEVICE_MATCH).start()
    chord = ChordWatcher(config.CHORD_KEYS, config.CHORD_HOLD)

    engine = Engine(keyboard, keystream, layout, rotation,
                    fps=args.fps, idle_seconds=args.idle, chord=chord)

    def on_term(signum, frame):
        log.info("signal %d - stopping", signum)
        engine.stop()

    def on_usr1(signum, frame):
        engine.switch_requested = True

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    signal.signal(signal.SIGUSR1, on_usr1)

    log.info("running: %s | %d fps | brightness %d | hold %s for %.0fs to switch",
             " -> ".join(rotation), args.fps, args.brightness,
             "+".join(k.replace("KEY_", "") for k in config.CHORD_KEYS),
             config.CHORD_HOLD)
    try:
        engine.run()
    finally:
        keystream.stop()
        # Go dark on the way out. A lit board while nothing is grabbing the
        # keyboard would say "safe to use" when keystrokes now reach the TTY.
        keyboard.off()
        log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
