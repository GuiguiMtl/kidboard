"""Idle mode: a slow warm breath, dim enough to ignore.

Not "off" - the board should still look alive so it is obviously ready, and so
nobody wonders whether the Pi has died.
"""
import numpy as np

from .base import Effect, breathe

WARM = np.array((1.0, 0.45, 0.12), dtype=np.float32)


class Sleep(Effect):
    name = "sleep"
    needs_layout = False

    def __init__(self, rows, cols, layout=None):
        super().__init__(rows, cols, layout)
        self._t = 0.0

    def reset(self, buf):
        super().reset(buf)
        self._t = 0.0

    def on_frame(self, dt, buf):
        self._t += dt
        buf[:] = WARM * breathe(self._t, period=7.0, low=0.04, high=0.22)
