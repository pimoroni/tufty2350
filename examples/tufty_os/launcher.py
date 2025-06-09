import gc
import math
import os
import time

import tufty2350
from picovector import (ANTIALIAS_BEST, HALIGN_CENTER, PicoVector, Polygon,
                        Transform)

import tufty_os

ICONS = {
    "badge": "\uea67",
    "book_2": "\uf53e",
    "cloud": "\ue2bd",
    "description": "\ue873",
    "help": "\ue887",
    "wifi": "\ue63e",
    "image": "\ue3f4",
    "info": "\ue88e",
    "format_list_bulleted": "\ue241",
    "joystick": "\uf5ee"
}

APP_DIR = "/examples"
FONT_SIZE = 1

changed = False
exited_to_launcher = False

state = {
    "selected_icon": "ebook",
    "running": "launcher"
}

tufty_os.state_load("launcher", state)

if state["running"] != "launcher" and not tufty2350.woken_by_reset():
    tufty_os.launch(state["running"])

# If we don't launch an example, reset the state.
tufty_os.state_clear_running()

display = tufty2350.Tufty2350()
display.set_font("bitmap8")
display.led(0)

# Colours
BACKGROUND = display.create_pen(24, 59, 78)
FOREGROUND = display.create_pen(245, 238, 220)
HIGHLIGHT = display.create_pen(221, 168, 83)

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

examples = [x[:-3] for x in os.listdir(APP_DIR) if x.endswith(".py")]

MAX_PER_ROW = 3
MAX_PER_PAGE = MAX_PER_ROW * 2
ICONS_TOTAL = len(examples)
MAX_PAGE = math.ceil(ICONS_TOTAL / MAX_PER_PAGE)

WIDTH = 320

# Page layout
centers = [[50, 65], [162, 65], [WIDTH - 50, 65], [50, 170], [162, 170], [WIDTH - 50, 170]]


def draw_disk_usage(x):
    _, f_used, _ = tufty_os.get_disk_usage()

    display.set_pen(15)

    # Replace with suitable vector icon
    """
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
    """
    display.rectangle(x + 10, 5, 45, 10)
    display.set_pen(0)
    display.rectangle(x + 11, 6, 43, 8)
    display.set_pen(15)
    display.rectangle(x + 12, 7, int(41 / 100.0 * f_used), 6)


def read_header(label):
    file = f"{APP_DIR}/{label}.py"

    name = label
    icon = ICONS["description"]

    with open(file) as f:
        header = [f.readline().strip() for _ in range(3)]

    for line in header:
        if line.startswith("# ICON "):
            icon = line[7:].strip()
            icon = ICONS[icon]

        if line.startswith("# NAME "):
            name = line[7:]

    return name, icon


def render(selected_index):
    global icons_total
    global selected_file

    display.set_pen(BACKGROUND)
    display.clear()

    selected_page = selected_index // MAX_PER_PAGE

    icons = examples[selected_page * 6:selected_page * 6 + MAX_PER_PAGE]

    for index, label in enumerate(icons):
        x, y = centers[index]

        name, icon = read_header(label)

        display.set_pen(FOREGROUND)
        vector.set_font_size(28)
        vector.set_transform(t)
        vector.text(icon, x, y)
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
        w = vector.measure_text(name)[2]
        vector.text(name, int(x - (w / 2)), y + 45)

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

    # draw_disk_usage(100)

    display.set_pen(FOREGROUND)
    vector.set_font_size(14)
    vector.text("TuftyOS", 7, 14)

    display.update()


def wait_for_user_to_release_buttons():
    while display.pressed_any():
        time.sleep(0.01)


def launch_example(file):
    wait_for_user_to_release_buttons()

    file = f"{APP_DIR}/{file}"

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


try:
    selected_index = examples.index(state["selected_file"])
except (ValueError, KeyError):
    selected_index = 0

    print(state["selected_file"])

while True:

    if display.pressed(tufty2350.BUTTON_A):
        if (selected_index % MAX_PER_ROW) > 0:
            selected_index -= 1
            changed = True

    if display.pressed(tufty2350.BUTTON_B):
        launch_example(state["selected_file"])

    if display.pressed(tufty2350.BUTTON_C):
        if (selected_index % MAX_PER_ROW) < MAX_PER_ROW - 1:
            selected_index += 1
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
        state["selected_file"] = examples[selected_index]
        tufty_os.state_save("launcher", state)
        changed = False
        wait_for_user_to_release_buttons()

    render(selected_index)
