"""Badger × Bookoo — live brew display.

Architecture:
- badgeware.run(update) is the main loop: rendering + IO at the SDK's cadence.
- BLE uses raw bluetooth.BLE().irq() for notifications.  No asyncio, no aioble.
- Multi-target: each peripheral (scale, espresso monitor) has its own Target
  object; the IRQ dispatches by conn_handle.  update() walks the target list
  and (re)kicks a scan whenever one needs connecting.  Concurrent dual-central
  is enabled by the M6.5 custom firmware (btstack MAX_NR_HCI_CONNECTIONS=3).

Module layout (post-§8.2 split):
- coffee/palette.py    — six semantic colour tokens
- coffee/layout.py     — pixel-level grid (160 × 120)
- coffee/state.py      — `State` + pressure colour state machine (hysteresis)
- coffee/widgets.py    — header sub-elements (links, state dot, battery)
- coffee/trend.py      — 30 s rolling ring buffer + curve renderer
- coffee/render.py     — partial-redraw orchestrator (dirty flags)
- coffee/ble/scale.py
- coffee/ble/pressure.py
- coffee/__init__.py   — BLE state machine + button dispatch + update/init
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
    screen, io, PixelFont, WIDTH,
)

from . import bookoo
from .state import State
from . import render

# Expose the IRQ char_specs by their original names (re-exported by
# coffee/ble/__init__.py).
from .ble import _parse_scale, _parse_em_extraction, _parse_em_status


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

UUID_SVC_SCALE    = bluetooth.UUID(bookoo.SCALE_UUID_SERVICE)
UUID_CHAR_WEIGHT  = bluetooth.UUID(bookoo.SCALE_UUID_WEIGHT)
UUID_CHAR_CMD_SC  = bluetooth.UUID(bookoo.SCALE_UUID_COMMAND)

UUID_SVC_EM       = bluetooth.UUID(bookoo.EM_UUID_SERVICE)
UUID_CHAR_EM_EXT  = bluetooth.UUID(bookoo.EM_UUID_EXTRACTION)
UUID_CHAR_EM_STAT = bluetooth.UUID(bookoo.EM_UUID_STATUS)
UUID_CHAR_CMD_EM  = bluetooth.UUID(bookoo.EM_UUID_COMMAND)


# ── Fonts ────────────────────────────────────────────────────────
font_lg = None
font_sm = None


def _load_fonts():
    global font_lg, font_sm
    if font_lg is None:
        # Departure Mono first (style brief §3 — preferred); fall back to
        # Pimoroni stock absolute/ark if the Departure Mono PPFs aren't
        # present (e.g. on a firmware that didn't bake them into /rom/).
        # gc between loads — heap is tight (~25 KB free after coffee
        # import); on MemoryError on the second load, share the large
        # font as the small one (readable but cramped).
        import gc
        # Departure Mono renders pixel-perfect at multiples of 11 px
        # (per its README); 22 + 11 fit LORES legibly with crisp
        # 1-bit glyphs.  Sub-grid sizes (28, 10) get mangled by the
        # 1-bit threshold during conversion.
        candidates = [
            ("/rom/fonts/departure_22.ppf", "/rom/fonts/departure_11.ppf"),
            ("/rom/fonts/absolute.ppf",     "/rom/fonts/ark.ppf"),
            ("/system/assets/fonts/absolute.ppf",
             "/system/assets/fonts/ark.ppf"),
        ]
        for lg_path, sm_path in candidates:
            try:
                gc.collect()
                font_lg = PixelFont.load(lg_path)
                gc.collect()
                try:
                    font_sm = PixelFont.load(sm_path)
                except MemoryError:
                    font_sm = font_lg
                gc.collect()
                return
            except Exception:
                font_lg = font_sm = None
        raise OSError("no PPF fonts found in /rom/fonts or /system/assets/fonts")


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
        self.addr_type    = self._addr_type_hint
        self.state        = self.NONE
        self.conn_handle  = None
        self.svc_start    = None
        self.svc_end      = None
        self.chars        = {}
        self.subs_pending = []
        self.cmd_handle   = None
        setattr(State, self.link_attr, False)
        render.dirty_header = True

    def apply_hint(self, hint):
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
    targets           = []
    by_conn           = {}
    save_pending      = set()


ble = bluetooth.BLE()


def _target_named(name):
    for t in BLE.targets:
        if t.name == name:
            return t
    return None


def _start_scan():
    if BLE.scanning:
        return
    try:
        ble.gap_scan(0, 30_000, 30_000, True)
        BLE.scanning = True
        BLE.last_scan_kick_ms = time.ticks_ms()
    except Exception:
        pass


def _load_target_hints():
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
    render.dirty_header = True


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
                t.rescan_delay_ms = min(
                    t.rescan_delay_ms * 2, _BACKOFF_MAX_MS)
                t.reset()
                # Cascade: scale dropping → kick EM off too.  Without
                # the scale anchor, EM extraction data has no context,
                # and keeping EM connected drains both batteries
                # indefinitely if the operator left.  EM will be
                # re-connected by the watchdog if scale comes back.
                if t.name == "scale":
                    em = _target_named("em")
                    if em is not None and em.conn_handle is not None:
                        try:
                            ble.gap_disconnect(em.conn_handle)
                        except Exception:
                            pass
                    # M9.4: arm the auto-dormant grace timer. Run loop
                    # picks this up at top of update() and either cancels
                    # (if scale reconnects) or fires _enter_dormant().
                    global _dormant_pending_since_ms
                    _dormant_pending_since_ms = time.ticks_ms()

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
_frame_counter = 0

# M8 idle-backlight tracking (set in init(), updated by update()).
_idle_since_ms = 0
_backlight_on  = True

# Auto-dormant trigger (M9.4): scale disconnect with 30 s grace.
# When the scale BLE link drops, start a 30 s grace timer. If the scale
# reconnects within the window, cancel. Otherwise dormant.
#
# Set by _IRQ_PERIPHERAL_DISCONNECT for the scale target only — so cold
# boot with no scale ever connected never sets it, which is the implicit
# "armed" guard. EM disconnects do not set it (per the scale-as-intent
# architectural rule, see feedback_scale_intent_em_telemetry.md).
#
# Grace window absorbs transient BLE glitches without false-dormanting.
_dormant_pending_since_ms = 0
_DORMANT_GRACE_MS         = 30_000  # 30 s


def _set_backlight(on):
    global _backlight_on
    target = _BL_SMOOTH_VAL_ON if on else _BL_SMOOTH_VAL_OFF
    try:
        for i in range(badgeware.MAX_BACKLIGHT_SAMPLES):
            badgeware.backlight_smoothing[i] = target
        _backlight_on = on
    except Exception:
        pass


def _enter_dormant():
    # M9.4: powman.shipping_mode() = powman_off() = hardware off (not
    # dormant clock-gating). Works with USB attached because the SoC
    # actually powers down rather than fighting USB for clock; goto_dormant_for
    # would hard_assert → mp_pico_panic with USB attached.
    print("[coffee] entering dormant; press RESET to wake")
    _shutdown()
    try:
        powman.shipping_mode()
    except Exception as e:
        print("[coffee] dormant err: %r" % e)


def _shutdown():
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
    global _c_hold_frames
    if _all_three_held():
        _c_hold_frames = 0
        return

    pressed = io.pressed
    held    = io.held

    # M8: C long-press (≥ 1 s) → enter dormant.
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
    """Called by badgeware.run().  Service the BLE state machine + render."""
    global _idle_since_ms, _backlight_on, _frame_counter
    global _dormant_pending_since_ms
    now = time.ticks_ms()
    _frame_counter += 1

    # Invariant (R2 leak guard): state==NONE must imply conn_handle is None.
    for t in BLE.targets:
        if t.state == Target.NONE and t.conn_handle is not None:
            BLE.by_conn.pop(t.conn_handle, None)
            t.reset()

    # M7: drain pending hint persistence (set in IRQ on READY).
    while BLE.save_pending:
        name = BLE.save_pending.pop()
        t = _target_named(name)
        if t is not None:
            _save_target_hint(t)

    _check_repl_combo()
    _dispatch_buttons()

    # M8 idle-backlight: any button press OR non-IDLE session resets the timer.
    if len(io.pressed) > 0 or State.session != "IDLE":
        _idle_since_ms = now
        if not _backlight_on:
            _set_backlight(True)
    elif _backlight_on and time.ticks_diff(now, _idle_since_ms) > IDLE_BACKLIGHT_TIMEOUT_MS:
        _set_backlight(False)

    # Clear stale State.pres if no 0x1B extraction frame in the last 2 s.
    # The 0x1D heartbeat doesn't decode any payload bytes, so without this
    # the PRES digit latches at the final reading of the most recent shot
    # (e.g. 9 bar) until the next pull. Cosmetic-only after M9.3 — pres no
    # longer drives session — but kept so the digit reads correctly.
    _PRES_STALE_MS = 2000
    if State.pres != 0.0 and time.ticks_diff(now, State._pres_last_change_ms) > _PRES_STALE_MS:
        State.pres = 0.0

    # M9.3: scale is the only signal of brewing intent. The scale is the
    # active interaction surface (operator taps tare/start/stop); the EM
    # is a passive sensor and must not drive engagement state — otherwise
    # an idle EM at non-zero pressure (boiler steam) keeps the badge
    # awake forever. See feedback_scale_intent_em_telemetry.md.
    timer_running = (
        State.time != 0.0
        and time.ticks_diff(now, State._timer_last_change_ms) <= 1500
    )
    new_session = "IDLE"
    if timer_running:
        new_session = "LIVE"
    elif State.time != 0.0:
        new_session = "STOPPED"

    if new_session != State.session:
        State.session = new_session
        # Session transition → repaint everything.
        render.mark_all_dirty()

    # Render via partial-redraw orchestrator.
    render.tick(font_lg, font_sm, _frame_counter)

    # State-machine watchdog: kick a scan whenever any target is unconnected.
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

    # Auto-dormant (M9.4): scale is the operator's intent surface — if
    # the scale's BLE link drops and stays dropped for the grace window,
    # the brewing session is over and we power down. Set in IRQ on scale
    # disconnect; cleared here when scale reconnects.
    scale = _scale_target()
    if _dormant_pending_since_ms != 0:
        if scale is not None and scale.state == Target.READY:
            _dormant_pending_since_ms = 0
        elif time.ticks_diff(now, _dormant_pending_since_ms) > _DORMANT_GRACE_MS:
            print("[coffee] scale gone %d s; powering down" % (_DORMANT_GRACE_MS // 1000))
            _enter_dormant()
            return


def init():
    """Sync setup; returns normally so /system/main.py can call run(update)."""
    global _idle_since_ms
    _load_fonts()
    render.mark_all_dirty()

    # M8: initialise idle-backlight tracking.
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

    # M7: read /state/coffee.json hints.
    hints = _load_target_hints()
    for t in BLE.targets:
        h = hints.get(t.name)
        if h:
            t.apply_hint(h)

    # Bring up BLE radio.
    try:
        ble.active(False)
    except Exception:
        pass
    ble.active(True)
    ble.irq(_ble_irq)

    for t in BLE.targets:
        if t._addr_type_hint is not None:
            _attempt_direct_connect(t)
    if any(t.state == Target.NONE for t in BLE.targets):
        _start_scan()
