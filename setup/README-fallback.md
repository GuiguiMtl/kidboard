# When the driver will not build

## Known: kernel >= 6.18.33, `hid_report_raw_event` takes 6 arguments

Symptom in the apt output:

```
razerkbd_driver.c:3750:29: error: too few arguments to function 'hid_report_raw_event'
Error! Bad return status for module build on kernel: 6.18.39+rpt-rpi-2712 (aarch64)
dpkg: error processing package openrazer-driver-dkms (--configure)
```

Linux backported a signature change into stable kernels from **6.18.33**:

```c
hid_report_raw_event(hdev, type, data, size, 0);         /* old, 5 args */
hid_report_raw_event(hdev, type, data, size, size, 0);   /* new, 6 args */
```

Debian's openrazer-driver-dkms 3.10.2 still emits the old form. Upstream fixed
it in [PR #2843](https://github.com/openrazer/openrazer/pull/2843); Debian has
not picked it up yet.

**This also breaks your kernel packages.** DKMS runs from every kernel
`postinst`, so the failure leaves `linux-image-*` and `linux-headers-*`
unconfigured as well. Do not reboot in that state — fix dpkg first:

```bash
bash setup/recover.sh
```

That patches the packaged source, rebuilds the module, and runs
`dpkg --configure -a` so the kernel packages finish installing. It is
idempotent and keeps `.orig` backups. To undo the source change:

```bash
sudo python3 setup/fix-hid-6arg.py --revert
```

The patch is unconditional rather than version-gated. Every kernel this Pi will
run from here on is ≥ 6.18.39, so that is correct — but it would break a build
against a kernel older than 6.18.33, which is what the git route below avoids.

## Alternative: build from git master

Upstream carries a properly version-gated fix covering 5.10 through 7.1. Use
this if you would rather track upstream than carry a local patch. Note it
replaces the Debian daemon and python packages, because
`openrazer-daemon` depends on the exact `openrazer-driver-dkms` version.

```bash
sudo apt-get remove -y openrazer-driver-dkms openrazer-daemon python3-openrazer
sudo apt-get install -y git dkms build-essential python3-dbus python3-gi \
    python3-setuptools python3-daemonize
git clone https://github.com/openrazer/openrazer.git ~/openrazer
cd ~/openrazer
sudo make setup_dkms install_files udev_install
sudo make python_library_install daemon_install
sudo reboot
```

## Reading a failed build

```bash
dkms status
cat /var/lib/dkms/openrazer-driver/*/build/make.log
sudo dmesg | grep -i razer
```

Errors of the form "too few/many arguments" or "struct X has no member named Y"
are always a *kernel version* mismatch, never an ARM problem — the driver
expects a different kernel API than the one you are running.

## Confirming the hardware is seen at all

```bash
lsusb | grep -i 1532        # 1532 is Razer; 024e is BlackWidow V3
lsmod | grep razer          # razerkbd should be loaded
ls /sys/bus/hid/drivers/razerkbd/
```
