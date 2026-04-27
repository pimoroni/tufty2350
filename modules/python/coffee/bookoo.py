"""Bookoo BLE protocol parsers and command encoders.

Strictly per the official protocol docs:
  https://github.com/BooKooCode/OpenSource/blob/main/bookoo_mini_scale/protocols.md
  https://github.com/BooKooCode/OpenSource/blob/main/espresso_monitor/protocols.md

The aiobookoo HA reference (makerwolf/aiobookoo) decodes weight as 2 bytes,
flow as 1 byte, timer as 2 bytes, standby as 1 byte — silently truncating
high bytes.  Works for typical brews (< 655 g, < 65 s, < 2.55 g/s) but wrong
for channeling / gushers.  This module follows the doc's full byte ranges.

Frame checksum verified on captured frame (XOR all bytes 0..N-2 == byte N-1).
"""

# ── Mini Scale ───────────────────────────────────────────────────
SCALE_HDR1 = 0x03    # product number
SCALE_HDR2 = 0x0B    # type = weight notification
SCALE_FRAME_LEN = 20
SCALE_UUID_SERVICE = 0x0FFE
SCALE_UUID_WEIGHT  = 0xFF11
SCALE_UUID_COMMAND = 0xFF12

# ── Espresso Monitor ─────────────────────────────────────────────
EM_HDR1 = 0x02
EM_TYPE_EXTRACTION = 0x1B   # documented; live extraction telemetry
EM_TYPE_STATUS     = 0x1D   # undocumented but observed; idle heartbeat
EM_FRAME_LEN = 10
EM_UUID_SERVICE    = 0x0FFF
EM_UUID_COMMAND    = 0xFF01
EM_UUID_EXTRACTION = 0xFF02
EM_UUID_STATUS     = 0xFF03   # undocumented
EM_UUID_DEBUG      = 0xFF04   # undocumented Zephyr log; ignore at runtime

SIGN_PLUS  = 0x2B   # '+'
SIGN_MINUS = 0x2D   # '-'


def _xor_checksum(b, length):
    s = 0
    for i in range(length):
        s ^= b[i]
    return s


def _sign(byte_value):
    if byte_value == SIGN_MINUS:
        return -1
    if byte_value == SIGN_PLUS:
        return 1
    return 0


# ── Mini Scale weight frame ──────────────────────────────────────

def parse_scale_frame(b):
    """Parse a 20-byte 0xFF11 weight notification.

    Returns a dict on success, None on any validation failure.
    """
    if len(b) != SCALE_FRAME_LEN:
        return None
    if b[0] != SCALE_HDR1 or b[1] != SCALE_HDR2:
        return None
    if _xor_checksum(b, 19) != b[19]:
        return None

    # timer: bytes 2-4 (uint24 BE) milliseconds
    timer_ms = (b[2] << 16) | (b[3] << 8) | b[4]

    # weight: byte 6 sign, bytes 7-9 magnitude (uint24 BE), units 0.01 g
    weight_cg = (b[7] << 16) | (b[8] << 8) | b[9]
    weight_g = _sign(b[6]) * weight_cg / 100.0

    # flow: byte 10 sign, bytes 11-12 magnitude (uint16 BE), units 0.01 g/s
    flow_cgs = (b[11] << 8) | b[12]
    flow_gps = _sign(b[10]) * flow_cgs / 100.0

    return {
        "timer_s":        timer_ms / 1000.0,
        "unit":           b[5],
        "weight_g":       weight_g,
        "flow_gps":       flow_gps,
        "battery_pct":    b[13],
        "standby_min":    (b[14] << 8) | b[15],
        "buzzer_gear":    b[16],
        "flow_smoothing": b[17],
    }


# ── Espresso Monitor frames ──────────────────────────────────────

def parse_em_extraction(b):
    """Parse a 10-byte 0x1B extraction frame from char 0xFF02."""
    if len(b) != EM_FRAME_LEN:
        return None
    if b[0] != EM_HDR1 or b[1] != EM_TYPE_EXTRACTION:
        return None
    if _xor_checksum(b, 9) != b[9]:
        return None
    pressure_cb = (b[4] << 8) | b[5]   # centi-bar
    return {
        "pressure_bar":  pressure_cb / 100.0,
        "battery_pct":   b[6],
    }


def parse_em_status(b):
    """Parse a 10-byte 0x1D heartbeat frame from char 0xFF03 (undocumented)."""
    if len(b) != EM_FRAME_LEN:
        return None
    if b[0] != EM_HDR1 or b[1] != EM_TYPE_STATUS:
        return None
    if _xor_checksum(b, 9) != b[9]:
        return None
    return {
        "battery_pct":  b[4],
    }


# ── Command encoders ─────────────────────────────────────────────
#
# Note: the doc's command table contains some incorrect checksum values
# (e.g. start-timer shown as 0x0A but XOR gives 0x0D).  The XOR algorithm
# is verified via the receive direction — using algorithm, not the table.

def _cmd_scale(d1, d2=0x00, d3=0x00):
    body = bytes([SCALE_HDR1, 0x0A, d1, d2, d3])
    return body + bytes([_xor_checksum(body, 5)])


def cmd_scale_tare():           return _cmd_scale(0x01)
def cmd_scale_start_timer():    return _cmd_scale(0x04)
def cmd_scale_stop_timer():     return _cmd_scale(0x05)
def cmd_scale_reset_timer():    return _cmd_scale(0x06)
def cmd_scale_tare_and_start(): return _cmd_scale(0x07)


def cmd_scale_set_buzzer(level):
    """level in 0..5; 0 silences the beeper."""
    if not 0 <= level <= 5:
        raise ValueError("buzzer level out of range 0..5")
    return _cmd_scale(0x02, 0x00, level)


def cmd_scale_set_auto_off_minutes(minutes):
    """minutes in 5..30."""
    if not 5 <= minutes <= 30:
        raise ValueError("auto-off out of range 5..30 minutes")
    return _cmd_scale(0x03, 0x00, minutes)


def cmd_scale_set_flow_smoothing(on):
    return _cmd_scale(0x08, 0x01 if on else 0x00, 0x00)


def _cmd_em(d1):
    body = bytes([EM_HDR1, 0x0C, d1, 0x00, 0x00, 0x00])
    return body + bytes([_xor_checksum(body, 6)])


def cmd_em_start_extraction(): return _cmd_em(0x01)
def cmd_em_stop_extraction():  return _cmd_em(0x00)
