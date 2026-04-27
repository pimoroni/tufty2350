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
    HDR_PAD_R, LINK_S_X, LINK_P_X, LINK_S_DOT_W,
    LINK_S_GLYPH_W, STATE_DOT_W,
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


def draw_link(font, x, glyph, state):
    """Draw one S or P link indicator: 3×3 dot at x, 5×7 glyph after."""
    _draw_pix(x, 4, _link_dot_brush(state), _DOT3)
    screen.font = font
    screen.brush = STONE
    screen.text(glyph, x + LINK_S_DOT_W + 1, 2)


def draw_links(font, scale_state, pres_state):
    """Draw both S and P link indicators."""
    draw_link(font, LINK_S_X, "S", scale_state)
    draw_link(font, LINK_P_X, "P", pres_state)


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


def draw_battery(font, x, y):
    """Battery widget right-anchored at (x, y) — cells, then numeric or 'chg'."""
    if is_charging():
        label = "chg"
        pct = get_battery_level()
    else:
        pct = get_battery_level()
        label = f"{pct}%"
    cells = _battery_cells(pct)

    _BAT_BORDER.transform = Matrix().translate(x, y + 1)
    screen.brush = STONE
    screen.draw(_BAT_BORDER)

    _BAT_INNER.transform = Matrix().translate(x + 1, y + 2)
    from .palette import BG
    screen.brush = BG
    screen.draw(_BAT_INNER)

    for i in range(cells):
        _BAT_CELL.transform = Matrix().translate(x + 1 + i * 3, y + 2)
        screen.brush = STONE
        screen.draw(_BAT_CELL)

    screen.font = font
    w, _h = screen.measure_text(label)
    screen.brush = STONE
    screen.text(label, x - 2 - w, y)


# ── Header composite ───────────────────────────────────────────

def draw_header(font, scale_link, pres_link, session, frame_counter):
    """Assemble header: links left, state dot + battery right."""
    draw_links(
        font,
        "connected" if scale_link else "disconnected",
        "connected" if pres_link else "disconnected",
    )

    # Right side: battery cluster at far right, state dot just left of it.
    bat_w = 16  # 13 px border + 1 px gap + 2 px nub padding
    bat_x = WIDTH - HDR_PAD_R - bat_w
    draw_battery(font, bat_x, 1)

    dot_x = bat_x - 4 - STATE_DOT_W
    draw_state_dot(dot_x, 4, session, frame_counter)
