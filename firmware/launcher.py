import gc
import math
import os
import time

import tufty2350
from picovector import (ANTIALIAS_BEST, HALIGN_CENTER, PicoVector, Polygon,
                        Transform)

import tufty_os

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
        self.path = f"{name}/__main__"
        self._loaded = False

    def read_metadata(self):
        if self._loaded:
            return

        try:
            exec(open(f"{App.DIRECTORY}/{self._file}/__init__.py", "r").read(), self._meta)
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
            open(f"{App.DIRECTORY}/{file}/__init__.py", "r")
            return True
        except OSError:
            return False


FONT_SIZE = 1

changed = True
exited_to_launcher = False

state = {
    "selected_icon": "ebook",
    "running": "launcher",
    "selected_file": 0,
    "page": 0,
    "colours": [(24, 59, 78), (245, 238, 220), (255, 135, 0)]
}

tufty_os.state_load("launcher", state)

if state["running"] != "launcher":
    tufty_os.launch(state["running"])

display = tufty2350.Tufty2350()
display.set_font("bitmap8")
display.set_backlight(0)

apps = [App(x) for x in os.listdir(App.DIRECTORY) if App.is_valid(x)]

# Colours
BACKGROUND = display.create_pen(*state["colours"][0])
FOREGROUND = display.create_pen(*state["colours"][1])
HIGHLIGHT = display.create_pen(*state["colours"][2])

# Pico Vector
vector = PicoVector(display.display)
vector.set_antialiasing(ANTIALIAS_BEST)
t = Transform()
vector.set_font("Roboto-Medium-With-Material-Symbols.af", 20)
vector.set_font_align(HALIGN_CENTER)
vector.set_transform(t)

TITLE_BAR = Polygon()
TITLE_BAR.rectangle(2, 2, 316, 16, (8, 8, 8, 8))
TITLE_BAR.circle(308, 10, 4)

SELECTED_BORDER = Polygon()
SELECTED_BORDER.rectangle(0, 0, 90, 90, (10, 10, 10, 10), 5)

MAX_PER_ROW = 3
MAX_PER_PAGE = MAX_PER_ROW * 2
ICONS_TOTAL = len(apps)
MAX_PAGE = math.ceil(ICONS_TOTAL / MAX_PER_PAGE)

WIDTH = 320

# Page layout
centers = [[50, 65], [162, 65], [WIDTH - 50, 65], [50, 170], [162, 170], [WIDTH - 50, 170]]


def draw_disk_usage(x):
    _, f_used, _ = tufty_os.get_disk_usage()

    display.set_pen(FOREGROUND)

    display.image(
        bytearray(
            (
                0b00000000,
                0b00111100,
                0b00111100,
                0b00111100,
                0b00111000,
                0b00000000,
                0b00000000,
                0b00000001,
            )
        ),
        8,
        8,
        x,
        6,
    )

    display.rectangle(x + 10, 5, 45, 10)
    display.set_pen(BACKGROUND)
    display.rectangle(x + 11, 6, 43, 8)
    display.set_pen(HIGHLIGHT)
    display.rectangle(x + 12, 7, int(41 / 100.0 * f_used), 6)


def render(selected_index):
    global icons_total
    global selected_file

    display.set_pen(BACKGROUND)
    display.clear()

    selected_page = selected_index // MAX_PER_PAGE

    icons = apps[selected_page * 6:selected_page * 6 + MAX_PER_PAGE]

    for index, app in enumerate(icons):
        x, y = centers[index]

        app.read_metadata()

        display.set_pen(FOREGROUND)
        vector.set_font_size(28)
        vector.set_transform(t)
        vector.text(app.icon, x, y)
        t.translate(x, y)
        t.scale(1.0, 1.0)

        if selected_index % MAX_PER_PAGE == index:
            display.set_pen(HIGHLIGHT)
            t.translate(-45, -36)
            t.scale(1.0, 1.0)
            vector.draw(SELECTED_BORDER)
        t.reset()

        display.set_pen(FOREGROUND)
        vector.set_font_size(18)
        w = vector.measure_text(app.name)[2]
        vector.text(app.name, int(x - (w / 2)), y + 45)

    for i in range(MAX_PAGE):
        x = 310
        y = int((240 / 2) - (MAX_PAGE * 10 / 2) + (i * 10))
        display.set_pen(HIGHLIGHT)
        display.rectangle(x, y, 8, 8)
        if state["page"] != i:
            display.set_pen(FOREGROUND)
            display.rectangle(x + 1, y + 1, 6, 6)

    display.set_pen(HIGHLIGHT)
    vector.draw(TITLE_BAR)

    draw_disk_usage(130)

    display.set_pen(FOREGROUND)
    vector.set_font_size(14)
    vector.text("TuftyOS", 7, 14)

    display.update()
    gc.collect()


def wait_for_user_to_release_buttons():
    while display.pressed_any():
        time.sleep(0.01)


def launch_example(file):
    wait_for_user_to_release_buttons()

    file = f"{App.DIRECTORY}/{file}"

    for k in locals().keys():
        if k not in ("gc", "file", "tufty_os"):
            del locals()[k]

    gc.collect()

    tufty_os.launch(file)


def button(pin):
    global changed
    global selected_file
    global icons_total
    changed = True

    if pin == tufty2350.BUTTON_A:
        if (selected_file % MAX_PER_ROW) > 0:
            selected_file -= 1

    if pin == tufty2350.BUTTON_B:
        launch_example((state["page"] * MAX_PER_PAGE) + selected_file)

    if pin == tufty2350.BUTTON_C:
        if (selected_file % MAX_PER_ROW) < MAX_PER_ROW - 1:
            selected_file += 1

    if pin == tufty2350.BUTTON_UP:
        if selected_file >= MAX_PER_ROW:
            selected_file -= MAX_PER_ROW
        else:
            state["page"] = (state["page"] - 1) % MAX_PAGE
            selected_file += MAX_PER_ROW

    if pin == tufty2350.BUTTON_DOWN:
        if selected_file < MAX_PER_ROW and icons_total > MAX_PER_ROW:
            selected_file += MAX_PER_ROW
        elif selected_file >= MAX_PER_ROW or icons_total < MAX_PER_ROW + 1:
            state["page"] = (state["page"] + 1) % MAX_PAGE
            selected_file %= MAX_PER_ROW


def app_index(file):
    index = 0
    for app in apps:
        if app.path == file:
            return index
        index += 1
    return 0


selected_index = app_index(state["selected_file"])

i = 0

while True:
    if i < 15:
        i += 1
        display.set_backlight(i / 15)
        time.sleep(1.0 / 60)

    if display.pressed(tufty2350.BUTTON_A):
        if (selected_index % MAX_PER_ROW) > 0:
            selected_index -= 1
            changed = True

    if display.pressed(tufty2350.BUTTON_B):
        launch_example(state["selected_file"])

    if display.pressed(tufty2350.BUTTON_C):
        if (selected_index % MAX_PER_ROW) < MAX_PER_ROW - 1:
            selected_index += 1
            selected_index = min(selected_index, ICONS_TOTAL - 1)
            changed = True

    if display.pressed(tufty2350.BUTTON_UP):
        if selected_index >= MAX_PER_ROW:
            selected_index -= MAX_PER_ROW
            changed = True

    if display.pressed(tufty2350.BUTTON_DOWN):
        if selected_index < ICONS_TOTAL - 1:
            selected_index += MAX_PER_ROW
            selected_index = min(selected_index, ICONS_TOTAL - 1)
            changed = True

    if changed:
        state["selected_file"] = apps[selected_index].path
        tufty_os.state_save("launcher", state)
        changed = False
        wait_for_user_to_release_buttons()

        render(selected_index)
