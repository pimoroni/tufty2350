import os
import sys

sys.path.insert(0, "/system/apps/menu")
sys.path.insert(0, "/")
os.chdir("/system/apps/menu")

import ui

from app import Apps
import qwstpad

title_font = rom_font.ark
label_font = rom_font.sins
gamepad = None
controls = {}

# find installed apps and create apps
apps = Apps("/system/apps")

active = 0

MAX_ALPHA = 255
alpha = 30


def init_gamepad():
    global gamepad
    gamepads = qwstpad.Gamepadhelper()
    for i in gamepads.pads:
        if i is not None:
            gamepad = i
            return i
    return None

def parse_controls():
    global controls, gamepad

    if not gamepad:
        gamepad = init_gamepad()

    if gamepad:
        try:
            gamepad.update_buttons()
        except OSError:
            gamepad = init_gamepad()

    if gamepad:
        controls["MOVE_LEFT"] = badge.pressed(BUTTON_A) or gamepad.pressed("L")
        controls["MOVE_RIGHT"] = badge.pressed(BUTTON_C) or gamepad.pressed("R")
        controls["MOVE_DOWN"] = badge.pressed(BUTTON_DOWN) or gamepad.pressed("D")
        controls["MOVE_UP"] = badge.pressed(BUTTON_UP) or gamepad.pressed("U")
        controls["SELECT"] = badge.pressed(BUTTON_B) or gamepad.pressed("B")
    else:
        controls["MOVE_LEFT"] = badge.pressed(BUTTON_A)
        controls["MOVE_RIGHT"] = badge.pressed(BUTTON_C)
        controls["MOVE_DOWN"] = badge.pressed(BUTTON_DOWN)
        controls["MOVE_UP"] = badge.pressed(BUTTON_UP)
        controls["SELECT"] = badge.pressed(BUTTON_B)


def update():
    global active, apps, alpha

    parse_controls()

    # process button inputs to switch between apps
    if controls["MOVE_RIGHT"]:
        if (active % 3) < 2 and active < len(apps) - 1:
            active += 1
    if controls["MOVE_LEFT"]:
        if (active % 3) > 0 and active > 0:
            active -= 1
    if controls["MOVE_UP"] and active >= 3:
        active -= 3
    if controls["MOVE_DOWN"]:
        active += 3
        if active >= len(apps):
            active = len(apps) - 1

    apps.activate(active)

    if controls["SELECT"]:
        return f"/system/apps/{apps.active.path}"

    ui.draw_background()

    screen.font = title_font
    ui.draw_header()

    # draw menu apps
    apps.draw_icons()

    # draw label for active menu icon
    screen.font = label_font
    apps.draw_label()

    # draw hints for the active page
    apps.draw_pagination()

    if alpha <= MAX_ALPHA:
        screen.pen = color.rgb(0, 0, 0, 255 - alpha)
        screen.clear()
        alpha += 30

    return None

# "on_exit" will be called if callable, else returned verbatim by `launch`
on_exit = run(update).result
