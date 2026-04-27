"""Bookoo scale notify parser (UUID 0xFF11)."""
import time

from .. import bookoo, render
from ..state import State


def parse_scale(raw):
    f = bookoo.parse_scale_frame(bytes(raw))
    if f is None:
        return
    State.mass          = f["weight_g"]
    State.time          = f["timer_s"]
    State.flow          = f["flow_gps"]
    State.scale_battery = f["battery_pct"]
    if f["timer_s"] != State._timer_prev:
        State._timer_prev           = f["timer_s"]
        State._timer_last_change_ms = time.ticks_ms()
    # Mass + time → primary + secondary; battery → header.
    render.dirty_primary = True
    render.dirty_secondary = True
    render.dirty_header = True
