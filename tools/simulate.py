#!/usr/bin/env python3
"""Preview the effects in a terminal - no Pi, no keyboard, no OpenRazer.

Renders the 6x22 matrix as coloured blocks and feeds it synthetic keypresses,
so effects can be tuned on any machine and the engine can be exercised without
hardware.

    python3 tools/simulate.py                 # cycle every effect
    python3 tools/simulate.py --effect ripple --seconds 10
"""
import argparse
import itertools
import random
import sys
import time

import numpy as np

import _bootstrap  # noqa: F401
from kidboard.engine import Engine
from kidboard.keyboard_input import KeyEvent
from kidboard.layout import Layout

ROWS, COLS = 6, 22


class FakeKeyboard:
    """Draws the matrix as ANSI truecolour blocks."""

    def __init__(self, rows=ROWS, cols=COLS, render=True):
        self.rows, self.cols = rows, cols
        self.name = "Simulated 6x22"
        self.frames = 0
        self._render = render
        if render:
            sys.stdout.write("\033[2J\033[?25l")     # clear, hide cursor

    def draw(self, buf):
        self.frames += 1
        if not self._render:
            return True
        out = ["\033[H"]
        for r in range(self.rows):
            for c in range(self.cols):
                red, green, blue = (np.clip(buf[r, c], 0, 1) * 255).astype(int)
                out.append("\033[48;2;%d;%d;%dm  " % (red, green, blue))
            out.append("\033[0m\n")
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        return True

    def off(self):
        if self._render:
            sys.stdout.write("\033[0m\033[?25h\n")   # restore cursor
        return True


class FakeKeyStream:
    """A toddler: bursts of keys with pauses, not a metronome."""

    def __init__(self, keycodes, rate=6.0, seed=1):
        self._codes = list(keycodes)
        self._rate = rate
        self._rng = random.Random(seed)
        self._next = time.monotonic()

    def poll(self):
        now = time.monotonic()
        events = []
        while now >= self._next:
            code = self._rng.choice(self._codes)
            events.append(KeyEvent(code, "KEY_%d" % code, True, now))
            events.append(KeyEvent(code, "KEY_%d" % code, False, now))
            gap = self._rng.expovariate(self._rate)
            self._next += max(gap, 0.02)
        return events

    def stop(self):
        pass


def synthetic_layout(rows=ROWS, cols=COLS):
    """Stand-in for a real mapping: one fake keycode per cell, minus a few dead
    cells so the code that handles gaps gets exercised too."""
    key_to_cell, unpressable = {}, []
    code = 1
    for r in range(rows):
        for c in range(cols):
            if (r + c * 3) % 17 == 0:
                unpressable.append((r, c))
                continue
            key_to_cell[code] = (r, c)
            code += 1
    return Layout(rows, cols, key_to_cell, unpressable, name="simulated")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--effect", help="one effect instead of cycling all of them")
    ap.add_argument("--seconds", type=float, default=4.0, help="per effect")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--rate", type=float, default=6.0, help="keypresses per second")
    ap.add_argument("--headless", action="store_true",
                    help="run the loop without drawing; used as a smoke test")
    args = ap.parse_args()

    layout = synthetic_layout()
    keyboard = FakeKeyboard(render=not args.headless)
    keystream = FakeKeyStream(sorted(layout.key_to_cell), rate=args.rate)

    from kidboard import effects as registry
    names = [args.effect] if args.effect else registry.available(layout)

    engine = Engine(keyboard, keystream, layout, names,
                    fps=args.fps, idle_seconds=0, chord=None)

    deadline = time.monotonic() + args.seconds
    switches = itertools.count()

    original_pump = engine._pump

    def pump(now):
        nonlocal deadline
        original_pump(now)
        if now >= deadline:
            deadline = now + args.seconds
            if next(switches) >= len(names) - 1:
                engine.stop()
            else:
                engine.next_effect()

    engine._pump = pump

    try:
        engine.run()
    except KeyboardInterrupt:
        pass
    finally:
        keyboard.off()

    print("rendered %d frames across %s" % (keyboard.frames, ", ".join(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
