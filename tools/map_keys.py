#!/usr/bin/env python3
"""Build the key -> LED cell mapping. Run this over SSH.

The keyboard is grabbed, so its keys reach only this tool; your SSH terminal is
driven from your PC's keyboard. That split is what makes the prompts
unambiguous - typing 'q' at the terminal is never confused with mapping the Q
key on the Razer.

    python3 tools/map_keys.py            # resumes an existing layout
    python3 tools/map_keys.py --restart  # start from an empty mapping

At each step one LED lights. Press the key underneath it on the Razer keyboard.
If no key sits there, press Enter in the terminal.
"""
import argparse
import os
import select
import sys
import time

import numpy as np

import _bootstrap  # noqa: F401
from kidboard import config
from kidboard.device import Keyboard, NoDeviceError
from kidboard.keyboard_input import KeyStream
from kidboard.layout import Layout, load_or_none

AUTOSAVE_EVERY = 8

# A press must be followed by this much silence before the next cell is shown.
# Razer keyboards report through several event nodes and kidboard grabs all of
# them, so one physical press can arrive more than once. Without a settle, the
# duplicate lands on the next cell and skips it - which shows up later as keys
# that were never mapped.
SETTLE_QUIET = 0.30
SETTLE_TIMEOUT = 3.0
HELP = """
  <press a key on the Razer>  map it to the lit cell
  Enter                       no key here (decorative LED or dead cell)
  u                           undo the last answer
  s                           skip this cell, decide later
  q                           save and quit
  ?                           this help
"""


def draw_single(kbd, buf, cell):
    buf[:] = 0.015                      # faint wash, so the board reads as alive
    buf[cell[0], cell[1]] = (1.0, 1.0, 1.0)
    kbd.draw(buf)


def settle(keys):
    """Drain events until the keyboard has been quiet for SETTLE_QUIET."""
    deadline = time.monotonic() + SETTLE_TIMEOUT
    last_seen = time.monotonic()
    while time.monotonic() < deadline:
        if keys.poll():
            last_seen = time.monotonic()
        elif time.monotonic() - last_seen >= SETTLE_QUIET:
            return
        time.sleep(0.01)


def stdin_line():
    if not select.select([sys.stdin], [], [], 0)[0]:
        return None
    line = sys.stdin.readline()
    if line == "":
        return "q"                      # EOF, e.g. the pipe closed
    return line.strip().lower()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", default=config.LAYOUT_PATH)
    ap.add_argument("--restart", action="store_true", help="ignore any existing layout")
    args = ap.parse_args()

    try:
        kbd = Keyboard(brightness=70)
    except NoDeviceError as exc:
        print("FAIL: %s" % exc)
        return 1

    layout = None if args.restart else load_or_none(args.layout)
    if layout is None:
        layout = Layout(kbd.rows, kbd.cols, name="blackwidow_v3")
    elif (layout.rows, layout.cols) != (kbd.rows, kbd.cols):
        print("existing layout is %dx%d but the device is %dx%d - starting fresh"
              % (layout.rows, layout.cols, kbd.rows, kbd.cols))
        layout = Layout(kbd.rows, kbd.cols, name="blackwidow_v3")

    todo = layout.unmapped_cells()
    total = kbd.rows * kbd.cols
    if not todo:
        print("every cell is already accounted for in %s. Use --restart to redo."
              % args.layout)
        return 0

    print(__doc__)
    print("%d of %d cells left to identify.%s" % (len(todo), total, HELP))

    buf = np.zeros((kbd.rows, kbd.cols, 3), dtype=np.float32)
    history = []            # (cell, previous_cell_or_None, kind, keycode)
    index = 0
    answered = 0

    with KeyStream(match=config.DEVICE_MATCH) as keys:
        # Give the grab a moment, and drop anything typed before we were ready.
        time.sleep(0.6)
        keys.poll()

        while index < len(todo):
            cell = todo[index]
            draw_single(kbd, buf, cell)
            sys.stdout.write("\r[%3d/%3d] row %d col %2d > "
                             % (index + 1, len(todo), cell[0], cell[1]))
            sys.stdout.flush()

            decided = False
            rewind = False
            while not decided:
                for event in keys.poll():
                    if not event.down:
                        continue
                    previous = layout.key_to_cell.get(event.code)
                    if previous is not None and previous != cell:
                        print("\n  note: %s was on row %d col %d; moving it here"
                              % (event.name, previous[0], previous[1]))
                    layout.key_to_cell[event.code] = cell
                    layout.unpressable.discard(cell)
                    history.append((cell, previous, "key", event.code))
                    print("%s" % event.name)
                    decided = True
                    break

                if decided:
                    break

                line = stdin_line()
                if line is None:
                    time.sleep(0.02)
                    continue

                if line == "":
                    layout.unpressable.add(cell)
                    history.append((cell, None, "unpressable", None))
                    print("  (no key)")
                    decided = True
                elif line == "s":
                    history.append((cell, None, "skip", None))
                    print("  (skipped)")
                    decided = True
                elif line == "u":
                    if not history:
                        print("  nothing to undo")
                        continue
                    prev_cell, prev_value, kind, code = history.pop()
                    if kind == "key":
                        layout.key_to_cell.pop(code, None)
                        if prev_value is not None:
                            layout.key_to_cell[code] = prev_value
                    elif kind == "unpressable":
                        layout.unpressable.discard(prev_cell)
                    print("  undid row %d col %d" % (prev_cell[0], prev_cell[1]))
                    rewind = True
                    decided = True
                elif line == "q":
                    layout.save(args.layout)
                    print("\nsaved %s (%d keys, %d dead cells, %d still unknown)"
                          % (args.layout, len(layout.key_to_cell),
                             len(layout.unpressable), len(layout.unmapped_cells())))
                    kbd.off()
                    return 0
                elif line == "?":
                    print(HELP)
                else:
                    print("  ? unrecognised - '?' for help")

            # Absorb the key-up, any duplicate report of the same press from
            # another node, and autorepeat, before moving to the next cell.
            settle(keys)

            if rewind:
                # Step back onto the cell whose answer we just threw away.
                index = max(0, index - 1)
                continue

            index += 1
            answered += 1
            if answered % AUTOSAVE_EVERY == 0:
                layout.save(args.layout)

    layout.save(args.layout)
    print("\n\ndone - saved %s" % args.layout)
    print("  %d keys mapped, %d cells with no key, %d unknown"
          % (len(layout.key_to_cell), len(layout.unpressable),
             len(layout.unmapped_cells())))
    print("\nNow check it:  python3 tools/verify_layout.py")
    kbd.off()
    return 0


if __name__ == "__main__":
    sys.exit(main())
