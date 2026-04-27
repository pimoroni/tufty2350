# Patched Tufty 2350 firmware — coffee / dual-central edition

This branch (`m6.5-dual-central` on `zestuart/tufty2350`) is a fork of
[`pimoroni/tufty2350`](https://github.com/pimoroni/tufty2350) carrying
two patches plus a frozen MicroPython app, used to drive a live
brew-display from a Bookoo Mini Coffee Scale and a Bookoo Espresso
Monitor over BLE on one badge.

For the upstream Tufty 2350 README (specs, install, WiFi, API docs),
see `README.md` next to this file.  Everything here is the delta on
top.

## What this branch adds

### 1. btstack patch — concurrent dual-central

Upstream MicroPython hard-codes both `MAX_NR_HCI_CONNECTIONS` and
`MAX_NR_GATT_CLIENTS` to **1** in
`extmod/btstack/btstack_config_common.h`.  On CYW43439 silicon (the
Tufty's radio) this serialises BLE centrals — connecting a second
peripheral disconnects the first with `OSError 107`, then `EINVAL`
on retry.  Reported in [MicroPython issue #15420].

The MicroPython submodule on this branch
([`zestuart/micropython:bw-1.27.0`]) bumps both to **3**.  Verified on
the patched UF2: probe verdict A, `s_n=155 e_n=5 s_drop=False
e_drop=False` for two peripherals (Bookoo scale + EM) streaming
concurrently for 10 s.

### 2. Frozen `coffee` MicroPython package

`modules/python/coffee/` and `modules/python/mona_shim.py` are baked
into ROM.  They could in principle live on LFS as plain Python, but
the modular split (palette / layout / state / widgets / trend /
render / ble) plus runtime compile cost on a 63 KB total heap (37 KB
free at REPL) leaves ~12 KB free *after* `import coffee`, which is
not enough to also runtime-compile the package — `import coffee` then
hits `MemoryError 1336 bytes`.  Freezing puts bytecode in ROM and
removes the compile step; module dicts and instance state are the
only heap costs.

Module layout:

```
modules/python/coffee/
  __init__.py    — BLE state machine + button dispatch + update/init
  palette.py     — 6 semantic colour tokens
  layout.py      — pixel-level grid (160×120 LORES)
  state.py       — State + pressure colour state machine (hysteresis)
  widgets.py     — header sub-elements (link indicators, state dot, battery)
  trend.py       — 30 s rolling ring buffer + curve renderer
  render.py      — partial-redraw orchestrator
  bookoo.py      — Bookoo BLE protocol (parsers + command encoders)
  ble/
    __init__.py
    scale.py     — scale notify parser
    pressure.py  — EM extraction + status parsers
modules/python/mona_shim.py
  Mona-OS-shaped `badgeware` API shim over stock `picovector` +
  `st7789` + `_input` (so the same coffee app can target either
  Mona-OS V4.03 or the stock Pimoroni firmware without per-platform
  forks).
```

### 3. Departure Mono PPFs

`romfs/fonts/departure_22.ppf` (cell 14×28) and
`romfs/fonts/departure_11.ppf` (cell 7×14), generated from
[Departure Mono 1.500] (SIL OFL) via the `ttf_to_ppf.py`
converter in the host project (out of repo).  Renders at
multiples of 11 px per the font's design grid.

Falls back to stock Pimoroni `absolute.ppf` / `ark.ppf` if either
Departure file isn't present.

## Build

`ci/micropython.sh` is the upstream Pimoroni build script,
unchanged from upstream except for cache-buster tags on edits.
GitHub Actions builds the UF2 in ~5 min on push.

The latest shipped UF2 on this branch is at SHA `616ec7f9…`
(2026-04-26).

## Boot path

The Pimoroni stock firmware's frozen `modules/common/main.py`
calls `__import__("/system/main")` and `fatal_error`s with
"Unable to mount filesystem" if `/system` is missing — `/main.py`
on LFS is **not** auto-run.

For the coffee app to launch on boot, push a `/system/main.py`
on LFS that aliases `mona_shim` as `badgeware`, imports the
frozen `coffee`, and runs the loop.  Reference implementation in
the [host project README](#).

## Licence

Upstream Pimoroni Tufty 2350 firmware: see upstream repo.
btstack patch is a one-line constant change.
`coffee/`, `mona_shim.py`, and `ttf_to_ppf.py` are MIT, attributed to
Ze Stuart unless noted otherwise in file headers.
Departure Mono is SIL OFL — see the font's LICENSE in the upstream
release zip.

[MicroPython issue #15420]: https://github.com/micropython/micropython/issues/15420
[`zestuart/micropython:bw-1.27.0`]: https://github.com/zestuart/micropython/tree/bw-1.27.0
[Departure Mono 1.500]: https://departuremono.com/
