"""Whole board flashes a new colour on every key. Needs no mapping.

The strongest effect for a very small child: maximum, unmissable consequence
for any key at all, including the broken spacebar's neighbours.
"""
import numpy as np

from .base import Effect, hsv


class Flash(Effect):
    name = "flash"
    needs_layout = False

    HALF_LIFE = 0.35        # seconds for a flash to fall to half brightness
    FLOOR = 0.06            # never fully dark, so the board reads as "on"

    def __init__(self, rows, cols, layout=None):
        super().__init__(rows, cols, layout)
        self._colour = np.zeros(3, dtype=np.float32)
        self._level = 0.0

    def on_key(self, event, cell):
        self._colour[:] = hsv(self.next_hue(), 0.95, 1.0)
        self._level = 1.0

    def on_frame(self, dt, buf):
        self._level *= 0.5 ** (dt / self.HALF_LIFE)
        level = max(self._level, self.FLOOR)
        buf[:] = self._colour * level
