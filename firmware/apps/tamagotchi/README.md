# Tamagotchi

A virtual pet that lives on the badge. It hatches from an egg, grows through
five life stages, and gets hungry, bored, filthy and occasionally ill — all in
real time against the battery-backed RTC, so it keeps ageing while the badge is
in another app, asleep, or switched off. Come back after a night and it is
hungry; leave it a full day and you are holding a funeral.

## Install

Follow [Install and launch](../../../APPS.md#4-install-and-launch), copying this
entire `tamagotchi` directory into the badge's `apps` folder. Select
**Tamagotchi** in the menu and press **B**.

The folder needs only `__init__.py` and the 24×24 `icon.png`; there are no
assets to bundle, because the pet is drawn from vector primitives and the fonts
come from the badge. No Wi-Fi or firmware flashing is required.

## Controls

| Button | Does |
| --- | --- |
| **A** / **C** | Move along the action bar |
| **B** | Do the selected action, or confirm |
| **UP** | Open the stat sheet |
| **DOWN** | Back / cancel |
| **HOME** | Leave the app |

The six actions are **FEED** (a meal or a snack), **PLAY** (a best-of-three
guessing game), **CLEAN**, **MEDS**, **LIGHT** (send it to sleep) and **INFO**.

Progress saves after every action and every 60 seconds, so leaving via HOME at
any moment is safe.

## Looking after it

Four gauges run along the top — food, fun, energy and hygiene — and a heart in
the corner shows health, which is the one that matters.

- **Food and fun** drain steadily; let either reach zero and health follows.
- **Energy** refills while asleep. Turn the lights off to send the pet to bed;
  waking it early makes it grumpy. An exhausted pet collapses on its own.
- **Poops** appear every couple of hours and pull hygiene down faster the more
  of them are left lying about.
- **Illness** sets in when the pet is left hungry or filthy, shown by a red
  cross over its head. Give it MEDS.

Ignored completely, it is in trouble after about half a day and dies after
roughly one. Hold **B** at the grave for a fresh egg, and the generation counter
ticks up.

Each pet is named at random from a list of one hundred, kept to eight characters
so the hatching announcement fits across the screen.

## Growing up

| Stage | Reached at |
| --- | --- |
| Egg | — |
| Baby | 2 minutes |
| Child | 1 hour |
| Teen | 6 hours |
| Adult | 24 hours |
| Elder | 72 hours |

Each stage is drawn differently: the baby has a springy antenna, the teen and
adult grow pointed ears and arms, the elder gets eyebrows.

## Firmware compatibility

The app runs on both the shipped firmware and newer builds, choosing at startup
between the API each provides:

| Needs | Shipped firmware | Newer firmware |
| --- | --- | --- |
| Fonts | `rom_font.<name>`, else `pixel_font.load()` | `font.<name>` |
| Ellipses | 20-point polygon via `shape.custom()` | `shape.ellipse()` |
| Sky gradient | banded fill | same banded fill |
| Colour shading | computed from `(r, g, b)` tuples | same |
| Text size | no scaling — larger glyphs use a larger font | same |

There is nothing to configure, and no behaviour changes between them.

## Tuning

The decay rates (points per hour), poop and illness odds, health drain and
regeneration, and the stage ages are all constants in one block near the top of
`__init__.py`. The pet is drawn in `draw_pet()` from vector primitives rather
than sprite sheets, so its colours and proportions are a few numbers away from
being something else entirely.

The app runs in Tufty's 160×120 `LORES` mode for a steady framerate.
