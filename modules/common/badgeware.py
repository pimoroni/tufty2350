import gc
import json
import os
import time

import cppmem
import machine
import micropython
import powman
from picovector import ANTIALIAS_BEST, PicoVector, Polygon, Transform, HALIGN_CENTER   # noqa F401

board = os.uname().machine.split(" ")[1]

if board == "Tufty":

    from picographics import DISPLAY_EXPLORER, PicoGraphics
    display = PicoGraphics(DISPLAY_EXPLORER, rotate=180)

    LIGHT_SENSOR = machine.ADC(machine.Pin("LIGHT_SENSE"))

    def get_light():
        # TODO: Returning the raw u16 is a little meh here, can we do an approx lux conversion?
        return LIGHT_SENSOR.read_u16()

elif board == "Badger":
    pass
elif board == "Blinky":
    pass

WIDTH, HEIGHT = display.get_bounds()

# Pico Vector
vector = PicoVector(display)
vector.set_antialiasing(ANTIALIAS_BEST)

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
    BUTTON_UP
}


cppmem.set_mode(cppmem.MICROPYTHON)

exit_to_launcher = False


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


def pressed_any():
    return 0 in [button.value() for button in BUTTONS]


def update():
    display.update()


def pressed(button):
    return button.value() == 0


@micropython.native
def icon(data, index, data_w, icon_size, x, y):
    s_x = (index * icon_size) % data_w
    s_y = int((index * icon_size) / data_w)

    for o_y in range(icon_size):
        for o_x in range(icon_size):
            o = ((o_y + s_y) * data_w) + (o_x + s_x)
            bm = 0b10000000 >> (o & 0b111)
            if data[o >> 3] & bm:
                display.pixel(x + o_x, y + o_y)


def image(data, w, h, x, y):
    for oy in range(h):
        row = data[oy]
        for ox in range(w):
            if row & 0b1 == 0:
                display.pixel(x + ox, y + oy)
            row >>= 1


def sleep():
    display.set_backlight(0)
    powman.sleep()


class App:
    ICONS = {
        "badge": "\uea67",
        "book_2": "\uf53e",
        "check_box": "\ue834",
        "cloud": "\ue2bd",
        "deployed-code": "\uf720",
        "description": "\ue873",
        "help": "\ue887",
        "water_full": "\uf6d6",
        "wifi": "\ue63e",
        "image": "\ue3f4",
        "info": "\ue88e",
        "format_list_bulleted": "\ue241",
        "joystick": "\uf5ee"
    }
    DIRECTORY = "apps"
    DEFAULT_ICON = "description"
    ERROR_ICON = "help"  # TODO: have a reserved error icon

    def __init__(self, name):
        self._file = name
        self._meta = {
            "NAME": name,
            "ICON": App.DEFAULT_ICON,
            "DESC": ""
        }
        self.path = f"{name}/__init__"
        self._loaded = False

    def read_metadata(self):
        if self._loaded:
            return

        try:
            exec(open(f"{App.DIRECTORY}/{self._file}/metadata.py", "r").read(), self._meta)
        except SyntaxError:
            self._meta["ICON"] = App.ERROR_ICON
        self._loaded = True

    @property
    def name(self):
        self.read_metadata()
        return self._meta["NAME"]

    @property
    def icon(self):
        self.read_metadata()
        try:
            return App.ICONS[self._meta["ICON"]]
        except KeyError:
            return App.ICONS[App.ERROR_ICON]

    @property
    def desc(self):
        self.read_metadata()
        return self._meta["DESC"]

    @staticmethod
    def is_valid(file):
        try:
            open(f"{App.DIRECTORY}/{file}/metadata.py", "r")
            return True
        except OSError:
            return False


# List the apps available on device
apps = [App(x) for x in os.listdir(App.DIRECTORY) if App.is_valid(x)]


def wait_for_user_to_release_buttons():
    while pressed_any():
        time.sleep(0.01)


def get_battery_level():
    """
    # Battery measurement
    vbat_adc = machine.ADC(PIN_BATTERY)
    vref_adc = machine.ADC(PIN_1V2_REF)
    vref_en = machine.Pin(PIN_VREF_POWER)
    vref_en.init(machine.Pin.OUT)
    vref_en.value(0)

    # Enable the onboard voltage reference
    vref_en.value(1)

    # Calculate the logic supply voltage, as will be lower that the usual 3.3V when running off low batteries
    vdd = 1.24 * (65535 / vref_adc.read_u16())
    vbat = (
        (vbat_adc.read_u16() / 65535) * 3 * vdd
    )  # 3 in this is a gain, not rounding of 3.3V

    # Disable the onboard voltage reference
    vref_en.value(0)

    # Convert the voltage to a level to display onscreen
    return vbat
    """


def get_disk_usage():
    # f_bfree and f_bavail should be the same?
    # f_files, f_ffree, f_favail and f_flag are unsupported.
    f_bsize, f_frsize, f_blocks, f_bfree, _, _, _, _, _, f_namemax = os.statvfs("/")

    f_total_size = f_frsize * f_blocks
    f_total_free = f_bsize * f_bfree
    f_total_used = f_total_size - f_total_free

    f_used = 100 / f_total_size * f_total_used
    f_free = 100 / f_total_size * f_total_free

    return f_total_size, f_used, f_free


def state_running():
    state = {"running": "launcher"}
    state_load("launcher", state)
    return state["running"]


def state_clear_running():
    running = state_running()
    state_modify("launcher", {"running": "launcher"})
    return running != "launcher"


def state_set_running(app):
    state_modify("launcher", {"running": app})


def state_launch():
    app = state_running()
    if app is not None and app != "launcher":
        launch(app)


def state_delete(app):
    try:
        os.remove("/state/{}.json".format(app))
    except OSError:
        pass


def state_save(app, data):
    try:
        with open("/state/{}.json".format(app), "w") as f:
            f.write(json.dumps(data))
            f.flush()
    except OSError:
        import os
        try:
            os.stat("/state")
        except OSError:
            os.mkdir("/state")
            state_save(app, data)


def state_modify(app, data):
    state = {}
    state_load(app, state)
    state.update(data)
    state_save(app, state)


def state_load(app, defaults):
    try:
        data = json.loads(open("/state/{}.json".format(app), "r").read())
        if type(data) is dict:
            defaults.update(data)
            return True
    except (OSError, ValueError):
        pass

    state_save(app, defaults)
    return False


def launch(file):
    global exit_to_launcher

    exit_to_launcher = False

    wait_for_user_to_release_buttons()

    app_path = f"{App.DIRECTORY}/{file}"

    """
    for k in locals().keys():
        if k not in ("gc", "file", "badgeware_os"):
            del locals()[k]
    """
    gc.collect()

    state_set_running(file)

    gc.collect()

    def quit_to_launcher(_pin):
        global exit_to_launcher
        state_clear_running()
        os.sync()
        while BUTTON_HOME.value() == 0:
            pass
        exit_to_launcher = True

    BUTTON_HOME.irq(trigger=machine.Pin.IRQ_FALLING, handler=quit_to_launcher)

    try:
        app = __import__(app_path)
        app.init()

        while not exit_to_launcher:
            app.update()
            app.render()

    except ImportError as e:
        print(e)
        # If the app doesn't exist, notify the user
        warning(None, f"Could not launch: {file}")
        time.sleep(4.0)
    except Exception as e:  # noqa: BLE001 (We really do want to catch *all* exceptions!)
        # If the app throws an error, catch it and display!
        print(e)
        warning(None, str(e))
        time.sleep(4.0)

    # If the app exits or errors, do not relaunch!
    state_clear_running()
    exit_to_launcher = True


# Draw an overlay box with a given message within it
def warning(display, message, width=WIDTH - 20, height=HEIGHT - 20, line_spacing=20, text_size=0.6):
    print(message)
    """
    if display is None:
        display = Tufty2350()
        # display.led(128)
    """

    # Draw a light grey background
    display.set_pen(12)
    display.rectangle((WIDTH - width) // 2, (HEIGHT - height) // 2, width, height)

    width -= 20
    height -= 20

    display.set_pen(15)
    display.rectangle((WIDTH - width) // 2, (HEIGHT - height) // 2, width, height)

    # Take the provided message and split it up into
    # lines that fit within the specified width
    words = message.split(" ")

    lines = []
    current_line = ""
    for word in words:
        if display.measure_text(current_line + word + " ", text_size) < width:
            current_line += word + " "
        else:
            lines.append(current_line.strip())
            current_line = word + " "
    lines.append(current_line.strip())

    display.set_pen(0)

    # Display each line of text from the message, centre-aligned
    num_lines = len(lines)
    for i in range(num_lines):
        length = display.measure_text(lines[i], text_size)
        current_line = (i * line_spacing) - ((num_lines - 1) * line_spacing) // 2
        display.text(lines[i], (WIDTH - length) // 2, (HEIGHT // 2) + current_line, WIDTH, text_size)

    display.update()
