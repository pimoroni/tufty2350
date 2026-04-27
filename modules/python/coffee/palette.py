"""Palette tokens per badger-bookoo-style-brief.md §2.

Six semantic tokens; legacy names (AMBER, GREEN, RED, SLATE, WHITE,
CYAN) kept as aliases so existing call sites in __init__.py keep
working until §8.5 / §8.4 migrate them.

RGB888 (we go through `brushes.color()`); the brief's RGB565 column
is for HIRES porting in Phase 2.
"""
from badgeware import brushes


BG          = brushes.color(0x00, 0x00, 0x00)
PAPER       = brushes.color(0xED, 0xE8, 0xDE)
STONE       = brushes.color(0x7A, 0x7E, 0x83)
STONE_DIM   = brushes.color(0x3A, 0x3D, 0x42)
OCHRE       = brushes.color(0xD4, 0xA8, 0x5A)
TERRACOTTA  = brushes.color(0xC9, 0x70, 0x64)


# Legacy aliases (will be removed once call sites migrate in §8.4 / §8.5).
AMBER = OCHRE
RED   = TERRACOTTA
WHITE = PAPER
SLATE = STONE
GREEN = PAPER
CYAN  = STONE
