"""OpenRazer wrapper.

Everything the rest of the code needs from the keyboard's LEDs, plus survival
across `systemctl restart openrazer-daemon` and USB replug.
"""
import logging

log = logging.getLogger(__name__)


class NoDeviceError(RuntimeError):
    pass


class Keyboard:
    """A Razer keyboard with an addressable matrix."""

    def __init__(self, brightness=70, name_hint=None):
        self._brightness = brightness
        self._name_hint = name_hint
        self._device = None
        self._fx = None
        self.rows = 0
        self.cols = 0
        self.name = "<disconnected>"
        self.connect()

    # ---------------------------------------------------------------- connect
    def connect(self):
        from openrazer.client import DeviceManager

        manager = DeviceManager()
        # We drive every key individually; letting the daemon mirror effects
        # across devices would fight us.
        manager.sync_effects = False

        candidates = []
        for dev in manager.devices:
            fx = getattr(dev.fx, "advanced", None)
            if fx is None:            # no addressable matrix, e.g. a plain mouse
                continue
            if self._name_hint and self._name_hint.lower() not in dev.name.lower():
                continue
            candidates.append((dev, fx))

        if not candidates:
            raise NoDeviceError(
                "no Razer device with an addressable matrix found. "
                "Check: openrazer-daemon running, user in plugdev, rebooted since install."
            )

        # Prefer the widest matrix - on a keyboard+mouse setup that is the keyboard.
        dev, fx = max(candidates, key=lambda pair: pair[1].rows * pair[1].cols)
        self._device, self._fx = dev, fx
        self.rows, self.cols = fx.rows, fx.cols
        self.name = dev.name

        try:
            dev.brightness = self._brightness
        except Exception as exc:                      # not fatal, just brighter
            log.warning("could not set brightness: %s", exc)

        log.info("connected to %s (%dx%d)", self.name, self.rows, self.cols)
        return self

    def _reconnect(self):
        try:
            self.connect()
            return True
        except Exception as exc:
            log.warning("reconnect failed: %s", exc)
            return False

    # ------------------------------------------------------------------ output
    def draw(self, buf):
        """Push a (rows, cols, 3) float array in 0..1 to the keyboard.

        Returns True if the frame landed. A dropped frame is not worth crashing
        over - the daemon restarts, we pick the device back up next tick.
        """
        matrix = self._fx.matrix
        for r in range(self.rows):
            row = buf[r]
            for c in range(self.cols):
                px = row[c]
                matrix[r, c] = (
                    _byte(px[0]), _byte(px[1]), _byte(px[2])
                )
        try:
            self._fx.draw()
            return True
        except Exception as exc:
            log.warning("draw failed (%s); reconnecting", exc)
            return self._reconnect()

    def reactive(self, color=(0, 255, 255), speed=2):
        """Firmware-side reactive glow. Costs no CPU and survives us dying.

        speed: 1=500ms 2=1000ms 3=1500ms 4=2000ms
        """
        self._device.fx.reactive(color[0], color[1], color[2], speed)

    def off(self):
        try:
            self._device.fx.none()
        except Exception:
            pass

    @property
    def brightness(self):
        return self._brightness

    @brightness.setter
    def brightness(self, value):
        self._brightness = max(0, min(100, int(value)))
        try:
            self._device.brightness = self._brightness
        except Exception as exc:
            log.warning("could not set brightness: %s", exc)


def _byte(value):
    if value <= 0.0:
        return 0
    if value >= 1.0:
        return 255
    return int(value * 255.0 + 0.5)
