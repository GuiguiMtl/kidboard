#!/usr/bin/env python3
"""Check the mapping is actually right before building effects on top of it.

    python3 tools/verify_layout.py            # press keys, watch the right LED light
    python3 tools/verify_layout.py --sweep    # walk every mapped cell in order

Press mode is the honest test: it exercises the same lookup the real effects
use, and it tells you at the end which keys you never got round to pressing.
"""
import argparse
import select
import sys
import time

import numpy as np

import _bootstrap  # noqa: F401
from kidboard import config
from kidboard.device import Keyboard, NoDeviceError
from kidboard.keyboard_input import KeyStream
from kidboard.layout import load_or_none


def report_static(layout):
    print("layout %s: %dx%d, %d keys, %d dead cells, %d unknown cells"
          % (layout.name, layout.rows, layout.cols, len(layout.key_to_cell),
             len(layout.unpressable), len(layout.unmapped_cells())))

    from evdev import ecodes
    by_cell = {}
    for code, cell in layout.key_to_cell.items():
        by_cell.setdefault(cell, []).append(code)
    clashes = {cell: codes for cell, codes in by_cell.items() if len(codes) > 1}
    if clashes:
        print("\n!! %d cell(s) claimed by more than one key - remap these:" % len(clashes))
        for cell, codes in sorted(clashes.items()):
            names = ", ".join(str(ecodes.KEY.get(c, c)) for c in codes)
            print("   row %d col %2d : %s" % (cell[0], cell[1], names))

    unknown = layout.unmapped_cells()
    if unknown:
        print("\n%d cell(s) never identified (they will stay dark under splash/paint):"
              % len(unknown))
        print("   " + ", ".join("%d/%d" % c for c in unknown[:24])
              + (" ..." if len(unknown) > 24 else ""))
    return not clashes


def sweep(kbd, layout, delay):
    from evdev import ecodes

    buf = np.zeros((kbd.rows, kbd.cols, 3), dtype=np.float32)
    cells = sorted(layout.key_to_cell.items(), key=lambda kv: kv[1])
    print("\nsweeping %d mapped cells - watch for a key lighting out of order\n"
          % len(cells))
    for code, cell in cells:
        buf[:] = 0.01
        buf[cell[0], cell[1]] = (1.0, 1.0, 1.0)
        kbd.draw(buf)
        name = ecodes.KEY.get(code, code)
        if isinstance(name, (list, tuple)):
            name = name[0]
        print("  row %d col %2d  %s" % (cell[0], cell[1], name))
        time.sleep(delay)
    kbd.off()


def press(kbd, layout):
    buf = np.zeros((kbd.rows, kbd.cols, 3), dtype=np.float32)
    confirmed = set()
    unmapped = set()
    last_seen = {}
    DEDUPE = 0.05      # one press can be reported by several nodes

    print("\npress keys on the Razer keyboard. Enter in this terminal to finish.\n")
    with KeyStream(match=config.DEVICE_MATCH) as keys:
        time.sleep(0.6)
        keys.poll()
        while True:
            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                break

            for event in keys.poll():
                if not event.down:
                    continue
                previous = last_seen.get(event.code)
                if previous is not None and event.at - previous < DEDUPE:
                    continue           # same press, second node
                last_seen[event.code] = event.at
                cell = layout.cell(event.code)
                if cell is None:
                    unmapped.add(event.name)
                    buf[:] = (0.15, 0.0, 0.0)      # whole board red: not mapped
                    print("  %-18s NOT MAPPED" % event.name)
                else:
                    confirmed.add(event.code)
                    buf[:] = 0.01
                    buf[cell[0], cell[1]] = (0.0, 1.0, 0.4)
                    print("  %-18s row %d col %2d" % (event.name, cell[0], cell[1]))
                kbd.draw(buf)

            time.sleep(0.02)

    kbd.off()

    from evdev import ecodes
    missed = set(layout.key_to_cell) - confirmed
    print("\n%d/%d mapped keys confirmed" % (len(confirmed), len(layout.key_to_cell)))
    if missed:
        names = sorted(str(ecodes.KEY.get(c, c)) for c in missed)
        print("never pressed: " + ", ".join(names))
    if unmapped:
        print("\n!! keys with no mapping (rerun tools/map_keys.py): "
              + ", ".join(sorted(unmapped)))
    return not unmapped


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", default=config.LAYOUT_PATH)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--delay", type=float, default=0.35)
    args = ap.parse_args()

    layout = load_or_none(args.layout)
    if layout is None:
        print("no layout at %s - run tools/map_keys.py first" % args.layout)
        return 1

    clean = report_static(layout)

    try:
        kbd = Keyboard(brightness=70)
    except NoDeviceError as exc:
        print("FAIL: %s" % exc)
        return 1

    if args.sweep:
        sweep(kbd, layout, args.delay)
        return 0 if clean else 1

    ok = press(kbd, layout)
    return 0 if (ok and clean) else 1


if __name__ == "__main__":
    sys.exit(main())
