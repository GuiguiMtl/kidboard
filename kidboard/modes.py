"""Adult-only effect switching.

A toddler mashing with both palms will hit almost every combination eventually,
so the switch is two keys at opposite ends of the board held together for
several seconds. Palm slaps are brief; a deliberate hold is not.
"""
import logging
import time

log = logging.getLogger(__name__)


class ChordWatcher:
    def __init__(self, key_names, hold_seconds):
        from evdev import ecodes

        self.codes = set()
        for name in key_names:
            code = ecodes.ecodes.get(name)
            if code is None:
                log.warning("chord key %s unknown to this kernel; ignoring", name)
                continue
            self.codes.add(code)
        self.hold = hold_seconds
        self._held = set()
        self._since = None
        self._fired = False

    def feed(self, event):
        if event.down:
            self._held.add(event.code)
        else:
            self._held.discard(event.code)

        complete = self.codes and self.codes.issubset(self._held)
        if complete:
            if self._since is None:
                self._since = event.at
        else:
            self._since = None
            self._fired = False

    def poll(self, now):
        """True exactly once per completed hold."""
        if self._since is None or self._fired:
            return False
        if now - self._since >= self.hold:
            self._fired = True
            return True
        return False
