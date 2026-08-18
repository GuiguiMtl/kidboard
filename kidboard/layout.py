"""Mapping between evdev key codes and (row, col) cells in the LED matrix.

There is no way to discover this from the hardware - Razer exposes a 6x22 grid
and says nothing about which cell is under which key. tools/map_keys.py walks
the grid and records the answer; this module loads the result.
"""
import json
import os


class Layout:
    def __init__(self, rows, cols, key_to_cell=None, unpressable=None, name=""):
        self.rows = rows
        self.cols = cols
        self.name = name
        # {evdev keycode int: (row, col)}
        self.key_to_cell = dict(key_to_cell or {})
        # Cells with an LED but no usable key underneath - the broken spacebar,
        # decorative strips. Effects still paint them; they just never fire.
        self.unpressable = {tuple(c) for c in (unpressable or ())}

    # ------------------------------------------------------------------ lookup
    def cell(self, keycode):
        """(row, col) for a key, or None if it was never mapped."""
        return self.key_to_cell.get(keycode)

    def mapped_cells(self):
        return set(self.key_to_cell.values())

    def unmapped_cells(self):
        """Cells with no key and not explicitly marked - i.e. still unknown."""
        known = self.mapped_cells() | self.unpressable
        return [(r, c) for r in range(self.rows) for c in range(self.cols)
                if (r, c) not in known]

    # ------------------------------------------------------------------- io
    @classmethod
    def load(cls, path):
        from evdev import ecodes

        with open(path) as fh:
            raw = json.load(fh)

        key_to_cell = {}
        unknown = []
        for name, cell in raw.get("keys", {}).items():
            code = ecodes.ecodes.get(name)
            if code is None:
                unknown.append(name)
                continue
            key_to_cell[code] = tuple(cell)

        if unknown:
            raise ValueError(
                "layout %s names keys this kernel does not know: %s"
                % (path, ", ".join(sorted(unknown)))
            )

        return cls(
            rows=raw["rows"],
            cols=raw["cols"],
            key_to_cell=key_to_cell,
            unpressable=raw.get("unpressable", []),
            name=raw.get("name", os.path.basename(path)),
        )

    def save(self, path):
        from evdev import ecodes

        keys = {}
        for code, cell in sorted(self.key_to_cell.items(), key=lambda kv: kv[1]):
            name = ecodes.KEY.get(code)
            if isinstance(name, (list, tuple)):   # aliased codes, e.g. KEY_MIN_INTERESTING
                name = name[0]
            if name is None:
                continue
            keys[name] = list(cell)

        payload = {
            "name": self.name or "blackwidow_v3",
            "rows": self.rows,
            "cols": self.cols,
            "keys": keys,
            "unpressable": [list(c) for c in sorted(self.unpressable)],
        }
        tmp = path + ".tmp"
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(tmp, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, path)   # never leave a half-written layout behind


def load_or_none(path):
    """Layout if it exists and parses, else None. Missing layouts are normal
    before mapping - the layout-free effects still run."""
    if not os.path.exists(path):
        return None
    return Layout.load(path)
