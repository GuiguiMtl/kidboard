#!/usr/bin/env python3
"""Measure key chatter and pick a debounce window.

This keyboard registers a single physical press several times - a known fault
of the V3 Mini. Run this, press keys normally, and it reports how far apart the
repeats actually are, so KIDBOARD_DEBOUNCE_MS is chosen from measurement rather
than guesswork.

    python3 tools/keydebug.py              # raw stream, no filtering
    python3 tools/keydebug.py --debounce 60  # check a candidate window

Press each key once, deliberately, maybe twenty times across the board. Do not
double-tap on purpose - that is what we are trying to tell apart from chatter.
"""
import argparse
import select
import sys
import time

import _bootstrap  # noqa: F401
from kidboard import config
from kidboard.keyboard_input import KeyStream

# A repeat further apart than this is treated as a real second press, not
# chatter, and is excluded from the recommendation.
REAL_PRESS_MS = 250.0


def percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction) - 1))
    return ordered[index]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--debounce", type=int, default=0,
                    help="ms; 0 (default) shows the unfiltered stream")
    args = ap.parse_args()

    last = {}
    gaps = []
    presses = 0
    sources = {}

    with KeyStream(match=config.DEVICE_MATCH, debounce_ms=args.debounce) as keys:
        time.sleep(0.6)
        keys.poll()
        print("grabbed:")
        for name in keys.grabbed_names:
            print("   " + name)
        print("\ndebounce: %s" % ("off" if not args.debounce else "%d ms" % args.debounce))
        print("press keys one at a time. Enter in this terminal to stop.\n")

        while True:
            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                break

            for event in keys.poll():
                if not event.down:
                    continue
                presses += 1
                sources[event.source] = sources.get(event.source, 0) + 1
                note = ""
                previous = last.get(event.code)
                if previous is not None:
                    gap_ms = (event.at - previous) * 1e3
                    if gap_ms < REAL_PRESS_MS:
                        gaps.append(gap_ms)
                        note = "  <-- repeat %.0f ms after the last one" % gap_ms
                last[event.code] = event.at
                print("  %-18s %-22s%s" % (event.name, event.source, note))

            time.sleep(0.01)

    print("\n%d press events, %d suppressed by debounce" % (presses, keys.suppressed))

    if len(sources) > 1:
        print("\nreported by %d nodes - counts per node:" % len(sources))
        for path, count in sorted(sources.items()):
            print("   %-22s %d" % (path, count))

    if not gaps:
        print("\nNo repeats under %.0f ms." % REAL_PRESS_MS)
        if args.debounce:
            print("Debounce of %d ms is holding. Keep it." % args.debounce)
        else:
            print("This keyboard is not chattering right now.")
        return 0

    worst = max(gaps)
    p95 = percentile(gaps, 0.95)
    print("\n%d repeat(s) under %.0f ms" % (len(gaps), REAL_PRESS_MS))
    print("   median %.0f ms   p95 %.0f ms   worst %.0f ms"
          % (percentile(gaps, 0.5), p95, worst))

    # Clear the worst observed bounce, with headroom, but stay well under a
    # deliberate double-tap so real fast presses are never eaten.
    recommended = int(min(150, max(40, worst * 1.5 + 10)))
    print("\nSuggested:  KIDBOARD_DEBOUNCE_MS=%d" % recommended)
    print("Set it in setup/kidboard.service, or export it to try it out.")
    if worst > 150:
        print("\nNote: a %.0f ms bounce is large. That switch may be failing;" % worst)
        print("a debounce that long will start to feel unresponsive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
