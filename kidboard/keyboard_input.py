"""Exclusive keyboard capture.

This is the safety-critical file. An evdev grab (EVIOCGRAB) tells the kernel to
stop delivering events from a device to everyone else, so her keystrokes reach
this process and nothing at all besides - no TTY, no shell, no SSH session.

Razer keyboards present several event nodes (main keyboard, consumer-control,
macro/vendor node) and they all emit EV_KEY. Grabbing only the first one leaks
keystrokes from the others, so we grab every matching node.
"""
import logging
import selectors
import threading
import time
from collections import deque

log = logging.getLogger(__name__)

RESCAN_INTERVAL = 3.0      # seconds between rediscovery attempts when unplugged


class KeyEvent:
    __slots__ = ("code", "name", "down", "at", "source")

    def __init__(self, code, name, down, at, source=""):
        self.code = code
        self.name = name
        self.down = down       # True on press, False on release
        self.at = at
        self.source = source   # which event node reported it; several may

    def __repr__(self):
        return "<KeyEvent %s %s%s>" % (
            self.name, "down" if self.down else "up",
            " from " + self.source if self.source else "")


class KeyStream:
    """Background thread that grabs matching devices and queues key events."""

    def __init__(self, match="razer", maxlen=256, debounce_ms=None):
        from . import config

        self._match = match.lower()
        # Hardware debounce. Only presses are filtered - releases pass through
        # untouched, so a chattering key can never get stuck in the "held"
        # state that the effect-switch chord depends on.
        if debounce_ms is None:
            debounce_ms = config.DEBOUNCE_MS
        self._debounce = max(0.0, debounce_ms / 1000.0)
        self._last_down = {}
        self.suppressed = 0
        self._queue = deque(maxlen=maxlen)   # bounded: a stuck consumer must not eat RAM
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._devices = []
        self._thread = None
        self.grabbed_names = []

    # ------------------------------------------------------------- discovery
    def _discover(self):
        from evdev import InputDevice, list_devices, ecodes

        found = []
        for path in list_devices():
            try:
                dev = InputDevice(path)
            except OSError:
                continue        # disappeared between listing and opening
            caps = dev.capabilities()
            if ecodes.EV_KEY not in caps:
                dev.close()
                continue
            if self._match not in dev.name.lower():
                dev.close()
                continue
            found.append(dev)
        return found

    def _grab_all(self):
        devices, names = [], []
        for dev in self._discover():
            try:
                dev.grab()
            except OSError as exc:
                # Someone else holds it, or we lack permission. Do not keep a
                # half-grabbed device around: an ungrabbed node leaks keystrokes.
                log.error("could not grab %s (%s): %s", dev.name, dev.path, exc)
                dev.close()
                continue
            devices.append(dev)
            names.append("%s (%s)" % (dev.name, dev.path))
        return devices, names

    def _release_all(self):
        for dev in self._devices:
            try:
                dev.ungrab()
            except OSError:
                pass
            try:
                dev.close()
            except OSError:
                pass
        self._devices = []
        self.grabbed_names = []

    # ------------------------------------------------------------------ thread
    def start(self):
        self._thread = threading.Thread(target=self._run, name="keystream", daemon=True)
        self._thread.start()
        return self

    def _run(self):
        from evdev import ecodes

        while not self._stop.is_set():
            self._devices, self.grabbed_names = self._grab_all()
            if not self._devices:
                log.warning("no matching input device; retrying in %.0fs", RESCAN_INTERVAL)
                self._stop.wait(RESCAN_INTERVAL)
                continue

            log.info("grabbed %d node(s): %s", len(self._devices), ", ".join(self.grabbed_names))
            sel = selectors.DefaultSelector()
            for dev in self._devices:
                sel.register(dev, selectors.EVENT_READ)

            try:
                while not self._stop.is_set():
                    for key, _ in sel.select(timeout=0.5):
                        dev = key.fileobj
                        for event in dev.read():
                            if event.type != ecodes.EV_KEY:
                                continue
                            if event.value == 2:      # autorepeat: she is holding it
                                continue
                            name = ecodes.KEY.get(event.code)
                            if isinstance(name, (list, tuple)):
                                name = name[0]
                            now = time.monotonic()
                            if event.value == 1 and self._debounce:
                                previous = self._last_down.get(event.code)
                                if previous is not None and now - previous < self._debounce:
                                    self.suppressed += 1
                                    continue
                                self._last_down[event.code] = now
                            self._push(KeyEvent(event.code, name, event.value == 1,
                                                now, dev.path))
            except OSError as exc:
                log.warning("input device went away (%s); rescanning", exc)
            finally:
                sel.close()
                self._release_all()

            if not self._stop.is_set():
                self._stop.wait(RESCAN_INTERVAL)

        self._release_all()

    def _push(self, event):
        with self._lock:
            self._queue.append(event)

    # ------------------------------------------------------------------ public
    def poll(self):
        """Drain and return everything queued since the last call."""
        with self._lock:
            events = list(self._queue)
            self._queue.clear()
        return events

    @property
    def connected(self):
        return bool(self._devices)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._release_all()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False
