#!/usr/bin/env bash
# Kidboard bootstrap for Raspberry Pi OS (64-bit, Bookworm or later).
# Run on the Pi:  bash setup/install.sh
set -euo pipefail

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !  %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] && die "Run as your normal user, not root. It will sudo where needed."

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_USER="$USER"

# ---------------------------------------------------------------- kernel headers
# Raspberry Pi OS does NOT use the stock Debian linux-headers-* naming, and the old
# raspberrypi-kernel-headers package is stale (built for 5.4). DKMS needs
# /lib/modules/$(uname -r)/build to resolve or the driver build fails.
log "Detecting kernel flavour"
KREL="$(uname -r)"
case "$KREL" in
  *-2712)  HEADERS_PKG="linux-headers-rpi-2712" ;;   # Pi 5
  *-v8*)   HEADERS_PKG="linux-headers-rpi-v8"   ;;   # Pi 4 / Pi 3, 64-bit
  *-v7l*|*-v7*) die "32-bit kernel detected ($KREL). Reinstall Raspberry Pi OS 64-bit." ;;
  *)       HEADERS_PKG="linux-headers-rpi-v8"
           warn "Unrecognised kernel '$KREL', guessing $HEADERS_PKG" ;;
esac
echo "kernel=$KREL  headers=$HEADERS_PKG"

log "Installing packages"
sudo apt-get update
sudo apt-get install -y \
  "$HEADERS_PKG" dkms build-essential \
  openrazer-driver-dkms openrazer-daemon python3-openrazer \
  python3-evdev python3-numpy python3-dbus python3-gi

# DKMS only links against headers it can find. Verify before trusting the build.
if [[ ! -e "/lib/modules/$KREL/build" ]]; then
  die "/lib/modules/$KREL/build is missing — headers did not match the running kernel.
     Try: sudo apt full-upgrade && sudo reboot, then re-run this script."
fi

log "Checking the razerkbd module built"
if ! dkms status 2>/dev/null | grep -qi 'openrazer.*installed'; then
  warn "DKMS does not report openrazer as installed. Falling back to a source build."
  warn "See setup/README-fallback.md if this also fails."
  dkms status || true
fi

# ---------------------------------------------------------------- groups
# plugdev: openrazer-daemon talks to the device.
# input:   we read (and exclusively grab) /dev/input/event*.
log "Adding $TARGET_USER to plugdev and input"
sudo gpasswd -a "$TARGET_USER" plugdev
sudo gpasswd -a "$TARGET_USER" input

# ---------------------------------------------------------------- service
log "Installing systemd unit"
sudo install -m 0644 "$REPO_DIR/setup/kidboard.service" /etc/systemd/system/kidboard.service
sudo sed -i "s|@USER@|$TARGET_USER|g; s|@REPO@|$REPO_DIR|g; s|@UID@|$(id -u)|g" /etc/systemd/system/kidboard.service
sudo systemctl daemon-reload
sudo systemctl enable kidboard.service

cat <<'NEXT'

--------------------------------------------------------------------
Installed. Two things left, both matter:

 1. REBOOT. The kernel module and your new group membership both
    need it. Nothing below works until you do.

 2. Turn OFF console autologin:
        sudo raspi-config
        -> 1 System Options -> S5 Boot / Auto Login -> B1 Console
    This is the backstop. If the kidboard service ever dies, the
    keyboard grab is released and keystrokes reach the TTY. With
    autologin on, that is a toddler typing into a live shell.

After rebooting, verify in this order:
        python3 tools/detect.py          # must print RazerBlackWidowV3, 6x22
        python3 tools/detect.py --reactive   # keys should glow when pressed
        python3 tools/bench.py           # want >= 25 fps
--------------------------------------------------------------------
NEXT
