# Kidboard

A Razer BlackWidow V3 with a broken spacebar, turned into a light toy for a
toddler. Plugged into a headless Raspberry Pi: she bashes the keys, the board
reacts, and the keystrokes go **nowhere** — no shell, no TTY, nothing.

The keyboard is a 6x22 grid of addressable LEDs. That is the whole display.

## How it works

```
[keyboard] --evdev, exclusively grabbed--> input thread --> engine --> framebuffer
[keyboard] <--OpenRazer DBus, 30 fps------ draw loop <-----------------'
```

Input and output are separate paths that never meet. The exclusive grab
(`EVIOCGRAB`) is the safety property: the kernel stops delivering those events
to anyone else. Razer keyboards expose several event nodes and they all emit
keys, so `kidboard/keyboard_input.py` grabs every one of them.

## Setup on the Pi

Raspberry Pi OS 64-bit, Pi 4 or Pi 5.

```bash
bash setup/install.sh
sudo reboot
```

Then **turn off console autologin** — `sudo raspi-config` → System Options →
Boot / Auto Login → **Console**. This is the backstop: if the service dies the
grab is released, and with autologin on that means a toddler typing into a live
shell.

## If setup fails on the driver build

On Raspberry Pi OS with kernel >= 6.18.33, Debian's OpenRazer 3.10.2 does not
compile: `hid_report_raw_event` gained a sixth argument. The DKMS hook runs from
every kernel `postinst`, so this also leaves `linux-image-*` and `linux-headers-*`
unconfigured. **Do not reboot in that state.**

```bash
bash setup/recover.sh     # patches the driver, then dpkg --configure -a
```

`setup/install.sh` applies the same fix automatically. Details and the
build-from-git alternative are in `setup/README-fallback.md`.

## Bring-up order

Each step gates the next. Do not skip ahead.

| Step | Command | Expect |
|---|---|---|
| 1. Driver | `python3 tools/detect.py` | `RazerBlackWidowV3`, `6x22`, grabbable nodes |
| 2. Lights | `python3 tools/detect.py --reactive` | keys glow cyan when pressed |
| 3. Speed | `python3 tools/bench.py` | ≥ 25 fps |
| 4. Run it | `python3 -m kidboard.main` | board reacts; SSH session stays empty |
| 5. Mapping | `python3 tools/map_keys.py` | `layouts/blackwidow_v3.json` |
| 6. Check | `python3 tools/verify_layout.py` | every key lights its own LED |
| 7. Service | `sudo systemctl start kidboard` | survives reboot |

Step 2 is the firmware's own reactive effect. It needs none of this code, and it
keeps working if everything else breaks.

Steps 4 and 5 are deliberately in that order — the layout-free effects (`flash`,
`rainbow`) run before any mapping exists, so the toy is usable the same evening
the driver comes up. Mapping unlocks `splash`, `ripple` and `paint`.

## Effects

| Name | Needs mapping | What it does |
|---|---|---|
| `flash` | no | whole board flashes a new colour on every key |
| `rainbow` | no | scrolling rainbow that speeds up as she types |
| `splash` | yes | pressed key lights and fades, spilling onto neighbours |
| `ripple` | yes | expanding rings from each key |
| `paint` | yes | every key keeps its colour; the board fills in |
| `sleep` | no | slow warm breath after 5 minutes idle |

Switching effects is adult-only: hold **Esc + Enter together for 3 seconds**.
Far apart on the board and behind a long hold, so palm-slapping will not trip
it. Also `sudo systemctl kill -s SIGUSR1 kidboard`, or `--effect NAME`.

## Working on it without hardware

```bash
python3 tools/selftest.py                    # no Pi, no keyboard
python3 tools/simulate.py --effect ripple    # renders the matrix in the terminal
```

`tools/simulate.py` swaps in a fake keyboard and a fake toddler, so effects can
be tuned anywhere.

## Deploying from Windows

```powershell
.\deploy.ps1 -Target pi@raspberrypi.local -Restart
.\deploy.ps1 -Target pi@raspberrypi.local -PullLayout   # after mapping
```

The layout is the one artefact you cannot regenerate without sitting at the
keyboard — pull it back and commit it.

## Tuning

Environment variables, no edits needed:

```bash
KIDBOARD_BRIGHTNESS=40 KIDBOARD_FPS=20 python3 -m kidboard.main
```

`KIDBOARD_IDLE_SECONDS`, `KIDBOARD_CHORD_HOLD`, `KIDBOARD_LAYOUT` too — see
`kidboard/config.py`.

## Two physical notes

- **Keycaps come off by hand** and a BlackWidow's are small enough to be a
  choking hazard. The broken spacebar may already leave a stabiliser exposed.
  Worth a look before it goes on a lap, and again now and then.
- **Use the official PSU** (Pi 4: 3 A, Pi 5: 5 V/5 A). Full-matrix RGB draws
  real current, and an undersized supply shows up as random USB dropouts rather
  than an obvious power error.

## Later

The 6x22 grid is a real low-res display. Around age 3, `kidboard/effects/` is
where whack-a-key, colour matching and Simon sequences plug in — same interface,
no rework needed.
