"""Expanding rings from each pressed key."""
import numpy as np

from .base import Effect, decay, distance_grid, hsv


class Ripple(Effect):
    name = "ripple"
    needs_layout = True

    SPEED = 11.0            # cells per second
    WIDTH = 1.6             # ring thickness in cells
    LIFE = 1.6              # seconds before a ring is retired
    MAX_RIPPLES = 12        # a toddler mashing will otherwise queue hundreds

    def __init__(self, rows, cols, layout=None):
        super().__init__(rows, cols, layout)
        self._yy, self._xx = distance_grid(rows, cols)
        self._ripples = []

    def reset(self, buf):
        super().reset(buf)
        self._ripples.clear()

    def on_key(self, event, cell):
        if cell is None:
            return
        r, c = cell
        colour = np.asarray(hsv(self.next_hue(), 0.95, 1.0), dtype=np.float32)
        self._ripples.append([float(r), float(c), 0.0, colour])
        if len(self._ripples) > self.MAX_RIPPLES:
            del self._ripples[:-self.MAX_RIPPLES]

    def on_frame(self, dt, buf):
        decay(buf, 0.25, dt)
        alive = []
        for ripple in self._ripples:
            r, c, age, colour = ripple
            age += dt
            if age >= self.LIFE:
                continue
            ripple[2] = age
            alive.append(ripple)

            radius = age * self.SPEED
            dist = np.hypot(self._yy - r, self._xx - c)
            # Gaussian band around the ring radius, fading as the ring ages.
            band = np.exp(-((dist - radius) ** 2) / (2.0 * self.WIDTH ** 2))
            band *= max(0.0, 1.0 - age / self.LIFE)
            contribution = band[:, :, None] * colour
            np.maximum(buf, contribution, out=buf)
        self._ripples = alive
