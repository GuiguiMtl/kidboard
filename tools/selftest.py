#!/usr/bin/env python3
"""Hardware-free checks. Runs anywhere, including the machine you edit on.

    python3 tools/selftest.py
"""
import sys
import time

import numpy as np

import _bootstrap  # noqa: F401
from kidboard import effects as registry
from kidboard.effects.base import decay
from kidboard.engine import Engine
from kidboard.keyboard_input import KeyEvent
from kidboard.layout import Layout

sys.path.insert(0, __file__.rsplit("selftest.py", 1)[0])
from simulate import FakeKeyStream, FakeKeyboard, synthetic_layout  # noqa: E402

FAILURES = []


def check(name, condition, detail=""):
    status = "ok  " if condition else "FAIL"
    print("  %s %s%s" % (status, name, ("  <- " + detail) if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def effect_produces_light(name, layout):
    effect = registry.build(name, layout.rows, layout.cols, layout)
    buf = np.zeros((layout.rows, layout.cols, 3), dtype=np.float32)
    codes = sorted(layout.key_to_cell)

    peak = 0.0
    for frame in range(60):
        if frame % 7 == 0:
            code = codes[frame % len(codes)]
            effect.on_key(KeyEvent(code, "K", True, 0.0), layout.cell(code))
        effect.on_frame(1 / 30.0, buf)
        peak = max(peak, float(buf.max()))

    check("%s lights up" % name, peak > 0.2, "peak was %.3f" % peak)
    check("%s stays in range" % name,
          float(buf.min()) >= 0.0 and float(buf.max()) <= 1.0,
          "min %.3f max %.3f" % (buf.min(), buf.max()))
    check("%s has no NaNs" % name, bool(np.isfinite(buf).all()))


def unmapped_keys_are_survivable(layout):
    """Effects must not explode on a key that was never mapped - that is the
    normal state before tools/map_keys.py has been run."""
    buf = np.zeros((layout.rows, layout.cols, 3), dtype=np.float32)
    for name in registry.REGISTRY:
        effect = registry.build(name, layout.rows, layout.cols, layout)
        effect.on_key(KeyEvent(9999, "KEY_UNKNOWN", True, 0.0), None)
        effect.on_frame(1 / 30.0, buf)
    check("unmapped keypress handled by every effect", True)


def decay_is_framerate_independent():
    slow = np.ones((1, 1, 3), dtype=np.float32)
    fast = np.ones((1, 1, 3), dtype=np.float32)
    decay(slow, 0.5, 0.1)
    for _ in range(10):
        decay(fast, 0.5, 0.01)
    check("decay is frame-rate independent",
          abs(float(slow[0, 0, 0]) - float(fast[0, 0, 0])) < 1e-5,
          "%.6f vs %.6f" % (slow[0, 0, 0], fast[0, 0, 0]))


def layout_roundtrip(tmp_path="layouts/.selftest.local.json"):
    """save/load needs evdev for the key-name table; skip where it is absent."""
    try:
        import evdev  # noqa: F401
    except ImportError:
        print("  skip layout save/load roundtrip (evdev not installed)")
        return
    import os
    from evdev import ecodes
    original = Layout(6, 22, {ecodes.KEY_A: (3, 1), ecodes.KEY_ESC: (0, 0)},
                      [(5, 3)], name="selftest")
    original.save(tmp_path)
    loaded = Layout.load(tmp_path)
    os.unlink(tmp_path)
    check("layout roundtrip", loaded.key_to_cell == original.key_to_cell
          and loaded.unpressable == original.unpressable)


def engine_runs():
    layout = synthetic_layout()
    keyboard = FakeKeyboard(render=False)
    keystream = FakeKeyStream(sorted(layout.key_to_cell), rate=20.0)
    engine = Engine(keyboard, keystream, layout,
                    registry.available(layout), fps=30, idle_seconds=0)

    stop_at = time.monotonic() + 1.0
    inner = engine._pump

    def pump(now):
        inner(now)
        if now >= stop_at:
            engine.stop()

    engine._pump = pump
    engine.run()
    check("engine drives frames", keyboard.frames > 20,
          "only %d frames" % keyboard.frames)


def engine_sleeps_and_wakes():
    layout = synthetic_layout()
    keyboard = FakeKeyboard(render=False)

    class Silent:
        def poll(self):
            return []

    engine = Engine(keyboard, Silent(), layout, ["flash"], fps=30, idle_seconds=0.2)
    engine._last_key_at = time.monotonic() - 1.0
    engine._pump(time.monotonic())
    check("engine sleeps when idle", engine._asleep)

    engine.keystream = FakeKeyStream(sorted(layout.key_to_cell), rate=100.0)
    time.sleep(0.05)
    engine._pump(time.monotonic())
    check("engine wakes on a keypress", not engine._asleep)


def main():
    layout = synthetic_layout()

    print("effects")
    for name in registry.available(layout):
        effect_produces_light(name, layout)
    unmapped_keys_are_survivable(layout)

    print("\nmaths")
    decay_is_framerate_independent()

    print("\nlayout")
    layout_roundtrip()

    print("\nengine")
    engine_runs()
    engine_sleeps_and_wakes()

    print()
    if FAILURES:
        print("%d FAILED: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
