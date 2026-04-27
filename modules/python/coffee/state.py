"""Session FSM and pressure colour state machine.

`State` is the single canonical source of telemetry / link state,
populated from BLE IRQ parsers (in `coffee.ble.*`) and read by the
render loop.

Pressure colour-coding lives here too: per style brief §M1.3 it's a
hysteresis state machine with thresholds at 6.0 / 9.0 / 11.0 bar
and a 0.2 bar deadband, implemented as `pressure_brush(value)`
returning the brush for the current `pres` reading.
"""
from .palette import OCHRE, PAPER, TERRACOTTA, STONE_DIM


# ── Shared state ────────────────────────────────────────────────

class State:
    """All values driven by the BLE IRQ callback."""
    mass = 0.0
    time = 0.0
    pres = 0.0
    flow = 0.0
    session = "IDLE"
    scale_link = False
    pres_link = False
    scale_battery = None
    em_battery = None

    # Timer-running detection.  The Bookoo protocol has no explicit
    # "running" flag, so we infer from whether the timer field has
    # changed recently.
    _timer_prev = 0.0
    _timer_last_change_ms = 0
    _pres_last_change_ms = 0


# ── Pressure colour state machine (style brief §M1.3) ───────────
# Hysteresis prevents flicker when a noisy reading hovers around a
# threshold.  State transitions only on >0.2 bar excursion past the
# threshold; sticky on the over states so a single calm sample
# doesn't drop us back to PAPER.

_PRES_PAPER       = 0
_PRES_OCHRE_LOW   = 1   # <6 bar — pre-infusion / low warning
_PRES_OCHRE_HIGH  = 2   # 9..11 bar — high warning
_PRES_TERRACOTTA  = 3   # >11 bar — overpressure

_pres_state = _PRES_PAPER


def pressure_brush(bar, session=None):
    """Return the brush for the pressure digit.  Stateful (hysteresis)."""
    global _pres_state

    if session is None:
        session = State.session

    # Outside LIVE the digits drop to STONE_DIM regardless of value.
    if session != "LIVE":
        # Reset hysteresis state so the next LIVE entry starts clean.
        _pres_state = _PRES_PAPER
        return STONE_DIM

    # Sticky overpressure: stay TERRACOTTA until value drops to <= 10.8.
    if _pres_state == _PRES_TERRACOTTA:
        if bar <= 10.8:
            _pres_state = _PRES_OCHRE_HIGH
        else:
            return TERRACOTTA

    if bar > 11.0:
        _pres_state = _PRES_TERRACOTTA
        return TERRACOTTA

    # High warning: enter at >9.2, leave at <=9.0.
    if _pres_state == _PRES_OCHRE_HIGH:
        if bar <= 9.0:
            _pres_state = _PRES_PAPER
        else:
            return OCHRE
    elif bar > 9.2:
        _pres_state = _PRES_OCHRE_HIGH
        return OCHRE

    # Low warning: enter at <5.8, leave at >=6.0.
    if _pres_state == _PRES_OCHRE_LOW:
        if bar >= 6.0:
            _pres_state = _PRES_PAPER
        else:
            return OCHRE
    elif bar < 5.8:
        _pres_state = _PRES_OCHRE_LOW
        return OCHRE

    return PAPER


def reset_pressure_state():
    """Force the pressure SM back to PAPER (e.g. on session exit or RESET)."""
    global _pres_state
    _pres_state = _PRES_PAPER


# ── Legacy aliases ──────────────────────────────────────────────
# Existing __init__.py call sites.  Removed once render rewrite
# migrates them.
def pres_brush(bar):
    return pressure_brush(bar)
