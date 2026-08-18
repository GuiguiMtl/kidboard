"""Every key permanently keeps the colour it was given.

The board fills in as she works across it, and it is still there when she looks
back. Effort accumulates into something visible, which is a different and
longer-lasting kind of interesting than a flash that vanishes.
"""
import math

import numpy as np

from .base import Effect, hsv


class Paint(Effect):
    name = "paint"
    needs_layout = True

    SHIMMER_DEPTH = 0.18    # gentle life so a finished board is not a static picture
    SHIMMER_PERIOD = 4.0
    UNLIT = 0.05            # unpainted keys glow faintly, inviting a press

    def __init__(self, rows, cols, layout=None):
        super().__init__(rows, cols, layout)
        self._canvas = np.zeros((rows, cols, 3), dtype=np.float32)
        self._canvas[:] = self.UNLIT
        self._t = 0.0

    def reset(self, buf):
        super().reset(buf)
        self._canvas[:] = self.UNLIT

    def on_key(self, event, cell):
        if cell is None:
            return
        # Pressing an already-painted key repaints it, so there is always
        # something new to do even once the board is full.
        self._canvas[cell[0], cell[1]] = hsv(self.next_hue(), 0.9, 1.0)

    def on_frame(self, dt, buf):
        self._t += dt
        shimmer = 1.0 - self.SHIMMER_DEPTH * (
            0.5 - 0.5 * math.cos(2.0 * math.pi * self._t / self.SHIMMER_PERIOD)
        )
        np.multiply(self._canvas, shimmer, out=buf)
