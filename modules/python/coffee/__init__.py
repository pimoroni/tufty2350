"""Badger × Bookoo — live brew display.

Architecture:
- badgeware.run(update) is the main loop: rendering + IO at the SDK's cadence.
- BLE uses raw bluetooth.BLE().irq() for notifications.  No asyncio, no aioble.
- Multi-target: each peripheral (scale, espresso monitor) has its own Target
  object; the IRQ dispatches by conn_handle.  update() walks the target list
  and (re)kicks a scan whenever one needs connecting.  Concurrent dual-central
  is enabled by the M6.5 custom firmware (btstack MAX_NR_HCI_CONNECTIONS=3).
"""
import sys, os, json
# Best-effort cwd setup; harmless if /coffee/ doesn't exist on LFS
# (e.g., when this module is frozen into the firmware build).
try:
    sys.path.insert(0, "/coffee")
except Exception:
    pass
try:
    os.chdir("/coffee")
except Exception:
    pass

import bluetooth
import time
import powman

import badgeware
from badgeware import (
    screen, brushes, shapes, io,
    PixelFont, Matrix,
    get_battery_level, is_charging,
    WIDTH, HEIGHT,
)

from . import bookoo

# ── BLE constants (MicroPython bluetooth IRQ event codes) ─────────
_IRQ_SCAN_RESULT                = 5
_IRQ_SCAN_DONE                  = 6
_IRQ_PERIPHERAL_CONNECT         = 7
_IRQ_PERIPHERAL_DISCONNECT      = 8
_IRQ_GATTC_SERVICE_RESULT       = 9
_IRQ_GATTC_SERVICE_DONE         = 10
_IRQ_GATTC_CHARACTERISTIC_RESULT = 11
_IRQ_GATTC_CHARACTERISTIC_DONE   = 12
_IRQ_GATTC_WRITE_DONE           = 17
_IRQ_GATTC_NOTIFY               = 18

ADDR_TYPE_PUBLIC = 0
ADDR_TYPE_RANDOM = 1

SCALE_MAC_HEX = "db:fb:08:6e:5b:c7"
EM_MAC_HEX    = "ee:82:df:cf:24:56"

# ── M7 persistence + backoff constants ──────────────────────────
_STATE_PATH             = "/state/coffee.json"
_STATE_SCHEMA_VERSION   = 1
_BACKOFF_INITIAL_MS     = 1000
_BACKOFF_MAX_MS         = 30_000

# ── M8 power-state constants ────────────────────────────────────
IDLE_BACKLIGHT_TIMEOUT_MS = 60_000
_BL_SMOOTH_VAL_ON         = 1.0
_BL_SMOOTH_VAL_OFF        = 0.0
# `powman.goto_dormant_for` takes a single positional float in
# **seconds** (probed 2026-04-26).  86 400 s = 24 h.  This is the
# RTC safety-net for "C long-press soft-off"; the user wakes the
# badge by pressing RESET (always works), or via VBUS plug-in when
# off-battery.  Auto-button-wake during dormant requires Pin.irq
# wake-source configuration that the SDK does not expose cleanly
# from MicroPython on this build; deferred.
_DORMANT_DURATION_S       = 86_400.0

UUID_SVC_SCALE    = bluetooth.UUID(bookoo.SCALE_UUID_SERVICE)
UUID_CHAR_WEIGHT  = bluetooth.UUID(bookoo.SCALE_UUID_WEIGHT)
UUID_CHAR_CMD_SC  = bluetooth.UUID(bookoo.SCALE_UUID_COMMAND)

UUID_SVC_EM       = bluetooth.UUID(bookoo.EM_UUID_SERVICE)
UUID_CHAR_EM_EXT  = bluetooth.UUID(bookoo.EM_UUID_EXTRACTION)
UUID_CHAR_EM_STAT = bluetooth.UUID(bookoo.EM_UUID_STATUS)
UUID_CHAR_CMD_EM  = bluetooth.UUID(bookoo.EM_UUID_COMMAND)

# ── Palette ──────────────────────────────────────────────────────
BG        = brushes.color(0, 0, 0)
AMBER     = brushes.color(255, 176, 0)
GREEN     = brushes.color(51, 255, 102)
RED       = brushes.color(255, 48, 48)
CYAN      = brushes.color(0, 207, 255)
SLATE     = brushes.color(74, 99, 120)
SLATE_DIM = brushes.color(42, 53, 64)
WHITE     = brushes.color(244, 244, 245)


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
    # "running" flag, so we infer from whether the timer field has changed
    # recently.
    _timer_prev = 0.0
    _timer_last_change_ms = 0
    _pres_last_change_ms = 0


# ── Pressure colour-coding ───────────────────────────────────────
def pres_brush(bar):
    if bar > 11.0:
        return RED
    if bar >= 6.0:
        return GREEN
    return AMBER


# ── Layout (160 x 120) ───────────────────────────────────────────
HDR_H     = 10
PRIM_TOP  = HDR_H + 1
PRIM_H    = 46
SEC_TOP   = PRIM_TOP + PRIM_H + 1
SEC_H     = 24
TREND_TOP = SEC_TOP + SEC_H + 1
TREND_H   = 14
FOOT_TOP  = TREND_TOP + TREND_H + 1
COL_W     = WIDTH // 2

TREND_N = 16
TREND_STRIDE = WIDTH // (TREND_N - 1)
trend_pres = [0.0] * TREND_N
trend_flow = [0.0] * TREND_N

# ── Cached shape primitives ──────────────────────────────────────
PIX  = shapes.rectangle(0, 0, 1, 1)
DOT2 = shapes.rectangle(0, 0, 2, 2)
DOT3 = shapes.rectangle(0, 0, 3, 3)
HLINE_FULL  = shapes.rectangle(0, 0, WIDTH, 1)
BAT_BORDER  = shapes.rectangle(0, 0, 13, 6)
BAT_INNER   = shapes.rectangle(0, 0, 11, 4)
BAT_CELL    = shapes.rectangle(0, 0, 2, 4)
VDIV_PRIM = None
VDIV_SEC  = None

font_lg = None
font_sm = None


def _load_fonts():
    global font_lg, font_sm
    if font_lg is None:
        # Pimoroni stock /rom/fonts/ first; fallback to Mona-OS
        # /system/assets/fonts/.  Heap is tight (~25 KB free after
        # coffee import) so gc between loads, and if the second
        # font won't fit, share the large one — readable but
        # cramped is acceptable for M6.5 ship gate (M8.5 polishes).
        import gc
        for prefix in ("/rom/fonts", "/system/assets/fonts"):
            try:
                gc.collect()
                font_lg = PixelFont.load(prefix + "/absolute.ppf")
                gc.collect()
                try:
                    font_sm = PixelFont.load(prefix + "/ark.ppf")
                except MemoryError:
                    font_sm = font_lg
                gc.collect()
                return
            except Exception:
                font_lg = font_sm = None
        raise OSError("no PPF fonts found in /rom/fonts or /system/assets/fonts")


# ── Drawing helpers ──────────────────────────────────────────────

def _hline(y):
    HLINE_FULL.transform = Matrix().translate(0, y)
    screen.brush = SLATE_DIM
    screen.draw(HLINE_FULL)


def _draw_pix(x, y, brush, shape=PIX):
    shape.transform = Matrix().translate(x, y)
    screen.brush = brush
    screen.draw(shape)


def draw_dividers():
    screen.brush = SLATE_DIM
    _hline(HDR_H)
    _hline(SEC_TOP - 1)
    _hline(TREND_TOP - 1)
    _hline(FOOT_TOP - 1)
    if VDIV_PRIM is not None:
        VDIV_PRIM.transform = Matrix().translate(COL_W, PRIM_TOP)
        screen.draw(VDIV_PRIM)
        VDIV_SEC.transform = Matrix().translate(COL_W, SEC_TOP)
        screen.draw(VDIV_SEC)


def draw_header():
    screen.font = font_sm
    x = 3
    for tag, ok in (("S", State.scale_link), ("P", State.pres_link)):
        _draw_pix(x, 3, GREEN if ok else SLATE, DOT3)
        screen.brush = SLATE
        screen.text(tag, x + 5, 1)
        x += 14

    if is_charging():
        label = "chg"
        pct = get_battery_level()
    else:
        pct = get_battery_level()
        label = f"{pct}%"
    cells = max(0, min(4, (pct + 12) // 25))

    cx = WIDTH - 4 - 14
    BAT_BORDER.transform = Matrix().translate(cx, 2)
    screen.brush = SLATE
    screen.draw(BAT_BORDER)
    BAT_INNER.transform = Matrix().translate(cx + 1, 3)
    screen.brush = BG
    screen.draw(BAT_INNER)
    for i in range(cells):
        BAT_CELL.transform = Matrix().translate(cx + 1 + i * 3, 3)
        screen.brush = CYAN
        screen.draw(BAT_CELL)

    w, _ = screen.measure_text(label)
    screen.brush = CYAN
    screen.text(label, cx - 2 - w, 1)


def _big_value(value_str, unit_str, x, y, value_brush):
    screen.font = font_lg
    screen.brush = value_brush
    screen.text(value_str, x, y)
    vw, vh = screen.measure_text(value_str)
    screen.font = font_sm
    screen.brush = CYAN
    _, uh = screen.measure_text(unit_str)
    screen.text(unit_str, x + vw + 2, y + vh - uh)


def _med_value(value_str, unit_str, x, y, value_brush):
    screen.font = font_sm
    screen.brush = value_brush
    screen.text(value_str, x, y)
    vw, _ = screen.measure_text(value_str)
    screen.brush = SLATE
    screen.text(unit_str, x + vw + 2, y)


def _small_label(label, x, y):
    screen.font = font_sm
    screen.brush = SLATE
    screen.text(label, x, y)


def draw_primary():
    val_y = PRIM_TOP + 4
    lab_y = PRIM_TOP + PRIM_H - 9
    _big_value(f"{State.mass:.1f}", "g",   6, val_y, AMBER)
    _small_label("MASS", 6, lab_y)
    _big_value(f"{State.pres:.1f}", "bar", COL_W + 5, val_y, pres_brush(State.pres))
    _small_label("PRES", COL_W + 5, lab_y)


def draw_secondary():
    val_y = SEC_TOP + 2
    lab_y = SEC_TOP + SEC_H - 9
    _med_value(f"{State.time:.1f}", "s",   6, val_y, WHITE)
    _small_label("TIME", 6, lab_y)
    _med_value(f"{State.flow:.1f}", "g/s", COL_W + 5, val_y, CYAN)
    _small_label("FLOW", COL_W + 5, lab_y)


def draw_trend():
    screen.brush = AMBER
    for i in range(TREND_N):
        v = trend_pres[i]
        if v < 0: v = 0
        if v > 12.0: v = 12.0
        x = i * TREND_STRIDE
        y = TREND_TOP + TREND_H - 2 - int((v / 12.0) * (TREND_H - 2))
        DOT2.transform = Matrix().translate(x, y)
        screen.draw(DOT2)
    screen.brush = CYAN
    for i in range(TREND_N):
        v = trend_flow[i]
        if v < 0: v = 0
        if v > 4.0: v = 4.0
        x = i * TREND_STRIDE
        y = TREND_TOP + TREND_H - 2 - int((v / 4.0) * (TREND_H - 2))
        DOT2.transform = Matrix().translate(x, y)
        screen.draw(DOT2)


def draw_footer():
    screen.font = font_sm
    label = State.session
    w, _ = screen.measure_text(label)
    pill_w = w + 12
    px = WIDTH // 2 - pill_w // 2
    py = FOOT_TOP + (22 - 8) // 2
    if State.session == "LIVE":
        col = GREEN
    elif State.session == "STOPPED":
        col = AMBER
    else:
        col = SLATE
    _draw_pix(px + 2, py + 2, col, DOT3)
    screen.brush = col
    screen.text(label, px + 8, py)


# ── Notify parsers ───────────────────────────────────────────────

def _parse_scale(raw):
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


def _parse_em_extraction(raw):
    f = bookoo.parse_em_extraction(bytes(raw))
    if f is None:
        return
    State.pres                 = f["pressure_bar"]
    State.em_battery           = f["battery_pct"]
    State._pres_last_change_ms = time.ticks_ms()


def _parse_em_status(raw):
    f = bookoo.parse_em_status(bytes(raw))
    if f is None:
        return
    State.em_battery = f["battery_pct"]


# ── BLE state machine via raw IRQ ────────────────────────────────

class Target:
    """One BLE peripheral and its state-machine progress."""
    NONE       = 0
    CONNECTING = 2
    DISC_SVC   = 3
    DISC_CHAR  = 4
    ENABLING   = 5
    READY      = 6

    def __init__(self, name, mac_hex, service_uuid, char_specs,
                 link_attr, cmd_uuid=None):
        # `char_specs` is a list of (uuid, parser_fn) for chars to subscribe.
        # `cmd_uuid` (optional) is a write-target char whose handle we also
        # capture during char discovery, for M6 button-driven commands.
        self.name             = name
        self.mac              = bytes(int(p, 16) for p in mac_hex.split(":"))
        self.service_uuid     = service_uuid
        self.char_specs       = char_specs
        self.link_attr        = link_attr
        self.cmd_uuid         = cmd_uuid
        # M7: addr_type hint persisted across resets so direct-connect
        # can be retried on next boot without scanning first.
        self._addr_type_hint  = None
        self.rescan_delay_ms  = _BACKOFF_INITIAL_MS
        self._auto_off_set    = False
        self.reset()

    def reset(self):
        # Restore addr_type from the persisted hint so the watchdog's
        # direct-connect retry path still has a valid type.
        self.addr_type    = self._addr_type_hint
        self.state        = self.NONE
        self.conn_handle  = None
        self.svc_start    = None
        self.svc_end      = None
        self.chars        = {}    # value_handle -> parser_fn
        self.subs_pending = []    # value_handles still to subscribe
        self.cmd_handle   = None
        setattr(State, self.link_attr, False)

    def apply_hint(self, hint):
        """Populate addr_type from /state/coffee.json so the boot path can
        skip scan-first for this target.  Hint is a dict from
        `_load_target_hints()`."""
        addr_type = hint.get("addr_type")
        mac_str   = hint.get("mac")
        if not isinstance(addr_type, int) or not isinstance(mac_str, str):
            return
        try:
            mac_b = bytes(int(p, 16) for p in mac_str.split(":"))
        except (ValueError, AttributeError):
            return
        if mac_b != self.mac:
            return
        self._addr_type_hint = addr_type
        self.addr_type       = addr_type


class BLE:
    scanning          = False
    last_scan_kick_ms = 0
    targets           = []        # populated in init()
    by_conn           = {}        # conn_handle -> Target
    # M7: targets queued for hint-persist (deferred to update() so we
    # never do file IO from inside a BLE IRQ).
    save_pending      = set()


ble = bluetooth.BLE()


def _target_named(name):
    for t in BLE.targets:
        if t.name == name:
            return t
    return None


def _start_scan():
    """Kick a fresh continuous scan (no-op if already scanning)."""
    if BLE.scanning:
        return
    try:
        ble.gap_scan(0, 30_000, 30_000, True)
        BLE.scanning = True
        BLE.last_scan_kick_ms = time.ticks_ms()
    except Exception:
        pass


def _load_target_hints():
    """Return {name: hint_dict} from /state/coffee.json, or {} on any
    parse error.  Treated as a hint, never as authority — corruption
    falls back to hard-coded MACs."""
    try:
        with open(_STATE_PATH, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if (not isinstance(data, dict)
            or data.get("v") != _STATE_SCHEMA_VERSION):
        return {}
    targets = data.get("targets")
    if not isinstance(targets, dict):
        return {}
    return targets


def _save_target_hint(t):
    """Merge target's (mac, addr_type) into /state/coffee.json atomically.
    Foreground-only — never call from an IRQ."""
    try:
        try:
            os.mkdir("/state")
        except OSError:
            pass
        existing = _load_target_hints()
        existing[t.name] = {
            "mac":       ":".join("%02x" % b for b in t.mac),
            "addr_type": t.addr_type,
        }
        payload = {"v": _STATE_SCHEMA_VERSION, "targets": existing}
        tmp = _STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.rename(tmp, _STATE_PATH)
    except Exception:
        pass


def _attempt_direct_connect(t):
    """Skip the scan; gap_connect using the persisted addr_type hint.
    Returns True if the API call did not raise; CONNECT IRQ (or its
    absence after timeout) determines actual success."""
    if t._addr_type_hint is None:
        return False
    try:
        ble.gap_connect(t._addr_type_hint, t.mac)
        t.state = Target.CONNECTING
        BLE.last_scan_kick_ms = time.ticks_ms()
        return True
    except Exception:
        t.state = Target.NONE
        return False


def _kick_next_subscribe(t):
    while t.subs_pending:
        h = t.subs_pending[0]
        try:
            ble.gattc_write(t.conn_handle, h + 1, b"\x01\x00", 1)
            return
        except Exception:
            t.subs_pending.pop(0)
    t.state = Target.READY
    # M7: reset backoff on successful READY; queue hint-persist for
    # the foreground; on first scale READY, extend its idle auto-off
    # to 30 min so future autonomous sessions have a 30-min grace.
    t.rescan_delay_ms = _BACKOFF_INITIAL_MS
    BLE.save_pending.add(t.name)
    if (t.name == "scale"
            and not t._auto_off_set
            and t.cmd_handle is not None):
        try:
            ble.gattc_write(
                t.conn_handle, t.cmd_handle,
                bookoo.cmd_scale_set_auto_off_minutes(30), 1)
            t._auto_off_set = True
        except Exception:
            pass
    setattr(State, t.link_attr, True)


def _ble_irq(event, data):
    try:
        if event == _IRQ_SCAN_RESULT:
            if not BLE.scanning:
                return
            addr_type, addr, _adv_type, _rssi, _adv_data = data
            addr_b = bytes(addr)
            for t in BLE.targets:
                if t.state == Target.NONE and addr_b == t.mac:
                    try:
                        ble.gap_scan(None)
                    except Exception:
                        pass
                    BLE.scanning = False
                    t.addr_type = addr_type
                    t.state     = Target.CONNECTING
                    try:
                        ble.gap_connect(addr_type, addr_b)
                    except Exception:
                        t.state = Target.NONE
                    return

        elif event == _IRQ_SCAN_DONE:
            BLE.scanning = False

        elif event == _IRQ_PERIPHERAL_CONNECT:
            conn_handle, _addr_type, addr = data
            addr_b = bytes(addr)
            for t in BLE.targets:
                if t.state == Target.CONNECTING and addr_b == t.mac:
                    t.conn_handle    = conn_handle
                    BLE.by_conn[conn_handle] = t
                    t.svc_start      = None
                    t.chars          = {}
                    t.subs_pending   = []
                    t.cmd_handle     = None
                    t.state          = Target.DISC_SVC
                    ble.gattc_discover_services(conn_handle)
                    return

        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            conn_handle, _addr_type, _addr = data
            t = BLE.by_conn.pop(conn_handle, None)
            if t is not None:
                # M7: exponential backoff — double the rescan interval
                # up to 30 s.  Reset on successful READY transition.
                t.rescan_delay_ms = min(
                    t.rescan_delay_ms * 2, _BACKOFF_MAX_MS)
                t.reset()

        elif event == _IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start_handle, end_handle, uuid = data
            t = BLE.by_conn.get(conn_handle)
            if t is not None and uuid == t.service_uuid:
                t.svc_start = start_handle
                t.svc_end   = end_handle

        elif event == _IRQ_GATTC_SERVICE_DONE:
            conn_handle, _status = data
            t = BLE.by_conn.get(conn_handle)
            if t is None:
                return
            if t.svc_start is not None:
                t.state = Target.DISC_CHAR
                ble.gattc_discover_characteristics(
                    t.conn_handle, t.svc_start, t.svc_end
                )
            else:
                try:
                    ble.gap_disconnect(t.conn_handle)
                except Exception:
                    pass

        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            conn_handle, _def_handle, value_handle, _properties, uuid = data
            t = BLE.by_conn.get(conn_handle)
            if t is None:
                return
            for spec_uuid, parser in t.char_specs:
                if uuid == spec_uuid:
                    t.chars[value_handle] = parser
                    t.subs_pending.append(value_handle)
                    break
            if t.cmd_uuid is not None and uuid == t.cmd_uuid:
                t.cmd_handle = value_handle

        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            conn_handle, _status = data
            t = BLE.by_conn.get(conn_handle)
            if t is None:
                return
            if t.subs_pending:
                t.state = Target.ENABLING
                _kick_next_subscribe(t)
            else:
                try:
                    ble.gap_disconnect(t.conn_handle)
                except Exception:
                    pass

        elif event == _IRQ_GATTC_WRITE_DONE:
            conn_handle, _value_handle, _status = data
            t = BLE.by_conn.get(conn_handle)
            if t is None:
                return
            if t.state == Target.ENABLING and t.subs_pending:
                t.subs_pending.pop(0)
                _kick_next_subscribe(t)

        elif event == _IRQ_GATTC_NOTIFY:
            conn_handle, value_handle, notify_data = data
            t = BLE.by_conn.get(conn_handle)
            if t is None:
                return
            parser = t.chars.get(value_handle)
            if parser is not None:
                parser(notify_data)

    except Exception:
        # IRQ handlers must not raise.
        pass


_combo_frames = 0
_c_hold_frames = 0

# M8 idle-backlight tracking (set in init(), updated by update()).
_idle_since_ms = 0
_backlight_on  = True


def _set_backlight(on):
    """Force-set backlight by pre-loading badgeware's smoothing buffer.
    `update_backlight()` runs each frame inside `badgeware.run()` and
    reads this buffer; pre-loading is the only reliable way to override
    the auto-mode without fighting it (R8 / LEARNINGS)."""
    global _backlight_on
    target = _BL_SMOOTH_VAL_ON if on else _BL_SMOOTH_VAL_OFF
    try:
        for i in range(badgeware.MAX_BACKLIGHT_SAMPLES):
            badgeware.backlight_smoothing[i] = target
        _backlight_on = on
    except Exception:
        pass


def _enter_dormant():
    """C long-press soft-off: clean BLE shutdown, then dormant sleep.
    Wake source is RESET button (always works) or VBUS-detect (USB
    plug/unplug); the 24 h duration is an RTC safety-net.  Wake re-
    cold-boots the badge into /coffee/.  M7's persistence keeps the
    wake-to-READY path fast."""
    print("[coffee] entering dormant; press RESET to wake")
    _shutdown()
    try:
        powman.goto_dormant_for(_DORMANT_DURATION_S)
    except Exception as e:
        print("[coffee] dormant err: %r" % e)


def _shutdown():
    """Clean BLE teardown: gap_disconnect every active link, sleep so the
    controller releases session state.  Mitigates R14 ('zeros stream')
    on the next badge connect to the scale."""
    for ch in list(BLE.by_conn.keys()):
        try:
            ble.gap_disconnect(ch)
        except Exception:
            pass
    time.sleep_ms(500)


def _all_three_held():
    held = io.held
    return (io.BUTTON_A in held and io.BUTTON_B in held
            and io.BUTTON_C in held)


def _check_repl_combo():
    """A+B+C held for ~1 s in update() → drop to REPL.

    NEXT_PLAN.md §3: gives a reliable in-app exit when the boot-time
    escape-hatch dance fails (CDC starvation under tight render loop).
    """
    global _combo_frames
    if _all_three_held():
        _combo_frames += 1
        if _combo_frames >= 10:
            print("[coffee] A+B+C held; dropping to REPL")
            _shutdown()
            sys.exit()
    else:
        _combo_frames = 0


def _scale_target():
    for t in BLE.targets:
        if t.name == "scale":
            return t
    return None


def _dispatch_buttons():
    """Map buttons to scale commands when the scale is READY.  C long-press
    → enter dormant.  Suppressed while the A+B+C REPL combo is active so
    a debug-exit doesn't also tare/reset.
    """
    global _c_hold_frames
    if _all_three_held():
        _c_hold_frames = 0
        return

    pressed = io.pressed
    held    = io.held

    # M8: C long-press (≥ 1 s) → enter dormant.  Wake re-cold-boots.
    if io.BUTTON_C in held:
        _c_hold_frames += 1
        if _c_hold_frames == 10:
            _enter_dormant()
            return
    else:
        _c_hold_frames = 0

    scale = _scale_target()
    if scale is None or scale.state != Target.READY or scale.cmd_handle is None:
        return

    cmd = None
    if io.BUTTON_A in pressed:
        cmd = bookoo.cmd_scale_tare()
    elif io.BUTTON_B in pressed:
        cmd = bookoo.cmd_scale_reset_timer()
    elif io.BUTTON_UP in pressed:
        cmd = bookoo.cmd_scale_tare_and_start()
    elif io.BUTTON_DOWN in pressed:
        cmd = bookoo.cmd_scale_stop_timer()
    if cmd is None:
        return
    try:
        ble.gattc_write(scale.conn_handle, scale.cmd_handle, cmd, 1)
    except Exception:
        pass


def update():
    """Called by badgeware.run().  Render + service the BLE state machine."""
    now = time.ticks_ms()

    # Invariant (R2 leak guard, observed 2026-04-26): state==NONE must
    # imply conn_handle is None.  If a phantom CONNECT-without-disconnect
    # left a leaked handle, reset before any other logic touches it.
    for t in BLE.targets:
        if t.state == Target.NONE and t.conn_handle is not None:
            BLE.by_conn.pop(t.conn_handle, None)
            t.reset()

    # M7: drain pending hint persistence (set in IRQ on READY).  File
    # IO must not happen in IRQ context; doing it here is safe.
    while BLE.save_pending:
        name = BLE.save_pending.pop()
        t = _target_named(name)
        if t is not None:
            _save_target_hint(t)

    _check_repl_combo()
    _dispatch_buttons()

    # M8 idle-backlight: any button press OR non-IDLE session resets the
    # timer.  After IDLE_BACKLIGHT_TIMEOUT_MS, force backlight off via
    # the smoothing-buffer trick.
    global _idle_since_ms, _backlight_on
    if len(io.pressed) > 0 or State.session != "IDLE":
        _idle_since_ms = now
        if not _backlight_on:
            _set_backlight(True)
    elif _backlight_on and time.ticks_diff(now, _idle_since_ms) > IDLE_BACKLIGHT_TIMEOUT_MS:
        _set_backlight(False)

    # Derive session pill: combine scale-timer activity with EM pressure
    # presence (extraction → pres > 0.5 bar).  Either signal pulls us into
    # LIVE; loss of both with timer non-zero → STOPPED; otherwise IDLE.
    timer_running = (
        State.time != 0.0
        and time.ticks_diff(now, State._timer_last_change_ms) <= 1500
    )
    pres_active = State.pres > 0.5
    if timer_running or pres_active:
        State.session = "LIVE"
    elif State.time != 0.0:
        State.session = "STOPPED"
    else:
        State.session = "IDLE"

    # Render.
    screen.brush = BG
    screen.clear()
    draw_dividers()
    draw_header()
    draw_primary()
    draw_secondary()
    draw_trend()
    draw_footer()

    # State-machine watchdog (M6.5 dual-central + M7 backoff): kick a
    # scan whenever any target is unconnected.  Use the minimum
    # rescan_delay_ms across NONE targets so a recently-woken target
    # gets re-tried promptly.  Restart any scan that's been running
    # > 15 s.
    none_targets = [t for t in BLE.targets if t.state == Target.NONE]
    if none_targets and not BLE.scanning:
        min_delay = min(t.rescan_delay_ms for t in none_targets)
        if time.ticks_diff(now, BLE.last_scan_kick_ms) > min_delay:
            _start_scan()
    elif BLE.scanning and time.ticks_diff(now, BLE.last_scan_kick_ms) > 15_000:
        try:
            ble.gap_scan(None)
        except Exception:
            pass
        BLE.scanning = False


def init():
    """Sync setup; returns normally so /system/main.py can call run(update)."""
    global VDIV_PRIM, VDIV_SEC, _idle_since_ms
    _load_fonts()
    VDIV_PRIM = shapes.rectangle(0, 0, 1, PRIM_H)
    VDIV_SEC  = shapes.rectangle(0, 0, 1, SEC_H)

    # M8: initialise idle-backlight tracking; force backlight on in
    # case we're cold-booting from a dormant wake with a stale
    # smoothing buffer.
    _idle_since_ms = time.ticks_ms()
    _set_backlight(True)

    BLE.targets = [
        Target(
            "scale", SCALE_MAC_HEX, UUID_SVC_SCALE,
            [(UUID_CHAR_WEIGHT, _parse_scale)],
            "scale_link",
            cmd_uuid=UUID_CHAR_CMD_SC,
        ),
        Target(
            "em", EM_MAC_HEX, UUID_SVC_EM,
            [
                (UUID_CHAR_EM_EXT,  _parse_em_extraction),
                (UUID_CHAR_EM_STAT, _parse_em_status),
            ],
            "pres_link",
            cmd_uuid=UUID_CHAR_CMD_EM,
        ),
    ]

    # M7: read /state/coffee.json hints — addr_type lets us skip the
    # scan on the boot path.  Hints are merge-by-name; corruption falls
    # back silently to the hard-coded MACs.
    hints = _load_target_hints()
    for t in BLE.targets:
        h = hints.get(t.name)
        if h:
            t.apply_hint(h)

    # Bring up BLE radio (cycle to flush controller GATT cache, R13) and
    # install the IRQ handler.  Discovery and subscription are driven
    # entirely from the IRQ callback.
    try:
        ble.active(False)
    except Exception:
        pass
    ble.active(True)
    ble.irq(_ble_irq)

    # M7: for each target with a persisted addr_type hint, attempt
    # gap_connect directly.  The watchdog will fall back to scan after
    # `rescan_delay_ms` if no CONNECT IRQ arrives.
    for t in BLE.targets:
        if t._addr_type_hint is not None:
            _attempt_direct_connect(t)
    if any(t.state == Target.NONE for t in BLE.targets):
        _start_scan()
