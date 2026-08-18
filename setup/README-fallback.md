# When the packaged driver is too old

Raspberry Pi OS pulls OpenRazer from Debian, which can lag. If `tools/detect.py`
reports no devices but `lsusb` shows `1532:024e`, the packaged driver predates
your keyboard. Build from source instead:

```bash
sudo apt-get remove -y openrazer-driver-dkms openrazer-daemon python3-openrazer
sudo apt-get install -y git dkms build-essential python3-dbus python3-gi python3-setuptools
git clone https://github.com/openrazer/openrazer.git ~/openrazer
cd ~/openrazer
sudo make setup_dkms install_files udev_install
sudo make python_library_install daemon_install
sudo reboot
```

## Reading a failed DKMS build

```bash
dkms status
sudo dmesg | grep -i razer
cat /var/lib/dkms/openrazer-driver/*/build/make.log
```

The failure mode people hit on ARM is a *kernel version* mismatch, not
architecture — errors like `struct hid_driver has no member named 'match'` mean
the driver expects a different kernel API than the one you are running. Fix by
updating the kernel (`sudo apt full-upgrade && sudo reboot`) or by building the
driver from git master, which tracks newer kernels.

## Confirming the hardware is even seen

```bash
lsusb | grep -i 1532        # 1532 is Razer; 024e is BlackWidow V3
lsmod | grep razer          # razerkbd should be loaded
ls /sys/bus/hid/drivers/razerkbd/
```
