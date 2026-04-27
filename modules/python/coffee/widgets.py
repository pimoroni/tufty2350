"""Header sub-elements: link indicators, state dot, battery cluster.

Per style brief §M1.2 the header (y=0..13) carries:
- Left: S and P link indicators (3×3 dot + 5×7 glyph each, gap 5 px between)
- Right: state dot (3×3) + battery cluster (4 cells, 2×5 each, 1 px nub)

Colour rules:
- Link dot: PAPER when connected, TERRACOTTA when disconnected, STONE_DIM
  when idle (pre-scan).  Glyph always STONE.
- State dot:
    IDLE    → 1 px outline 3×3 in STONE (3 lines: top, sides, bottom)
    LIVE    → filled 3×3 PAPER, blink 1.4 s period (1.0 s on, 0.4 s lerped to STONE_DIM)
    STOPPED → filled 3×3 PAPER (no blink)
"""
from badgeware import (
    screen, shapes, Matrix, get_battery_level, is_charging, WIDTH,
)

from .palette import PAPER, STONE, STONE_DIM, TERRACOTTA
from .layout import (
    HDR_PAD_L, HDR_PAD_R, LINK_GAP, LINK_S_DOT_W, LINK_S_GLYPH_W, STATE_DOT_W,
)


# Cached primitives.
_PIX  = shapes.rectangle(0, 0, 1, 1)
_DOT3 = shapes.rectangle(0, 0, 3, 3)

_BAT_BORDER = shapes.rectangle(0, 0, 13, 6)
_BAT_INNER  = shapes.rectangle(0, 0, 11, 4)
_BAT_CELL   = shapes.rectangle(0, 0, 2, 4)


def _draw_pix(x, y, brush, shape=_PIX):
    shape.transform = Matrix().translate(x, y)
    screen.brush = brush
    screen.draw(shape)


# ── Link indicators (S, P) ──────────────────────────────────────

def _link_dot_brush(state):
    """state: 'connected', 'disconnected', 'idle'."""
    if state == "connected":
        return PAPER
    if state == "disconnected":
        return TERRACOTTA
    return STONE_DIM


def draw_link(font, x, glyph, state, battery_pct=None):
    """Draw one S or P link indicator at x.  Returns the rightmost x used
    so the caller can position the next element.  Layout:
      [3×3 dot] [1px gap] [glyph] [2px gap] [battery digits]
    Battery digits are rendered only if state == 'connected' and
    battery_pct is not None.  Variable-width — caller pads.
    """
    _draw_pix(x, 4, _link_dot_brush(state), _DOT3)
    screen.font = font
    screen.brush = STONE
    glyph_x = x + LINK_S_DOT_W + 1
    screen.text(glyph, glyph_x, 2)
    cursor = glyph_x + LINK_S_GLYPH_W
    if state == "connected" and battery_pct is not None:
        cursor += 2
        s = "%d" % int(battery_pct)
        screen.text(s, cursor, 2)
        w, _ = screen.measure_text(s)
        cursor += int(w)
    return cursor


# ── State dot ──────────────────────────────────────────────────

def state_dot_brush(session, frame_counter):
    """Return the brush for the state dot based on session + blink phase.

    Blink driven by frame counter at 10 Hz: 14-frame period = 1.4 s.
    First 10 frames PAPER, last 4 frames lerped to STONE_DIM (~30%).
    Brushes are pre-mixed; we approximate the lerp with two discrete
    brushes since we cannot blend on this picovector build.
    """
    if session == "IDLE":
        return None  # outline only — caller handles
    if session == "LIVE":
        if (frame_counter % 14) < 10:
            return PAPER
        return STONE_DIM      # approximated 30% lerp = darker grey
    # STOPPED
    return PAPER


def draw_state_dot(x, y, session, frame_counter):
    brush = state_dot_brush(session, frame_counter)
    if brush is None:
        # IDLE: 3×3 outline in STONE — top, sides, bottom (transparent fill).
        screen.brush = STONE
        screen.draw(shapes.rectangle(x,     y,     3, 1))  # top
        screen.draw(shapes.rectangle(x,     y + 2, 3, 1))  # bottom
        screen.draw(shapes.rectangle(x,     y + 1, 1, 1))  # left
        screen.draw(shapes.rectangle(x + 2, y + 1, 1, 1))  # right
        return
    # Filled 3×3.
    _draw_pix(x, y, brush, _DOT3)


# ── Battery cluster ────────────────────────────────────────────

def _battery_cells(pct):
    return max(0, min(4, (pct + 12) // 25))


def draw_battery(font, icon_x, text_x, y):
    """Battery cluster: text at text_x, icon at icon_x, both top-y = y."""
    if is_charging():
        label = "chg"
        pct = get_battery_level()
    else:
        pct = get_battery_level()
        label = f"{pct}%"
    cells = _battery_cells(pct)

    _BAT_BORDER.transform = Matrix().translate(icon_x, y + 1)
    screen.brush = STONE
    screen.draw(_BAT_BORDER)

    _BAT_INNER.transform = Matrix().translate(icon_x + 1, y + 2)
    from .palette import BG
    screen.brush = BG
    screen.draw(_BAT_INNER)

    for i in range(cells):
        _BAT_CELL.transform = Matrix().translate(icon_x + 1 + i * 3, y + 2)
        screen.brush = STONE
        screen.draw(_BAT_CELL)

    screen.font = font
    screen.brush = STONE
    screen.text(label, text_x, y)


def _battery_text_width(font, pct, charging):
    """Measure the battery label so the state dot can be positioned left of it."""
    label = "chg" if charging else f"{pct}%"
    screen.font = font
    w, _ = screen.measure_text(label)
    return int(w)


# ── Header composite ───────────────────────────────────────────

def draw_header(font, scale_link, pres_link, scale_battery, em_battery,
                session, frame_counter):
    """Assemble header: link/battery groups on the left; state dot +
    badge battery on the right.

    Left side, left-to-right (variable width):
      [S dot][S][gap][scale%]  [P dot][P][gap][em%]
    Right side, right-to-left (anchored to right padding):
      [badge cells][gap][badge text][gap][state dot]
    """
    # Left: S group, then P group with a gap between groups.
    cursor = HDR_PAD_L
    cursor = draw_link(
        font, cursor, "S",
        "connected" if scale_link else "disconnected",
        scale_battery,
    )
    cursor += LINK_GAP
    draw_link(
        font, cursor, "P",
        "connected" if pres_link else "disconnected",
        em_battery,
    )

    # Right: badge battery anchored to right edge, state dot left of text.
    pct = get_battery_level()
    charging = is_charging()
    text_w = _battery_text_width(font, pct, charging)
    icon_w = 13                                  # _BAT_BORDER width
    icon_x = WIDTH - HDR_PAD_R - icon_w
    text_x = icon_x - 2 - text_w
    dot_x  = text_x - 4 - STATE_DOT_W

    draw_battery(font, icon_x, text_x, 1)
    draw_state_dot(dot_x, 4, session, frame_counter)
