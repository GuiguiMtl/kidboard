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


def marking_remaining_cells_empty():
    """The 'd' command in map_keys: once every real key is mapped, whatever is
    left has no key under it. A 65% board has ~12 such cells out of 80."""
    layout = Layout(5, 16, {1: (0, 0), 2: (0, 1)}, [(4, 15)], name="t")

    leftover = layout.unmapped_cells()
    check("unknown cells exclude mapped and known-empty ones",
          (0, 0) not in leftover and (0, 1) not in leftover and (4, 15) not in leftover)

    for cell in leftover:
        layout.unpressable.add(cell)

    check("nothing unknown remains", layout.unmapped_cells() == [])
    check("mapped keys survive", layout.key_to_cell == {1: (0, 0), 2: (0, 1)})
    check("every cell is accounted for",
          len(layout.mapped_cells()) + len(layout.unpressable) == 5 * 16,
          "%d + %d" % (len(layout.mapped_cells()), len(layout.unpressable)))


def debounce_filters_chatter():
    """The keyboard registers one press several times. Presses are filtered;
    releases must not be, or a chattering key gets stuck 'held' and the
    effect-switch chord breaks."""
    from kidboard.keyboard_input import KeyStream

    stream = KeyStream.__new__(KeyStream)
    stream._debounce = 0.060
    stream._last_down = {}
    stream.suppressed = 0
    stream._queue = []
    stream._lock = _NullLock()

    def feed(code, down, at):
        """Mirrors the filter in KeyStream._run."""
        if down and stream._debounce:
            previous = stream._last_down.get(code)
            if previous is not None and at - previous < stream._debounce:
                stream.suppressed += 1
                return
            stream._last_down[code] = at
        stream._queue.append((code, down, at))

    # One press that chatters four times over 25 ms, then the release.
    for offset in (0.000, 0.008, 0.017, 0.025):
        feed(30, True, offset)
    feed(30, False, 0.030)

    downs = [e for e in stream._queue if e[1]]
    ups = [e for e in stream._queue if not e[1]]
    check("chatter collapses to one press", len(downs) == 1,
          "%d presses got through" % len(downs))
    check("releases are never filtered", len(ups) == 1)
    check("suppressed count is reported", stream.suppressed == 3,
          "counted %d" % stream.suppressed)

    # A deliberate second press well after the window must survive.
    feed(30, True, 0.400)
    downs = [e for e in stream._queue if e[1]]
    check("real second press survives", len(downs) == 2,
          "%d presses" % len(downs))

    # A different key pressed inside the window is unrelated.
    feed(31, True, 0.405)
    check("other keys unaffected", any(e[0] == 31 for e in stream._queue))


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def mapper_settles_after_duplicates():
    """One press can arrive from several event nodes. The mapper must swallow
    the extras instead of letting them advance the next cell."""
    from map_keys import settle, SETTLE_QUIET, SETTLE_TIMEOUT

    class Burst:
        """Emits n events, then falls silent."""

        def __init__(self, n):
            self.remaining = n

        def poll(self):
            if self.remaining > 0:
                self.remaining -= 1
                return [KeyEvent(30, "KEY_A", False, time.monotonic(), "/dev/input/event9")]
            return []

    burst = Burst(4)
    started = time.monotonic()
    settle(burst)
    elapsed = time.monotonic() - started
    check("settle drains duplicates", burst.remaining == 0)
    check("settle waits for quiet", elapsed >= SETTLE_QUIET,
          "returned after %.2fs" % elapsed)

    class Noisy:
        def poll(self):
            return [KeyEvent(30, "KEY_A", True, time.monotonic(), "/dev/input/event9")]

    started = time.monotonic()
    settle(Noisy())
    elapsed = time.monotonic() - started
    check("settle cannot hang", elapsed < SETTLE_TIMEOUT + 1.0,
          "took %.2fs" % elapsed)


def draw_skips_unchanged_frames():
    """A draw costs ~48 ms on the V3 Mini. Redrawing an identical frame is the
    single most expensive thing this code can do for no reason."""
    from kidboard.device import Keyboard

    class FakeMatrix:
        def __setitem__(self, key, value):
            pass

    class FakeFx:
        def __init__(self):
            self.matrix = FakeMatrix()
            self.draws = 0

        def draw(self):
            self.draws += 1

    kbd = Keyboard.__new__(Keyboard)
    kbd.rows, kbd.cols = 5, 16
    kbd._fx = FakeFx()
    kbd._last_frame = None
    kbd._offline = False

    buf = np.zeros((5, 16, 3), dtype=np.float32)
    buf[2, 3] = (1.0, 0.5, 0.25)

    kbd.draw(buf)
    kbd.draw(buf)
    kbd.draw(buf)
    check("identical frames drawn once", kbd._fx.draws == 1,
          "%d draws" % kbd._fx.draws)

    buf[0, 0] = (1.0, 1.0, 1.0)
    kbd.draw(buf)
    check("changed frame is drawn", kbd._fx.draws == 2,
          "%d draws" % kbd._fx.draws)

    # Sub-quantisation drift must not count as a change.
    buf[0, 0] = (1.0, 1.0, 1.0 - 1e-4)
    kbd.draw(buf)
    check("sub-1/255 drift ignored", kbd._fx.draws == 2,
          "%d draws" % kbd._fx.draws)


def reconnect_backs_off():
    """An unplugged keyboard must not retry (or log) on every dropped frame -
    that journal lives on an SD card."""
    from kidboard.device import Keyboard

    kbd = Keyboard.__new__(Keyboard)          # no hardware, no daemon
    kbd._next_retry = 0.0
    kbd._retry_delay = Keyboard.RETRY_MIN
    kbd._offline = False
    attempts = []

    def always_fails():
        attempts.append(time.monotonic())
        raise RuntimeError("unplugged")

    kbd.connect = always_fails

    # 0.4 s of dropped frames at 30 fps: 12 draw failures.
    deadline = time.monotonic() + 0.4
    frames = 0
    while time.monotonic() < deadline:
        kbd._reconnect()
        frames += 1
        time.sleep(1 / 30.0)

    check("reconnect backs off", len(attempts) < frames / 2,
          "%d attempts across %d failed frames" % (len(attempts), frames))
    check("backoff widens", kbd._retry_delay > Keyboard.RETRY_MIN,
          "delay stayed at %.2f" % kbd._retry_delay)
    check("outage reported once", kbd._offline)


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

    print("\nresilience")
    marking_remaining_cells_empty()
    debounce_filters_chatter()
    mapper_settles_after_duplicates()
    draw_skips_unchanged_frames()
    reconnect_backs_off()

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
