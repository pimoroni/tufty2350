"""Bookoo espresso monitor notify parsers (UUIDs 0xFF02 extraction, 0xFF03 status)."""
import time

from .. import bookoo, render, trend
from ..state import State


def parse_em_extraction(raw):
    f = bookoo.parse_em_extraction(bytes(raw))
    if f is None:
        return
    State.pres                 = f["pressure_bar"]
    State.em_battery           = f["battery_pct"]
    State._pres_last_change_ms = time.ticks_ms()
    # Pressure into trend ring (paired with current flow); pressure → primary.
    # See ble/scale.py: header isn't marked dirty per-frame to avoid flicker;
    # battery updates ride the 10-frame periodic header_tick.
    trend.push(State.pres, State.flow)
    render.dirty_primary = True
    render.dirty_trend = True


def parse_em_status(raw):
    # 0x1D status frame is undocumented; validate the link only and
    # don't decode any of its payload bytes.  EM battery percentage
    # comes from the 0x1B extraction frame (BYTE7, documented).
    bookoo.parse_em_status(bytes(raw))
