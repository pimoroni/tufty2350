import cppmem
import machine
import powman
from picographics import DISPLAY_EXPLORER, PicoGraphics


# We can rely on these having been set up by powman... maybe
BUTTON_DOWN = machine.Pin.board.BUTTON_DOWN
BUTTON_A = machine.Pin.board.BUTTON_A
BUTTON_B = machine.Pin.board.BUTTON_B
BUTTON_C = machine.Pin.board.BUTTON_C
BUTTON_UP = machine.Pin.board.BUTTON_UP
BUTTON_HOME = machine.Pin.board.BUTTON_HOME

SYSTEM_VERY_SLOW = 0
SYSTEM_SLOW = 1
SYSTEM_NORMAL = 2
SYSTEM_FAST = 3
SYSTEM_TURBO = 4

WIDTH = 320
HEIGHT = 240

SYSTEM_FREQS = [
    4000000,
    12000000,
    48000000,
    133000000,
    250000000
]

BUTTONS = {
    BUTTON_DOWN,
    BUTTON_A,
    BUTTON_B,
    BUTTON_C,
    BUTTON_UP,
    BUTTON_HOME
}

LIGHT_SENSOR = machine.ADC(machine.Pin("LIGHT_SENSE"))

cppmem.set_mode(cppmem.MICROPYTHON)


def is_wireless():
    return True


def woken_by_button():
    return powman.get_wake_reason() in (
        powman.WAKE_BUTTON_A,
        powman.WAKE_BUTTON_B,
        powman.WAKE_BUTTON_C,
        powman.WAKE_BUTTON_UP,
        powman.WAKE_BUTTON_DOWN)


def pressed_to_wake(button):
    # TODO: BUTTON_HOME cannot be a wake button
    # so maybe raise an exception
    return button in powman.get_wake_buttons()


def woken_by_reset():
    return powman.get_wake_reason() == 255


def system_speed(speed):
    try:
        machine.freq(SYSTEM_FREQS[speed])
    except IndexError:
        pass


class Tufty2350():
    def __init__(self):
        self.display = PicoGraphics(DISPLAY_EXPLORER, rotate=180)

    def __getattr__(self, item):
        # Glue to redirect calls to PicoGraphics
        return getattr(self.display, item)

    def update(self):
        self.display.update()

    def pressed(self, button):
        return button.value() == 0

    def pressed_any(self):
        return 0 in [button.value() for button in BUTTONS]

    def sleep(self):
        self.display.set_backlight(0)
        powman.sleep()

    def get_light(self):
        # TODO: Returning the raw u16 is a little meh here, can we do an approx lux conversion?
        return LIGHT_SENSOR.read_u16()
