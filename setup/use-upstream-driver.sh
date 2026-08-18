#!/usr/bin/env bash
# Replace the packaged driver source with upstream master's, keeping Debian's
# version number.
#
# Why: Debian's openrazer-driver-dkms 3.10.2 predates several kernel API
# changes and will not compile against 6.18. We hit two in a row -
# hid_report_raw_event gaining an argument, then hrtimer_init being removed -
# and patching them one at a time invites a third. Upstream carries properly
# version-gated fixes for all of them.
#
# Why not install upstream wholesale: openrazer-daemon depends on the exact
# openrazer-driver-dkms version, so purging the driver package drags the daemon
# and python library with it. Reusing Debian's version number keeps all three
# packages installed and apt consistent. The daemon only reports driver_version,
# it never gates on it, so the newer driver is fine underneath it.
#
#   bash setup/use-upstream-driver.sh
set -euo pipefail

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !  %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

CLONE_DIR="${CLONE_DIR:-$HOME/openrazer-upstream}"

log "Locating the packaged driver source"
SRC_DIR="$(ls -d /usr/src/openrazer-driver-* 2>/dev/null | head -1 || true)"
[[ -n "$SRC_DIR" ]] || die "no /usr/src/openrazer-driver-* found. Is openrazer-driver-dkms installed?"
DEB_VER="$(basename "$SRC_DIR" | sed 's/^openrazer-driver-//')"
echo "   $SRC_DIR  (version $DEB_VER)"

log "Build dependencies"
sudo apt-get install -y git dkms build-essential

log "Fetching upstream openrazer"
if [[ -d "$CLONE_DIR/.git" ]]; then
  git -C "$CLONE_DIR" fetch --depth 1 origin master
  git -C "$CLONE_DIR" reset --hard origin/master
else
  git clone --depth 1 https://github.com/openrazer/openrazer.git "$CLONE_DIR"
fi
UPSTREAM_VER="$(sed -n 's/^DKMS_VER?*=//p' "$CLONE_DIR/Makefile" | head -1)"
echo "   upstream driver version: ${UPSTREAM_VER:-unknown}"

log "Backing up the packaged source"
BACKUP="/usr/src/openrazer-driver-$DEB_VER.debian-backup"
if [[ ! -d "$BACKUP" ]]; then
  sudo cp -a "$SRC_DIR" "$BACKUP"
  echo "   $BACKUP"
else
  echo "   $BACKUP already exists, keeping the original"
fi

log "Installing upstream sources as version $DEB_VER"
# Clear first so files upstream removed do not linger and get compiled.
sudo rm -rf "$SRC_DIR"
sudo make -C "$CLONE_DIR" setup_dkms "DKMS_VER=$DEB_VER"
# dkms.conf ships upstream's version hardcoded; DKMS requires it to match the
# directory name, which must stay at Debian's version.
sudo sed -i "s/^PACKAGE_VERSION=.*/PACKAGE_VERSION=\"$DEB_VER\"/" "$SRC_DIR/dkms.conf"
grep -H PACKAGE_VERSION "$SRC_DIR/dkms.conf"

log "Clearing stale DKMS state"
sudo dkms remove "openrazer-driver/$DEB_VER" --all >/dev/null 2>&1 || true

log "Building, and letting dpkg finish what it started"
sudo dpkg --configure -a
sudo apt-get -f install -y

log "Result"
dkms status || true
echo
if dkms status 2>/dev/null | grep -qi 'openrazer.*installed'; then
  echo "   driver built OK"
else
  die "still failing. Read /var/lib/dkms/openrazer-driver/$DEB_VER/build/make.log
     To restore Debian's original source:
       sudo rm -rf $SRC_DIR && sudo mv $BACKUP $SRC_DIR"
fi

remaining="$(dpkg -l | awk '$1 ~ /^i[^i]/ {print $2}' || true)"
if [[ -n "$remaining" ]]; then
  die "still unconfigured: $remaining"
fi
echo "   all packages configured - safe to reboot"

cat <<'NEXT'

--------------------------------------------------------------------
Next:
    sudo reboot
    cd ~/kidboard && python3 tools/detect.py
--------------------------------------------------------------------
NEXT
