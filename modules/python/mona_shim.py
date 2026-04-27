"""Mona-OS `badgeware` API shim — direct picovector adapter for the
patched Tufty 2350 (3xBLE) UF2 (M6.5 verdict A).

Stock Pimoroni `badgeware` __init__.py attempts to hoist
picovector primitives into `builtins` but `setattr(builtins, ...)`
silently fails on this firmware build, so the apparent
`builtins.image / shape / color / screen` are never set.  We
bypass stock badgeware entirely and use `picovector` + `_input`
directly.

Inject in /main.py BEFORE `import coffee`:

    import sys, mona_shim
    sys.modules['badgeware'] = mona_shim
    import coffee
    coffee.init()
    mona_shim.run(coffee.update)
"""
import sys
import time
import machine
import picovector
import st7789
import _input

# ── Display + framebuffer image ───────────────────────────────────

_display = st7789.ST7789()
_screen = picovector.image(_display.WIDTH, _display.HEIGHT, memoryview(_display))

WIDTH = _display.WIDTH
HEIGHT = _display.HEIGHT

# Default font: Pimoroni stock builds in `rom_font.sins` etc.; our
# shim leaves font as None initially.  coffee.py loads its own via
# PixelFont.load() at init.

# ── Constants coffee.py expects ───────────────────────────────────

MAX_BACKLIGHT_SAMPLES = 8
backlight_smoothing = [1.0] * MAX_BACKLIGHT_SAMPLES

# Buttons — stock uses machine.Pin.board.BUTTON_*; coffee.py uses
# `pin in io.pressed` set tests.  Re-export the same Pin objects.
BUTTON_A = machine.Pin.board.BUTTON_A
BUTTON_B = machine.Pin.board.BUTTON_B
BUTTON_C = machine.Pin.board.BUTTON_C
BUTTON_UP = machine.Pin.board.BUTTON_UP
BUTTON_DOWN = machine.Pin.board.BUTTON_DOWN
BUTTON_HOME = machine.Pin.board.BUTTON_HOME


# ── brushes (→ picovector.color.rgb) ──────────────────────────────

class brushes:
    @staticmethod
    def color(r, g=None, b=None, a=255):
        if g is None and b is None:
            r = g = b = r
        return picovector.color.rgb(int(r), int(g), int(b), int(a))

    @staticmethod
    def xor(r, g=None, b=None, a=255):
        return brushes.color(r, g, b, a)


# ── shapes (→ picovector.shape.*) ─────────────────────────────────

class shapes:
    @staticmethod
    def rectangle(x, y, w, h, radius=0):
        if radius > 0:
            r = int(radius)
            return picovector.shape.rounded_rectangle(
                int(x), int(y), int(w), int(h), r, r, r, r)
        return picovector.shape.rectangle(int(x), int(y), int(w), int(h))

    @staticmethod
    def rounded_rectangle(x, y, w, h, radius, *corner_radii):
        r = int(radius)
        if corner_radii:
            r0 = r
            r1 = int(corner_radii[0]) if len(corner_radii) >= 1 else r
            r2 = int(corner_radii[1]) if len(corner_radii) >= 2 else r
            r3 = int(corner_radii[2]) if len(corner_radii) >= 3 else r
            return picovector.shape.rounded_rectangle(
                int(x), int(y), int(w), int(h), r0, r1, r2, r3)
        return picovector.shape.rounded_rectangle(
            int(x), int(y), int(w), int(h), r, r, r, r)


# ── Matrix (→ picovector.mat3) ────────────────────────────────────
# coffee.py uses `Matrix().translate(x, y)` — picovector.mat3 has
# `translate, rotate, scale, multiply, inverse`.  Need to verify
# that Matrix() constructor works without args.

Matrix = picovector.mat3


# ── PixelFont (→ picovector.pixel_font.load) ──────────────────────

class PixelFont:
    @staticmethod
    def load(path):
        return picovector.pixel_font.load(path)


# ── screen — Mona-OS-shaped surface over picovector image ─────────

class _ScreenAdapter:
    """Mona-OS `screen.brush` / `screen.draw(s)` / `screen.text(...)`
    over picovector `image.pen` / `image.shape(s)` / `image.text(...)`."""

    @property
    def brush(self):
        return _screen.pen

    @brush.setter
    def brush(self, value):
        _screen.pen = value

    @property
    def font(self):
        return _screen.font

    @font.setter
    def font(self, value):
        _screen.font = value

    @property
    def width(self):
        return _screen.width

    @property
    def height(self):
        return _screen.height

    @property
    def antialias(self):
        return getattr(_screen, "antialias", picovector.image.OFF)

    @antialias.setter
    def antialias(self, value):
        try:
            _screen.antialias = value
        except Exception:
            pass

    def clear(self, color=None):
        if color is not None:
            _screen.pen = color
        _screen.clear()

    def draw(self, shape):
        _screen.shape(shape)

    def text(self, text, x, y):
        _screen.text(str(text), int(x), int(y))

    def measure_text(self, text):
        try:
            r = _screen.measure_text(str(text))
            if isinstance(r, tuple) and len(r) == 2:
                return r
            if isinstance(r, int):
                return (r, 8)
            return (len(str(text)) * 6, 8)
        except Exception:
            return (len(str(text)) * 6, 8)

    def window(self, x, y, w, h):
        return _screen.window(int(x), int(y), int(w), int(h))


screen = _ScreenAdapter()


# ── io adapter — over _input module ───────────────────────────────

class _IOAdapter:
    BUTTON_A = BUTTON_A
    BUTTON_B = BUTTON_B
    BUTTON_C = BUTTON_C
    BUTTON_UP = BUTTON_UP
    BUTTON_DOWN = BUTTON_DOWN
    BUTTON_HOME = BUTTON_HOME

    @property
    def pressed(self):
        try:
            p = _input.pressed
            return p if isinstance(p, set) else set(p)
        except Exception:
            return set()

    @property
    def held(self):
        try:
            h = _input.held
            return h if isinstance(h, set) else set(h)
        except Exception:
            return set()

    @property
    def released(self):
        try:
            r = _input.released
            return r if isinstance(r, set) else set(r)
        except Exception:
            return set()

    @property
    def changed(self):
        try:
            c = _input.changed
            return c if isinstance(c, set) else set(c)
        except Exception:
            return set()

    def poll(self):
        try:
            _input.poll()
        except Exception:
            pass


io = _IOAdapter()


# ── Battery / charging — direct ADC reads ─────────────────────────

try:
    _vbat_adc = machine.ADC(machine.Pin.board.VBAT_SENSE)
except Exception:
    _vbat_adc = None

try:
    _sense_1v1_adc = machine.ADC(machine.Pin.board.SENSE_1V1)
except Exception:
    _sense_1v1_adc = None

try:
    _vbus_pin = machine.Pin.board.VBUS_DETECT
except Exception:
    _vbus_pin = None

try:
    _charge_pin = machine.Pin.board.CHARGE_STAT
except Exception:
    _charge_pin = None

_BAT_MAX = 4.10
_BAT_MIN = 3.00
_CONV = 3.3 / 65536


def _battery_voltage():
    if _vbat_adc is None or _sense_1v1_adc is None:
        return _BAT_MAX
    samples = 5
    v_total = 0
    r_total = 0
    for _ in range(samples):
        v_total += _vbat_adc.read_u16()
        r_total += _sense_1v1_adc.read_u16()
    voltage = (v_total / samples) * _CONV * 2
    vref = (r_total / samples) * _CONV
    return voltage / vref * 1.1


def get_battery_level():
    try:
        v = _battery_voltage()
        # Pimoroni formula
        return min(100, max(0, round(123 - (123 / pow((1 + pow((v / 3.2), 80)), 0.165)))))
    except Exception:
        return 100


def is_charging():
    if _vbus_pin is None or _charge_pin is None:
        return False
    try:
        if _vbus_pin.value():
            return not _charge_pin.value()
        return False
    except Exception:
        return False


def get_light():
    try:
        adc = machine.ADC(machine.Pin("LIGHT_SENSE"))
        return adc.read_u16()
    except Exception:
        return 0


# ── Backlight ────────────────────────────────────────────────────

def update_backlight():
    try:
        avg = sum(backlight_smoothing) / len(backlight_smoothing)
        _display.backlight(max(0.0, min(1.0, avg)))
    except Exception:
        pass


def set_brightness(level):
    try:
        _display.backlight(max(0.0, min(1.0, float(level))))
    except Exception:
        pass


# ── run(update) main loop ────────────────────────────────────────

def run(update_func, fps=30):
    period_ms = 1000 // max(1, fps)
    while True:
        t0 = time.ticks_ms()
        try:
            _input.poll()
        except Exception:
            pass
        try:
            result = update_func()
        except Exception as e:
            print("[run] update raised:", repr(e))
            raise
        try:
            _display.update()
        except Exception:
            pass
        if result is not None:
            return result
        elapsed = time.ticks_diff(time.ticks_ms(), t0)
        if elapsed < period_ms:
            time.sleep_ms(period_ms - elapsed)


# ── Miscellany ────────────────────────────────────────────────────

def is_dir(path):
    import os as _os
    try:
        return (_os.stat(path)[0] & 0x4000) != 0
    except Exception:
        return False


def file_exists(path):
    import os as _os
    try:
        _os.stat(path)
        return True
    except Exception:
        return False


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


# ── Initialise display once ───────────────────────────────────────
# Stock Pimoroni's badge.mode(LORES | VSYNC) sets vsync; emulate.
try:
    _display.set_vsync(True)
except Exception:
    pass

# Set initial pen + clear so the first frame isn't garbage.
try:
    _screen.pen = picovector.color.black
    _screen.clear()
    _display.update()
except Exception:
    pass
