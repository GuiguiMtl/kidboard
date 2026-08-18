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

## Debian 3.10.2 is too old for kernel 6.18 - use upstream's driver

The `hid_report_raw_event` fix above gets `razerkbd` compiling, and then the
build fails again in `razermouse_driver.c`:

```
razermouse_driver.c:4941:5: error: implicit declaration of function 'hrtimer_init';
                            did you mean 'hrtimers_init'?
```

Kernel 6.13 replaced `hrtimer_init()` + `.function =` with `hrtimer_setup()`,
and 6.18 removed the old call entirely. That is the second kernel API break in
one build, and 3.10.2 predates a good few more. Stop patching individually:

```bash
bash setup/use-upstream-driver.sh
```

This installs upstream master's driver sources into Debian's DKMS version slot.
You get every upstream kernel fix at once, all properly version-gated:

| Break | Upstream gate |
|---|---|
| `hid_report_raw_event` 6 args | `>= 6.18.33 && < 6.19`, plus 7.1, 7.0.10, 6.12.93, 6.6.143, 6.1.176, 5.15.210, 5.10.259 |
| `hrtimer_setup` | `>= 6.13.0` |

Debian's version number is reused deliberately. `openrazer-daemon` depends on
the *exact* `openrazer-driver-dkms` version, so purging the driver package drags
the daemon and python library out with it; keeping the number lets all three
stay installed and apt stay consistent. `dkms.conf` ships upstream's version
hardcoded, so the script rewrites it to match the directory name - DKMS requires
those to agree. The daemon only ever reports `driver_version`, it never gates on
it, so a newer driver underneath an older daemon is fine.

The script keeps Debian's original tree at
`/usr/src/openrazer-driver-<ver>.debian-backup`. To go back:

```bash
sudo rm -rf /usr/src/openrazer-driver-<ver>
sudo mv /usr/src/openrazer-driver-<ver>.debian-backup /usr/src/openrazer-driver-<ver>
sudo dpkg --configure -a
```

## Full upstream install

Only if you want upstream's daemon too. It replaces the Debian packages, so apt
no longer manages OpenRazer, and `daemon_install` runs `python3 setup.py
install`, which modern setuptools may refuse.

```bash
sudo apt-get remove -y openrazer-driver-dkms openrazer-daemon python3-openrazer
sudo apt-get install -y git dkms build-essential python3-dbus python3-gi python3-setuptools python3-daemonize
git clone https://github.com/openrazer/openrazer.git ~/openrazer
cd ~/openrazer
sudo make setup_dkms udev_install daemon_install python_library_install
sudo dkms install "openrazer-driver/$(sed -n 's/^DKMS_VER?*=//p' Makefile | head -1)"
sudo reboot
```

There is no `install_files` target despite what many guides say; the real ones
are `setup_dkms`, `udev_install`, `daemon_install`, `python_library_install`.

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
