#!/usr/bin/env bash
# Recover from the openrazer-driver-dkms build failure on kernel >= 6.18.33.
#
# The DKMS hook runs from every kernel postinst, so a failing openrazer build
# leaves linux-image-* and linux-headers-* unconfigured too. Do not reboot with
# dpkg in that state - fix it here first.
#
#   bash setup/recover.sh
set -euo pipefail

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !  %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m !! %s\033[0m\n' "$*" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_REV="$(git -C "$HERE/.." rev-parse --short HEAD 2>/dev/null || echo not-a-git-checkout)"
printf '\033[2mkidboard %s @ %s\033[0m\n' "$(basename "${BASH_SOURCE[0]}")" "$REPO_REV"


log "Packages currently not configured"
# 'iU' / 'iF' in the first two columns means unpacked-but-not-configured.
dpkg -l | awk '$1 ~ /^i[^i]/ {print "   " $1 " " $2}' || true

log "Patching the packaged driver for the 6-argument hid_report_raw_event"
sudo python3 "$HERE/fix-hid-6arg.py"

log "Rebuilding the module"
# Clear any half-added DKMS state so the rebuild starts clean.
for ver in $(dkms status 2>/dev/null | sed -n 's/^openrazer-driver[/,] *\([0-9.]*\).*/\1/p' | sort -u); do
  echo "   removing stale dkms state for openrazer-driver/$ver"
  sudo dkms remove "openrazer-driver/$ver" --all >/dev/null 2>&1 || true
done

log "Configuring the packages dpkg left behind"
# With the source patched, the postinst DKMS hook now succeeds, which lets the
# kernel packages finish configuring too.
# Non-fatal: the verification below reports what actually happened.
sudo dpkg --configure -a || true
sudo apt-get -f install -y || true

log "Result"
dkms status || true
echo
if dkms status 2>/dev/null | grep -qi 'openrazer.*installed'; then
  echo "   driver built OK"
else
  warn "driver still not installed - read /var/lib/dkms/openrazer-driver/*/build/make.log"
  warn "and see setup/README-fallback.md for the build-from-git route."
fi

remaining="$(dpkg -l | awk '$1 ~ /^i[^i]/ {print $2}' || true)"
if [[ -n "$remaining" ]]; then
  die "still unconfigured: $remaining
     Do not reboot yet. Run: sudo dpkg --configure -a"
fi
echo "   all packages configured - safe to reboot"

cat <<'NEXT'

--------------------------------------------------------------------
Next:
    sudo reboot
    python3 tools/detect.py
--------------------------------------------------------------------
NEXT
