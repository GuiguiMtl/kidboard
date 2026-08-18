"""Effect protocol plus the small bits of maths every effect wants."""
import colorsys
import math

import numpy as np

# Golden-ratio hue walk: successive colours are always far apart, so consecutive
# keypresses never look like the same colour twice.
GOLDEN = 0.61803398875


class Effect:
    name = "base"
    # Effects that place light under a specific key need the mapping table.
    # Layout-free effects run before you have mapped anything, which means the
    # toy works the day the driver comes up.
    needs_layout = False

    def __init__(self, rows, cols, layout=None):
        self.rows = rows
        self.cols = cols
        self.layout = layout
        self._hue = 0.0

    def next_hue(self):
        self._hue = (self._hue + GOLDEN) % 1.0
        return self._hue

    def reset(self, buf):
        buf[:] = 0.0

    def on_key(self, event, cell):
        """A key went down. `cell` is (row, col) or None if unmapped."""

    def on_frame(self, dt, buf):
        """Advance by dt seconds and write into buf (rows, cols, 3), 0..1."""


def hsv(h, s=1.0, v=1.0):
    return colorsys.hsv_to_rgb(h % 1.0, s, v)


def decay(buf, half_life, dt):
    """Exponential fade that is frame-rate independent."""
    if half_life <= 0:
        buf[:] = 0.0
    else:
        buf *= 0.5 ** (dt / half_life)


def distance_grid(rows, cols):
    """(rows, cols, 2) of cell coordinates, for vectorised distance maths.

    Columns are ~1 key wide but rows are ~1 key tall too, so plain Euclidean
    distance on the matrix indices looks right on the physical board.
    """
    yy, xx = np.mgrid[0:rows, 0:cols]
    return yy.astype(np.float32), xx.astype(np.float32)


def breathe(t, period=6.0, low=0.08, high=0.35):
    """Slow sine in [low, high]. Used for idle/sleep."""
    phase = 0.5 - 0.5 * math.cos(2.0 * math.pi * t / period)
    return low + (high - low) * phase
