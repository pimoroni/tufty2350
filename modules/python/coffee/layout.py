"""Layout grid per badger-bookoo-style-brief.md §M1.1.

Vertical budget: 14 + 50 + 34 + 22 = 120 px (no separate footer; the
state dot moves into the header per §8.4).  Existing layout was
10/46/24/14 + 24-px footer; this module replaces it.

All dimensions in framebuffer pixels (160×120 LORES).  HIRES
porting deferred to Phase 2.
"""
from badgeware import WIDTH, HEIGHT


# ── Row geometry ────────────────────────────────────────────────
HDR_TOP   = 0
HDR_H     = 14
HDR_BOTTOM_Y = HDR_H - 1               # y=13 — STONE_DIM 1 px border

PRIM_TOP  = HDR_H                      # y=14
PRIM_H    = 50
PRIM_BOTTOM_Y = PRIM_TOP + PRIM_H - 1  # y=63 — STONE_DIM 1 px border

SEC_TOP   = PRIM_TOP + PRIM_H          # y=64
SEC_H     = 34
SEC_BOTTOM_Y = SEC_TOP + SEC_H - 1     # y=97 — STONE_DIM 1 px border

TREND_TOP = SEC_TOP + SEC_H            # y=98
TREND_H   = HEIGHT - TREND_TOP         # 22 px — no bottom border (display edge)


# ── Column geometry ─────────────────────────────────────────────
COL_W     = WIDTH // 2                 # 80 px each side
VDIV_X    = COL_W                      # x=80 — STONE_DIM 1 px vertical divider


# ── Header sub-positions (4 px outer padding) ───────────────────
HDR_PAD_L = 4
HDR_PAD_R = 4
LINK_S_X  = HDR_PAD_L                  # S link indicator left edge
LINK_S_DOT_W = 3                       # 3×3 dot
LINK_S_GLYPH_W = 5                     # 5×7 glyph (S)
LINK_GAP  = 5                          # gap between S and P groups
LINK_P_X  = LINK_S_X + LINK_S_DOT_W + LINK_S_GLYPH_W + LINK_GAP

STATE_DOT_W = 3                        # 3×3 state dot, right of header


# ── Trend strip positions ───────────────────────────────────────
TREND_BASELINE_Y = HEIGHT - 1          # y=119 — STONE_DIM
TREND_MID_Y      = TREND_TOP + (TREND_H // 2)  # y=109 — dashed STONE_DIM
TREND_TICK_10S_X = 53                  # 10 s tick mark x
TREND_TICK_20S_X = 107                 # 20 s tick mark x

# Y-axis normalisation: pressure 0..12 → y=118..100, flow 0..3 → y=118..100
TREND_Y_MIN = 100                      # top of curves
TREND_Y_MAX = 118                      # bottom of curves (1 px above baseline)
TREND_PRES_RANGE = 12.0                # bar
TREND_FLOW_RANGE = 3.0                 # g/s

# X-axis: 30 s rolling, now_x advances 0..159 over 30 s, then scrolls
TREND_WINDOW_S   = 30.0
TREND_BUFFER_LEN = WIDTH               # 160 samples for pixel-aligned scroll
TREND_STRIDE     = 1                   # 1 px per sample


# ── Corner brackets (decorative) ────────────────────────────────
CORNER_BRACKETS = [
    (0,         0),                    # TL
    (WIDTH - 4, 0),                    # TR (4 px square)
    (0,         HEIGHT - 4),           # BL
    (WIDTH - 4, HEIGHT - 4),           # BR
]


# ── Legacy aliases (existing __init__.py call sites) ────────────
# These map old layout values to the new grid.  Kept until §8.2.6
# render rewrite migrates call sites.
FOOT_TOP = TREND_TOP + TREND_H         # = HEIGHT; pill is gone, footer is the trend's bottom edge
