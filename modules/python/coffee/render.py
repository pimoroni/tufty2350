"""Partial-redraw orchestrator.

Module-level dirty flags are set by IRQ parsers when their parsed
value changes; the render loop runs `redraw_*()` only for rows
whose flag is set, then clears it.  Header / state dot have their
own cadences (every 10 frames / every 4 frames respectively) — the
orchestrator wraps both via `tick(frame_counter)`.

Caveat from style brief and addendum §G: partial redraw is **CPU
avoidance, not bus bandwidth**.  `display.update()` pushes the full
framebuffer regardless of clip rectangles.  Win is in
`screen.draw()` cost.
"""
from badgeware import screen, shapes, Matrix, WIDTH, get_battery_level, is_charging

from .palette import BG, PAPER, STONE, STONE_DIM
from .layout import (
    HDR_H, PRIM_TOP, PRIM_H, PRIM_BOTTOM_Y, SEC_TOP, SEC_H, SEC_BOTTOM_Y,
    TREND_TOP, TREND_H, COL_W, VDIV_X,
)
from .state import State, pressure_brush
from . import widgets, trend


# ── Dirty flags ─────────────────────────────────────────────────
# IRQ parsers set these (or update() does, on session transitions).
# The orchestrator clears each after its row redraws.

dirty_header     = True
dirty_primary    = True
dirty_secondary  = True
dirty_trend      = True
_force_full      = True   # next tick repaints everything (post-wake / boot)
_header_sig      = None   # last visible-state signature; redraw only on change


def mark_all_dirty():
    global dirty_header, dirty_primary, dirty_secondary, dirty_trend, _force_full
    dirty_header = dirty_primary = dirty_secondary = dirty_trend = True
    _force_full = True


# ── Cached primitives ──────────────────────────────────────────
_HLINE = shapes.rectangle(0, 0, WIDTH, 1)


# ── Borders + dividers ─────────────────────────────────────────

def _hline(y):
    _HLINE.transform = Matrix().translate(0, y)
    screen.brush = STONE_DIM
    screen.draw(_HLINE)


def draw_dividers():
    """Row borders + vertical dividers — disabled per user request 2026-04-26.
    Layout grid is implied by row positions and label placement; no
    visible lines drawn between rows or columns.
    """
    pass


# ── Value helpers ──────────────────────────────────────────────

def _big_value(font_lg, font_sm, value_str, unit_str, x, y, value_brush):
    screen.font = font_lg
    screen.brush = value_brush
    screen.text(value_str, x, y)
    vw, vh = screen.measure_text(value_str)
    screen.font = font_sm
    screen.brush = STONE
    _, uh = screen.measure_text(unit_str)
    screen.text(unit_str, x + vw + 2, y + vh - uh)


def _med_value(font_sm, value_str, unit_str, x, y, value_brush):
    screen.font = font_sm
    screen.brush = value_brush
    screen.text(value_str, x, y)
    vw, _ = screen.measure_text(value_str)
    screen.brush = STONE
    screen.text(unit_str, x + vw + 2, y)


def _small_label(font_sm, label, x, y):
    screen.font = font_sm
    screen.brush = STONE
    screen.text(label, x, y)


# ── Row redraws ─────────────────────────────────────────────────

def redraw_primary(font_lg, font_sm):
    """Primary row: MASS | PRES.  No dividers or borders."""
    bg = shapes.rectangle(0, PRIM_TOP, WIDTH, PRIM_H)
    screen.brush = BG
    screen.draw(bg)

    # font_sm renders 11 px tall; lab_y must keep label fully inside the row
    # (PRIM_TOP..PRIM_TOP+PRIM_H-1) so the secondary's clear rect doesn't
    # clip its descenders.  Leave 1 px breathing room.
    # Place label directly under the digit row: digit at val_y, height
    # ~16 px → label sits at val_y + 16 + 1 px gap.  This is ~12 px
    # above the bottom of the row, intentional dead space below for
    # the label's descenders + visual breathing room.
    val_y = PRIM_TOP + 4
    lab_y = val_y + 17

    digits_brush = PAPER if State.session != "IDLE" else STONE_DIM

    _big_value(font_lg, font_sm, f"{State.mass:.1f}", "g",
               6, val_y, digits_brush)
    _small_label(font_sm, "MASS", 6, lab_y)
    _big_value(font_lg, font_sm, f"{State.pres:.1f}", "bar",
               COL_W + 5, val_y, pressure_brush(State.pres))
    _small_label(font_sm, "PRES", COL_W + 5, lab_y)


def redraw_secondary(font_sm):
    """Secondary row: TIME | FLOW.  No dividers or borders."""
    bg = shapes.rectangle(0, SEC_TOP, WIDTH, SEC_H)
    screen.brush = BG
    screen.draw(bg)

    val_y = SEC_TOP + 2
    lab_y = val_y + 12

    digits_brush = PAPER if State.session != "IDLE" else STONE_DIM
    flow_brush = PAPER if State.session == "LIVE" else STONE_DIM

    _med_value(font_sm, f"{State.time:.1f}", "s",
               6, val_y, digits_brush)
    _small_label(font_sm, "TIME", 6, lab_y)
    _med_value(font_sm, f"{State.flow:.1f}", "g/s",
               COL_W + 5, val_y, flow_brush)
    _small_label(font_sm, "FLOW", COL_W + 5, lab_y)


def redraw_header(font_sm, frame_counter):
    """Header: links + state dot + battery."""
    bg = shapes.rectangle(0, 0, WIDTH, HDR_H)
    screen.brush = BG
    screen.draw(bg)
    widgets.draw_header(
        font_sm,
        State.scale_link,
        State.pres_link,
        State.session,
        frame_counter,
    )


def redraw_trend():
    """Trend strip: chrome + curves + cursor."""
    bg = shapes.rectangle(0, TREND_TOP, WIDTH, TREND_H)
    screen.brush = BG
    screen.draw(bg)
    trend.draw()


def draw_corner_brackets():
    """Four 4×4 px corner brackets in STONE_DIM (brief §M1.2)."""
    from .layout import CORNER_BRACKETS
    screen.brush = STONE_DIM
    for cx, cy in CORNER_BRACKETS:
        # L-shape: two 1×3 lines meeting at the corner.
        # TL/BR mirror; for simplicity draw 4×4 outline-corner here.
        screen.draw(shapes.rectangle(cx, cy, 3, 1))
        screen.draw(shapes.rectangle(cx, cy, 1, 3))


# ── Tick (called from update() each frame) ─────────────────────

def tick(font_lg, font_sm, frame_counter):
    """Run one render frame.  Caller (`update()`) sets dirty flags
    on relevant state changes; this dispatches the redraws.
    """
    global dirty_header, dirty_primary, dirty_secondary, dirty_trend, _force_full

    # Full repaint on first frame after wake / mark_all_dirty.
    if _force_full:
        screen.brush = BG
        screen.draw(shapes.rectangle(0, 0, WIDTH, TREND_TOP + TREND_H))
        draw_dividers()
        redraw_header(font_sm, frame_counter)
        redraw_primary(font_lg, font_sm)
        redraw_secondary(font_sm)
        redraw_trend()
        draw_corner_brackets()
        dirty_header = dirty_primary = dirty_secondary = dirty_trend = False
        _force_full = False
        return

    # Header redraws only when its visible state has changed (signature
    # check) — periodic re-paint per frame caused visible flicker on
    # the bottom row of S/P/chg glyphs.  The signature includes the
    # blink phase during LIVE so the state-dot still pulses.
    global _header_sig
    blink_phase = (frame_counter // 4) if State.session == "LIVE" else 0
    sig = (
        State.scale_link, State.pres_link, State.session,
        State.scale_battery, State.em_battery,
        get_battery_level(), is_charging(),
        blink_phase,
    )
    if dirty_header or sig != _header_sig:
        redraw_header(font_sm, frame_counter)
        _header_sig = sig
        dirty_header = False

    if dirty_primary:
        redraw_primary(font_lg, font_sm)
        dirty_primary = False

    if dirty_secondary:
        redraw_secondary(font_sm)
        dirty_secondary = False

    if dirty_trend:
        redraw_trend()
        dirty_trend = False
