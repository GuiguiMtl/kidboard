"""Effect registry."""
from .base import Effect
from .flash import Flash
from .paint import Paint
from .rainbow import Rainbow
from .ripple import Ripple
from .sleep import Sleep
from .splash import Splash

REGISTRY = {cls.name: cls for cls in (Flash, Splash, Ripple, Paint, Rainbow, Sleep)}


def build(name, rows, cols, layout=None):
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise ValueError("unknown effect %r; have: %s"
                         % (name, ", ".join(sorted(REGISTRY)))) from None
    if cls.needs_layout and layout is None:
        raise ValueError("effect %r needs a key mapping; run tools/map_keys.py" % name)
    return cls(rows, cols, layout)


def available(layout=None):
    """Effect names usable right now - layout-free ones always, the rest only
    once a mapping exists."""
    return [name for name, cls in REGISTRY.items()
            if name != "sleep" and (layout is not None or not cls.needs_layout)]
