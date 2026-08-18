"""The pressed key lights up and fades, spilling a little onto its neighbours."""
import numpy as np

from .base import Effect, decay, hsv


class Splash(Effect):
    name = "splash"
    needs_layout = True

    HALF_LIFE = 0.55
    SPILL = 0.35            # how much of the colour lands on adjacent keys

    def __init__(self, rows, cols, layout=None):
        super().__init__(rows, cols, layout)
        self._pending = []

    def on_key(self, event, cell):
        if cell is None:
            return
        r, c = cell
        colour = np.asarray(hsv(self.next_hue(), 0.9, 1.0), dtype=np.float32)
        self._pending.append((r, c, colour))

    def on_frame(self, dt, buf):
        decay(buf, self.HALF_LIFE, dt)
        for r, c, colour in self._pending:
            buf[r, c] = colour
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    np.maximum(buf[nr, nc], colour * self.SPILL, out=buf[nr, nc])
        self._pending.clear()
