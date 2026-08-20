#!/usr/bin/env python3
"""Prove the keyboard grab is actually holding.

Run this over SSH *while kidboard is running*, then mash the Razer keyboard.

Watching your SSH session for stray characters proves nothing: SSH input comes
from the machine you are typing on, so the Pi's local keyboard could never
appear there whether the grab works or not. The real exposure is the Pi's own
console, tty1, which is invisible on a headless box.

This checks three things that are actually meaningful:

  1. Can another process still read the key events? If kidboard's grab holds,
     a passive reader sees nothing at all.
  2. Is anything reaching tty1? /dev/vcs1 is that console's screen contents,
     readable even with no monitor attached.
  3. Is console autologin on? If it is, a released grab means a live shell.

    sudo python3 tools/grabtest.py
"""
import argparse
import os
import select
import sys
import time

import _bootstrap  # noqa: F401
from kidboard import config


def razer_nodes():
    from evdev import InputDevice, list_devices, ecodes

    found = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except OSError:
            continue
        if ecodes.EV_KEY in dev.capabilities() and config.DEVICE_MATCH in dev.name.lower():
            found.append(dev)
        else:
            dev.close()
    return found


def read_console(index=1):
    """Current on-screen text of /dev/vcsN. Needs root."""
    try:
        with open("/dev/vcs%d" % index, "rb") as fh:
            raw = fh.read()
    except (OSError, PermissionError) as exc:
        return None, str(exc)
    text = raw.decode("utf-8", "replace")
    return " ".join(text.split()), None


def autologin_enabled():
    for path in ("/etc/systemd/system/getty@tty1.service.d/autologin.conf",
                 "/etc/systemd/system/getty@tty1.service.d/override.conf"):
        if os.path.exists(path):
            try:
                with open(path) as fh:
                    if "autologin" in fh.read():
                        return True, path
            except OSError:
                pass
    return False, None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=15.0)
    args = ap.parse_args()

    print("== Autologin ==")
    on, path = autologin_enabled()
    if on:
        print("  DANGER: console autologin is enabled (%s)" % path)
        print("  If kidboard ever stops, the keyboard types into a live shell.")
        print("  Fix: sudo raspi-config -> System Options -> Boot/Auto Login -> Console")
    else:
        print("  OK: no console autologin - a released grab lands on a login prompt")

    print("\n== Who holds the devices ==")
    devices = razer_nodes()
    if not devices:
        print("  FAIL: no Razer input nodes found")
        return 1

    held = 0
    for dev in devices:
        try:
            dev.grab()
            dev.ungrab()
            print("  %-20s %-40s FREE - nothing has grabbed this" % (dev.path, dev.name))
        except OSError:
            held += 1
            print("  %-20s %-40s held by another process" % (dev.path, dev.name))

    if held == len(devices):
        print("  OK: every node is grabbed (kidboard running?)")
    elif held:
        print("  WARNING: %d of %d nodes grabbed - the rest leak keystrokes"
              % (held, len(devices)))
    else:
        print("  WARNING: nothing is grabbed. Is kidboard running?")

    before, err = read_console()
    if err:
        print("\n== Console (tty1) ==\n  cannot read /dev/vcs1: %s" % err)
        print("  run with sudo to include this check")

    print("\n== Leak test ==")
    print("  Mash the Razer keyboard for %.0f seconds. Starting now." % args.seconds)

    # Passive read: no grab. A grabbed device delivers nothing to other readers.
    leaked = 0
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        ready, _, _ = select.select(devices, [], [], 0.2)
        for dev in ready:
            try:
                for event in dev.read():
                    from evdev import ecodes
                    if event.type == ecodes.EV_KEY and event.value == 1:
                        leaked += 1
            except OSError:
                pass

    print()
    if leaked:
        print("  LEAK: %d key press(es) reached a second reader." % leaked)
        print("  Those keystrokes are also reaching tty1.")
    else:
        print("  OK: no key events reached this process. The grab is holding.")

    if before is not None:
        after, _ = read_console()
        if after != before:
            print("\n  LEAK: the tty1 console changed while you typed.")
            print("    before: %s" % before[-160:])
            print("    after : %s" % after[-160:])
        else:
            print("  OK: tty1 console unchanged - nothing reached the console.")

    for dev in devices:
        dev.close()

    return 1 if leaked else 0


if __name__ == "__main__":
    sys.exit(main())
