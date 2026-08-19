"""The frame loop: input in, framebuffer out, at a steady rate."""
import logging
import time

import numpy as np

from . import effects as fx_registry
from .effects.sleep import Sleep

log = logging.getLogger(__name__)

# The chatter on this keyboard is intermittent and moves between keys, so a
# short bench session tells you very little. Report what the debounce actually
# caught during real use instead, where the sample is hours rather than seconds.
CHATTER_REPORT_INTERVAL = 600.0


class Engine:
    def __init__(self, keyboard, keystream, layout, effect_names,
                 fps=30, idle_seconds=300.0, chord=None):
        self.keyboard = keyboard
        self.keystream = keystream
        self.layout = layout
        self.fps = max(1, fps)
        self.idle_seconds = idle_seconds
        self.chord = chord

        self.rows, self.cols = keyboard.rows, keyboard.cols
        self.buf = np.zeros((self.rows, self.cols, 3), dtype=np.float32)

        if layout is not None and (layout.rows, layout.cols) != (self.rows, self.cols):
            log.warning("layout is %dx%d but the device is %dx%d - remap it",
                        layout.rows, layout.cols, self.rows, self.cols)

        self._names = list(effect_names)
        if not self._names:
            raise ValueError("no usable effects")
        self._index = 0
        self._effect = self._make(self._names[0])
        self._sleeper = Sleep(self.rows, self.cols, layout)
        self._asleep = False
        self._last_key_at = time.monotonic()
        self._running = False
        # Set from a signal handler; consumed in the loop so we never build an
        # effect from inside a signal context.
        self.switch_requested = False
        self._chatter_at = time.monotonic()
        self._chatter_seen = 0

    # ------------------------------------------------------------------ effects
    def _make(self, name):
        effect = fx_registry.build(name, self.rows, self.cols, self.layout)
        log.info("effect: %s", name)
        return effect

    def next_effect(self):
        self._index = (self._index + 1) % len(self._names)
        self._effect = self._make(self._names[self._index])
        self._effect.reset(self.buf)

    def set_effect(self, name):
        if name not in self._names:
            self._names.append(name)
        self._index = self._names.index(name)
        self._effect = self._make(name)
        self._effect.reset(self.buf)

    @property
    def current(self):
        return self._effect.name

    # --------------------------------------------------------------------- run
    def run(self):
        self._running = True
        frame_time = 1.0 / self.fps
        previous = time.monotonic()

        while self._running:
            now = time.monotonic()
            dt = now - previous
            previous = now
            # A long stall (daemon restart, USB replug) must not make effects
            # jump forward by seconds.
            dt = min(dt, 0.25)

            self._pump(now)
            active = self._sleeper if self._asleep else self._effect
            active.on_frame(dt, self.buf)
            self.keyboard.draw(self.buf)

            slack = frame_time - (time.monotonic() - now)
            if slack > 0:
                time.sleep(slack)

    def _pump(self, now):
        events = self.keystream.poll()

        for event in events:
            if self.chord is not None:
                self.chord.feed(event)
            if not event.down:
                continue

            self._last_key_at = now
            if self._asleep:
                self._wake()

            cell = self.layout.cell(event.code) if self.layout is not None else None
            self._effect.on_key(event, cell)

        chorded = self.chord is not None and self.chord.poll(now)
        if chorded or self.switch_requested:
            self.switch_requested = False
            self.next_effect()

        if (not self._asleep
                and self.idle_seconds > 0
                and now - self._last_key_at >= self.idle_seconds):
            self._sleep()

        self._report_chatter(now)

    def _report_chatter(self, now):
        if now - self._chatter_at < CHATTER_REPORT_INTERVAL:
            return
        self._chatter_at = now
        total = getattr(self.keystream, "suppressed", None)
        if total is None:
            return                      # a stream without debounce, e.g. the simulator
        recent = total - self._chatter_seen
        self._chatter_seen = total
        if recent:
            log.info("debounce suppressed %d chattered press(es) in the last %.0f min "
                     "(%d since start)", recent, CHATTER_REPORT_INTERVAL / 60.0, total)

    def _sleep(self):
        log.info("idle for %.0fs - sleeping", self.idle_seconds)
        self._asleep = True
        self._sleeper.reset(self.buf)

    def _wake(self):
        log.info("waking")
        self._asleep = False
        # Deliberately no reset: paint keeps the picture she made before the nap.

    def stop(self):
        self._running = False
