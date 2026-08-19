#!/usr/bin/env python3
"""Print raw key events with the node that reported them.

Use this when the mapper behaves as if you pressed a key twice. Razer keyboards
expose several event nodes and kidboard grabs all of them on purpose; if more
than one reports the same physical key, a single press arrives as two events.

    python3 tools/keydebug.py

Anything flagged DUPLICATE is the same keycode from a different node within the
dedupe window - that is the thing to fix, not something you did.
"""
import argparse
import select
import sys
import time

import _bootstrap  # noqa: F401
from kidboard import config
from kidboard.keyboard_input import KeyStream

WINDOW = 0.05      # seconds within which a repeat of the same key is suspicious


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", type=float, default=WINDOW)
    args = ap.parse_args()

    last = {}          # keycode -> (time, source)
    duplicates = 0
    total = 0

    with KeyStream(match=config.DEVICE_MATCH) as keys:
        time.sleep(0.6)
        keys.poll()
        print("grabbed:")
        for name in keys.grabbed_names:
            print("   " + name)
        print("\npress keys. Enter in this terminal to stop.\n")

        while True:
            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                break

            for event in keys.poll():
                if not event.down:
                    continue
                total += 1
                flag = ""
                previous = last.get(event.code)
                if previous and event.at - previous[0] < args.window:
                    duplicates += 1
                    flag = "  <-- DUPLICATE, %.0f ms after %s" % (
                        (event.at - previous[0]) * 1e3, previous[1])
                last[event.code] = (event.at, event.source)
                print("  %-18s %-22s%s" % (event.name, event.source, flag))

            time.sleep(0.01)

    print("\n%d press events, %d duplicates" % (total, duplicates))
    if duplicates:
        print("Confirmed: one physical press is arriving more than once.")
    else:
        print("No duplicates seen - the mapper problem is something else.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
