#!/usr/bin/env python3
"""Phase 0 gate. Nothing downstream matters until this passes.

    python3 tools/detect.py
    python3 tools/detect.py --reactive     # firmware glow, no custom code
"""
import argparse
import sys

import _bootstrap  # noqa: F401


def check_openrazer():
    print("== OpenRazer ==")
    try:
        from openrazer.client import DeviceManager
    except ImportError as exc:
        print("  FAIL: python3-openrazer not importable (%s)" % exc)
        return None

    try:
        manager = DeviceManager()
    except Exception as exc:
        print("  FAIL: cannot reach openrazer-daemon (%s)" % exc)
        print("        try: systemctl --user status openrazer-daemon")
        return None

    if not manager.devices:
        print("  FAIL: daemon is up but sees no devices.")
        print("        check: lsusb | grep -i 1532     (024e = BlackWidow V3)")
        print("               lsmod | grep razer")
        print("               groups | grep plugdev    (reboot after install)")
        return None

    chosen = None
    for dev in manager.devices:
        fx = getattr(dev.fx, "advanced", None)
        dims = "%dx%d" % (fx.rows, fx.cols) if fx else "no matrix"
        print("  %-40s serial=%-12s %s" % (dev.name, dev.serial, dims))
        if fx and (chosen is None or fx.rows * fx.cols > chosen[1].rows * chosen[1].cols):
            chosen = (dev, fx)

    if chosen is None:
        print("  FAIL: no device exposes an addressable matrix.")
        return None

    dev, fx = chosen
    print("  OK: using %s at %dx%d" % (dev.name, fx.rows, fx.cols))
    if (fx.rows, fx.cols) != (6, 22):
        print("  NOTE: expected 6x22 for a full-size BlackWidow V3; adjust if yours differs.")
    return dev


def check_evdev():
    print("\n== Input nodes ==")
    try:
        from evdev import InputDevice, list_devices, ecodes
    except ImportError as exc:
        print("  FAIL: python3-evdev not importable (%s)" % exc)
        return False

    matched = 0
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except OSError as exc:
            print("  %-20s cannot open: %s" % (path, exc))
            continue
        if ecodes.EV_KEY not in dev.capabilities():
            dev.close()
            continue
        is_razer = "razer" in dev.name.lower()
        status = ""
        if is_razer:
            matched += 1
            try:
                dev.grab()
                dev.ungrab()
                status = "grabbable"
            except OSError as exc:
                status = "NOT GRABBABLE: %s" % exc
        print("  %-20s %-45s %s" % (path, dev.name, status))
        dev.close()

    if not matched:
        print("  FAIL: no input node with 'razer' in the name.")
        return False
    print("  OK: %d razer node(s); all of them must be grabbed or keystrokes leak." % matched)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reactive", action="store_true",
                    help="set the firmware reactive effect and exit")
    ap.add_argument("--off", action="store_true", help="turn the lighting off")
    args = ap.parse_args()

    device = check_openrazer()
    inputs = check_evdev()

    if device is not None and args.off:
        device.fx.none()
        print("\nlighting off")
        return 0

    if device is not None and args.reactive:
        # 2 == 1000ms fade. Runs entirely in the keyboard; costs us nothing and
        # keeps working even if this project never gets further.
        device.fx.reactive(0, 255, 255, 2)
        print("\nreactive effect set - press keys, they should glow cyan and fade")
        return 0

    print()
    if device is None or not inputs:
        print("NOT READY - fix the FAILs above before going further.")
        return 1
    print("READY - both paths work. Next: python3 tools/bench.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
