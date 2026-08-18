#!/usr/bin/env python3
"""How fast can we actually push full frames over DBus?

The plan's gate is >= 25 fps. Below that, drop kidboard's FPS to 20 (fades still
look smooth) before considering anything more exotic.
"""
import argparse
import sys
import time

import numpy as np

import _bootstrap  # noqa: F401
from kidboard.device import Keyboard, NoDeviceError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--brightness", type=int, default=40)
    args = ap.parse_args()

    try:
        kbd = Keyboard(brightness=args.brightness)
    except NoDeviceError as exc:
        print("FAIL: %s" % exc)
        return 1

    print("%s  %dx%d  %d frames" % (kbd.name, kbd.rows, kbd.cols, args.frames))
    buf = np.zeros((kbd.rows, kbd.cols, 3), dtype=np.float32)

    times = []
    for i in range(args.frames):
        # Vary every pixel so nothing can short-circuit on an unchanged frame.
        phase = i / 30.0
        buf[:, :, 0] = (np.sin(phase) * 0.5 + 0.5)
        buf[:, :, 1] = (np.sin(phase + 2.1) * 0.5 + 0.5)
        buf[:, :, 2] = (np.sin(phase + 4.2) * 0.5 + 0.5)
        start = time.monotonic()
        kbd.draw(buf)
        times.append(time.monotonic() - start)

    times.sort()
    mean = sum(times) / len(times)
    p95 = times[int(len(times) * 0.95) - 1]
    worst = times[-1]

    print("\nper-frame draw:  mean %.1f ms   p95 %.1f ms   worst %.1f ms"
          % (mean * 1e3, p95 * 1e3, worst * 1e3))
    print("sustainable:     %.1f fps (mean)   %.1f fps (p95)" % (1 / mean, 1 / p95))

    kbd.off()
    if 1 / p95 >= 25:
        print("\nOK - 30 fps is fine.")
        return 0
    if 1 / p95 >= 18:
        print("\nMARGINAL - run with KIDBOARD_FPS=20.")
        return 0
    print("\nSLOW - check the Pi is not thermally throttled and the daemon is idle.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
