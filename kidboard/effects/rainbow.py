"""A rainbow that scrolls across the board and speeds up when she types.

Needs no mapping, and unlike the flash it is never dark or startling - a calmer
option for winding down.
"""
import numpy as np

from .base import Effect


class Rainbow(Effect):
    name = "rainbow"
    needs_layout = False

    BASE_SPEED = 0.06       # hue turns per second when idle
    KICK = 0.12             # extra speed per keypress
    MAX_SPEED = 0.9
    SPEED_HALF_LIFE = 1.2
    BASE_VALUE = 0.45
    KICK_VALUE = 0.55

    def __init__(self, rows, cols, layout=None):
        super().__init__(rows, cols, layout)
        self._phase = 0.0
        self._speed = 0.0
        self._energy = 0.0
        # Hue varies along a diagonal so the bands are not flat vertical stripes.
        yy, xx = np.mgrid[0:rows, 0:cols]
        self._field = (xx / max(cols - 1, 1) * 0.85
                       + yy / max(rows - 1, 1) * 0.25).astype(np.float32)

    def on_key(self, event, cell):
        self._speed = min(self._speed + self.KICK, self.MAX_SPEED)
        self._energy = 1.0

    def on_frame(self, dt, buf):
        fade = 0.5 ** (dt / self.SPEED_HALF_LIFE)
        self._speed *= fade
        self._energy *= fade
        self._phase = (self._phase + (self.BASE_SPEED + self._speed) * dt) % 1.0

        hue = (self._field + self._phase) % 1.0
        value = self.BASE_VALUE + self.KICK_VALUE * self._energy
        _hsv_to_rgb(hue, value, buf)


def _hsv_to_rgb(hue, value, out):
    """Vectorised HSV->RGB at full saturation. colorsys per cell is too slow
    to run 132 times a frame at 30 fps on a Pi."""
    h6 = hue * 6.0
    i = np.floor(h6).astype(np.int32)
    f = h6 - i
    p = 0.0
    q = value * (1.0 - f)
    t = value * f
    i = i % 6

    out[:, :, 0] = np.select([i == 0, i == 1, i == 2, i == 3, i == 4],
                             [value, q, p, p, t], default=value)
    out[:, :, 1] = np.select([i == 0, i == 1, i == 2, i == 3, i == 4],
                             [t, value, value, q, p], default=p)
    out[:, :, 2] = np.select([i == 0, i == 1, i == 2, i == 3, i == 4],
                             [p, p, t, value, value], default=q)
