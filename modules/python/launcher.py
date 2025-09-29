import gc
import math
import time

import badgeware

FONT_SIZE = 1

changed = True

state = {
    "selected_icon": "ebook",
    "running": "launcher",
    "selected_file": 0,
    "page": 0,
    "colours": [(24, 59, 78), (245, 238, 220), (255, 135, 0)]
}

display = badgeware.display
display.set_font("bitmap8")
display.set_backlight(1.0)
WIDTH, HEIGHT = badgeware.WIDTH, badgeware.HEIGHT

# Pico Vector
vector = badgeware.vector
vector.set_font("Roboto-Medium-With-Material-Symbols.af", 20)
vector.set_font_align(badgeware.HALIGN_CENTER)
t = badgeware.Transform()

badgeware.state_load("launcher", state)

if state["running"] != "launcher":
    badgeware.launch(state["running"])

apps = badgeware.apps

# Colours
BACKGROUND = display.create_pen(*state["colours"][0])
FOREGROUND = display.create_pen(*state["colours"][1])
HIGHLIGHT = display.create_pen(*state["colours"][2])
RED = display.create_pen(255, 0, 0)
YELLOW = display.create_pen(255, 255, 0)

TITLE_BAR = badgeware.Polygon()
TITLE_BAR.rectangle(2, 2, 316, 16, (8, 8, 8, 8))
TITLE_BAR.circle(308, 10, 4)

SELECTED_BORDER = badgeware.Polygon()
SELECTED_BORDER.rectangle(0, 0, 90, 90, (10, 10, 10, 10), 5)

MAX_PER_ROW = 3
MAX_PER_PAGE = MAX_PER_ROW * 2
ICONS_TOTAL = len(apps)
MAX_PAGE = math.ceil(ICONS_TOTAL / MAX_PER_PAGE)

# Page layout
centers = [[50, 65], [162, 65], [WIDTH - 50, 65], [50, 170], [162, 170], [WIDTH - 50, 170]]


def draw_disk_usage(x):
    _, f_used, _ = badgeware.get_disk_usage()

    display.set_pen(FOREGROUND)

    badgeware.image(
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


def draw_battery_remaining(x):

    percentage = badgeware.get_battery_level()

    if badgeware.is_charging():
        display.set_pen(YELLOW)
    elif percentage <= 10:
        display.set_pen(RED)
    else:
        display.set_pen(FOREGROUND)

    display.rectangle(x + 10, 5, 20, 10)
    display.rectangle(x + 30, 8, 2, 4)
    display.set_pen(BACKGROUND)
    display.rectangle(x + 11, 6, 18, 8)
    display.set_pen(HIGHLIGHT)
    display.rectangle(x + 12, 7, int(16 / 100 * percentage), 6)


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
    draw_battery_remaining(265)

    display.set_pen(FOREGROUND)
    vector.set_font_size(14)
    vector.text("TuftyOS", 7, 14)

    display.update()
    gc.collect()


def button(pin):
    global changed
    global selected_file
    global icons_total
    changed = True

    if pin == badgeware.BUTTON_A:
        if (selected_file % MAX_PER_ROW) > 0:
            selected_file -= 1

    if pin == badgeware.BUTTON_B:
        badgeware.launch((state["page"] * MAX_PER_PAGE) + selected_file)

    if pin == badgeware.BUTTON_C:
        if (selected_file % MAX_PER_ROW) < MAX_PER_ROW - 1:
            selected_file += 1

    if pin == badgeware.BUTTON_UP:
        if selected_file >= MAX_PER_ROW:
            selected_file -= MAX_PER_ROW
        else:
            state["page"] = (state["page"] - 1) % MAX_PAGE
            selected_file += MAX_PER_ROW

    if pin == badgeware.BUTTON_DOWN:
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

changed = True

while True:

    if i < 15:
        i += 1
        display.set_backlight(i / 15)
        time.sleep(1.0 / 60)

    if badgeware.pressed(badgeware.BUTTON_A):
        if (selected_index % MAX_PER_ROW) > 0:
            selected_index -= 1
            changed = True

    if badgeware.pressed(badgeware.BUTTON_B):
        badgeware.launch(state["selected_file"])
        changed = True

    if badgeware.pressed(badgeware.BUTTON_C):
        if (selected_index % MAX_PER_ROW) < MAX_PER_ROW - 1:
            selected_index += 1
            selected_index = min(selected_index, ICONS_TOTAL - 1)
            changed = True

    if badgeware.pressed(badgeware.BUTTON_UP):
        if selected_index >= MAX_PER_ROW:
            selected_index -= MAX_PER_ROW
            changed = True

    if badgeware.pressed(badgeware.BUTTON_DOWN):
        if selected_index < ICONS_TOTAL - 1:
            selected_index += MAX_PER_ROW
            selected_index = min(selected_index, ICONS_TOTAL - 1)
            changed = True

    state["selected_file"] = apps[selected_index].path

    if changed:
        badgeware.state_save("launcher", state)
        changed = False
        badgeware.wait_for_user_to_release_buttons()

    render(selected_index)
