# Layouts

`blackwidow_v3.json` is generated on the Pi by `tools/map_keys.py`. It is not
checked in until you have made it, because there is no way to derive it: Razer
exposes a 6x22 grid and never says which cell sits under which key, and the
answer differs between ANSI, ISO and AZERTY boards.

Shape:

```json
{
  "name": "blackwidow_v3",
  "rows": 6,
  "cols": 22,
  "keys":        { "KEY_ESC": [0, 0], "KEY_A": [3, 1] },
  "unpressable": [[5, 4], [5, 5]]
}
```

`unpressable` is cells that have an LED but no working key — decorative strips,
and the broken spacebar. Effects still paint them; they just never fire.

Commit this file once you have it. It is the one part of the project that costs
an evening of manual work to reproduce.
