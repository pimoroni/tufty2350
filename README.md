# Tessera

A live brew display for the [Pimoroni Tufty 2350](https://shop.pimoroni.com/products/tufty-2350)
badge.  Connects via Bluetooth Low Energy to a [Bookoo Mini Coffee Scale](https://bookoocoffee.com/)
and a [Bookoo Espresso Monitor](https://bookoocoffee.com/), and renders a
real-time UI of the espresso shot in progress: mass on the scale, timer, brew
pressure, flow rate, and a 30-second pressure trend.

This repository is a fork of [`pimoroni/tufty2350`](https://github.com/pimoroni/tufty2350)
that bundles the brew-display app as a frozen MicroPython package and a small
firmware patch for concurrent dual-central BLE.  Build a `.uf2`, flash it to
the badge, and the brewing UI is the application.

## What it does

- **Real-time brewing telemetry** at the SDK's render cadence — mass, timer,
  pressure (bar), and flow rate (g/s).  Bare values, units appear next to
  the labels with a U+00B7 separator.
- **30-second rolling trend graph** of pressure with flow overlay, on a 60×40
  pixel curve.
- **Pressure colour state machine** with hysteresis at 6/9/11 bar (low /
  high warning / overpressure), suppressed outside an active extraction.
- **Header link indicators** for scale (S) and espresso monitor (P), each
  with the peripheral's battery percentage when connected.  State pill
  shows IDLE / LIVE / STOPPED, with the LIVE state blinking at ~1.4 s.
- **Auto-power-off when the scale disconnects** with a 30-second grace
  window for radio glitches.  Hardware-off via `powman.shipping_mode()`;
  RESET wakes.  The espresso monitor is force-disconnected when the scale
  drops, to avoid draining its battery.
- **Boot-time escape hatch**: hold any user button at RESET to skip the
  app and drop to the MicroPython REPL — useful for development and
  recovery.

## Hardware required

- Pimoroni Tufty 2350 badge — RP2350, 2.8" 320×240 IPS LCD, CYW43439 radio.
- Bookoo Mini Coffee Scale — Bluetooth-enabled gravimetric scale.
- Bookoo Espresso Monitor — pressure / flow sensor that clamps onto an espresso machine's brew head.  Optional — without it, the badge still shows mass + timer.

## Quick start

Pre-built UF2s are produced on every push by GitHub Actions.  Pick one from
[the Actions tab](https://github.com/zestuart/tessera/actions/workflows/micropython.yml)
on the `m6.5-dual-central` branch, or build from source (below).

To flash:

1. Connect the Tufty 2350 via USB-C.
2. Hold the BOOT button (back of the badge) and tap RESET.  A USB drive named `RP2350` mounts.
3. Drag the `.uf2` onto the drive.  The badge re-enumerates as `MicroPython` once flashing finishes.
4. Push a small `/system/main.py` to the badge (LFS).  See
   [`COFFEE_README.md`](COFFEE_README.md) for the boot-path detail and
   reference launcher script.
5. Power the scale on.  The display populates as soon as the BLE link is up.

For a deeper how-to (specs, secrets.py, app installation), the upstream
Pimoroni README is preserved as [`README.upstream.md`](README.upstream.md).

## Architecture

See [`COFFEE_README.md`](COFFEE_README.md) for the full deep-dive.  Brief
version:

- The base firmware is the upstream Pimoroni Tufty 2350 build.
- The MicroPython submodule is replaced with [`zestuart/micropython:bw-1.27.0`](https://github.com/zestuart/micropython/tree/bw-1.27.0),
  which raises btstack's `MAX_NR_HCI_CONNECTIONS` and `MAX_NR_GATT_CLIENTS`
  from 1 to 3, enabling concurrent dual-central BLE on CYW43439 silicon
  ([upstream MicroPython issue #15420](https://github.com/micropython/micropython/issues/15420)).
- The brew-display app lives at `modules/python/coffee/` and is frozen into
  ROM at build time — heap pressure on this device is ~12 KB after import,
  not enough to runtime-compile the package.
- A `mona_shim.py` adapter bridges the Mona-OS `badgeware` API onto the
  stock Pimoroni `picovector` + `st7789` + `_input` primitives.

## Repository layout

```
modules/python/coffee/        ← the brew-display app (frozen)
modules/python/mona_shim.py   ← Mona-OS / Pimoroni badgeware shim
romfs/fonts/departure_*.ppf   ← Departure Mono font assets, baked in
ci/micropython.sh             ← upstream build script (touched only for cache-busters)
board/mpconfigboard.h         ← board name reflects the patched build
COFFEE_README.md              ← architecture deep-dive
README.upstream.md            ← upstream Pimoroni Tufty 2350 README
```

Anything not listed here is upstream Pimoroni / MicroPython / Pico SDK / btstack code.

## Build from source

```
git clone --recurse-submodules https://github.com/zestuart/tessera.git
cd tessera
git checkout m6.5-dual-central
ci/micropython.sh
```

`ci/micropython.sh` is the upstream Pimoroni build script, unchanged except
for a cache-buster comment that gets bumped per shipped change.  GitHub
Actions runs the same script on every push and produces a `.uf2` artefact in
~5 minutes.

## Status

Stable for the brewing flow.  Two open bugs documented in
[issue #1](https://github.com/zestuart/tessera/issues/1):

- Battery-only RESET (and RESET after auto-dormant) sometimes lands the
  badge in a blink state until USB is attached — likely a `powman` wake
  pathology.
- C long-press doesn't fire manual dormant — pin-membership check
  suspected.

The brewing flow itself works end-to-end: connect, brew, scale-off, dormant.

## Attribution

This repository builds on:

- [`pimoroni/tufty2350`](https://github.com/pimoroni/tufty2350) — Pimoroni's official Tufty 2350 firmware build.
- [`pimoroni/badgeware`](https://github.com/pimoroni/badger2350) — the badgeware Python framework, bundled in the firmware.
- [`micropython/micropython`](https://github.com/micropython/micropython) — MicroPython; this fork uses [`zestuart/micropython:bw-1.27.0`](https://github.com/zestuart/micropython/tree/bw-1.27.0) with the btstack-constants patch.
- [`raspberrypi/pico-sdk`](https://github.com/raspberrypi/pico-sdk) — Pico C SDK and the `powman` peripheral.
- [`bluekitchen/btstack`](https://github.com/bluekitchen/btstack) — Bluetooth stack.
- [Departure Mono](https://departuremono.com/) by [Helena Zhang](https://helenazhang.com/) — display font, regenerated as PPF assets.

Bookoo's BLE protocol details for the scale and espresso monitor are documented at the
[BookooCode/OpenSource](https://github.com/BookooCode/OpenSource) repository.

## Licence

The Tessera additions in this repository are MIT licensed — see
[`LICENSE`](LICENSE).  Specifically, that covers `modules/python/coffee/`,
`modules/python/mona_shim.py`, the cache-buster and board-name
modifications, and this README.

Code carried over from the fork's base or vendored from upstream retains
its original licences:

- MicroPython: MIT.
- Pico SDK: BSD-3-Clause.
- btstack: BSD-3-Clause (with some files dual-licensed; see the btstack tree).
- Departure Mono: SIL Open Font License 1.1.
- The upstream Pimoroni Tufty 2350 firmware build script and bundled
  Pimoroni-authored modules: Pimoroni has not published an explicit
  licence file in [the upstream repo](https://github.com/pimoroni/tufty2350)
  as of 2026-04-27.  If you intend to redistribute beyond personal /
  development use, please confirm terms with Pimoroni directly.
