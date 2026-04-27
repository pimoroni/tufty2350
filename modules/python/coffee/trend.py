"""30 s rolling trend ring buffer + curve renderer per style brief §M1.2.

Two parallel curves — pressure (PAPER) and flow (STONE) — both
1 px stroke at the same y-axis-normalised plot area
(pressure 0..12 bar → y=118..100; flow 0..3 g/s → y=118..100).

The brief specifies a 1 px-per-sample 30 s window scrolling
left-to-right; with 160 sample slots (one per pixel) the buffer
scrolls in place once filled.  Pre-fill with NaN sentinels so the
first 30 s shows only the rolling cursor.
"""
from badgeware import screen, shapes, Matrix

from .palette import PAPER, STONE, STONE_DIM
from .layout import (
    TREND_TOP, TREND_H, TREND_BASELINE_Y, TREND_MID_Y,
    TREND_TICK_10S_X, TREND_TICK_20S_X,
    TREND_Y_MIN, TREND_Y_MAX, TREND_PRES_RANGE, TREND_FLOW_RANGE,
    TREND_BUFFER_LEN, WIDTH,
)


_NAN = -1.0  # sentinel meaning "no sample yet"

# Ring buffer.  Index 0 = newest sample at now_x (head wraps).
pres_buf = [_NAN] * TREND_BUFFER_LEN
flow_buf = [_NAN] * TREND_BUFFER_LEN
head = 0


# Cached primitives.
_PIX = shapes.rectangle(0, 0, 1, 1)
_DOT2 = shapes.rectangle(0, 0, 2, 2)


def push(pres, flow):
    """Advance the ring head by one and write the latest sample."""
    global head
    head = (head + 1) % TREND_BUFFER_LEN
    pres_buf[head] = pres
    flow_buf[head] = flow


def reset():
    """Wipe the buffer (e.g. on session reset)."""
    global head
    for i in range(TREND_BUFFER_LEN):
        pres_buf[i] = _NAN
        flow_buf[i] = _NAN
    head = 0


def _y_for_pres(p):
    if p < 0: p = 0
    if p > TREND_PRES_RANGE: p = TREND_PRES_RANGE
    return int(TREND_Y_MAX - (p / TREND_PRES_RANGE) * (TREND_Y_MAX - TREND_Y_MIN))


def _y_for_flow(f):
    if f < 0: f = 0
    if f > TREND_FLOW_RANGE: f = TREND_FLOW_RANGE
    return int(TREND_Y_MAX - (f / TREND_FLOW_RANGE) * (TREND_Y_MAX - TREND_Y_MIN))


def _draw_pix(x, y, brush):
    _PIX.transform = Matrix().translate(x, y)
    screen.brush = brush
    screen.draw(_PIX)


def draw_chrome():
    """Draw baseline + mid-line + ticks (all STONE_DIM).  Cheap to redraw
    every frame; partial-redraw orchestrator may call only on transition."""
    screen.brush = STONE_DIM
    # Baseline at y=119 (full width)
    base = shapes.rectangle(0, TREND_BASELINE_Y, WIDTH, 1)
    screen.draw(base)
    # Dashed mid-line at y=109 — 2 on / 4 off
    for x in range(0, WIDTH, 6):
        seg = shapes.rectangle(x, TREND_MID_Y, 2, 1)
        screen.draw(seg)
    # Ticks at x=53 (10 s) and x=107 (20 s), 2 px tall from y=118..119
    for tx in (TREND_TICK_10S_X, TREND_TICK_20S_X):
        tick = shapes.rectangle(tx, TREND_BASELINE_Y - 1, 1, 2)
        screen.draw(tick)


def draw_curves():
    """Draw the rolling pressure + flow curves.  Pressure first (PAPER),
    then flow (STONE) on top so flow remains visible when overlapping."""
    # Pressure curve
    screen.brush = PAPER
    for i in range(TREND_BUFFER_LEN):
        v = pres_buf[i]
        if v < 0:
            continue
        y = _y_for_pres(v)
        _draw_pix(i, y, PAPER)
    # Flow curve
    screen.brush = STONE
    for i in range(TREND_BUFFER_LEN):
        v = flow_buf[i]
        if v < 0:
            continue
        y = _y_for_flow(v)
        _draw_pix(i, y, STONE)


def draw_now_cursor():
    """1 px vertical dashed line at the head (now_x); 1 on / 2 off,
    from y=99 to y=118."""
    screen.brush = STONE_DIM
    nx = head
    for y in range(TREND_TOP + 1, TREND_BASELINE_Y, 3):
        _draw_pix(nx, y, STONE_DIM)
    # Current-sample dots: 2 px on top of the cursor.
    pv = pres_buf[head]
    fv = flow_buf[head]
    if pv >= 0:
        py = _y_for_pres(pv)
        _DOT2.transform = Matrix().translate(nx - 1, py - 1)
        screen.brush = PAPER
        screen.draw(_DOT2)
    if fv >= 0:
        fy = _y_for_flow(fv)
        _DOT2.transform = Matrix().translate(nx - 1, fy - 1)
        screen.brush = STONE
        screen.draw(_DOT2)


def draw():
    """Full trend strip redraw: chrome + curves + cursor."""
    draw_chrome()
    draw_curves()
    draw_now_cursor()
