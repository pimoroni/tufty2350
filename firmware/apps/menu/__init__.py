import os
import sys

sys.path.insert(0, "/system/apps/menu")
sys.path.insert(0, "/")
os.chdir("/system/apps/menu")

import ui
from badgeware import run

from app import Apps

screen.font = pixel_font.load("/system/assets/fonts/ark.ppf")


# find installed apps and create apps
apps = Apps("/system/apps")

active = 0

MAX_ALPHA = 255
alpha = 30

io.poll()

def update():
    global active, apps, alpha

    # process button inputs to switch between apps
    if io.BUTTON_C in io.pressed:
        if (active % 3) < 2 and active < len(apps) - 1:
            active += 1
    if io.BUTTON_A in io.pressed:
        if (active % 3) > 0 and active > 0:
            active -= 1
    if io.BUTTON_UP in io.pressed and active >= 3:
        active -= 3
    if io.BUTTON_DOWN in io.pressed:
        active += 3
        if active >= len(apps):
            active = len(apps) - 1

    apps.activate(active)

    if io.BUTTON_B in io.pressed:
        return f"/system/apps/{apps.active.path}"

    ui.draw_background()
    ui.draw_header()

    # draw menu apps
    apps.draw_icons()

    # draw label for active menu icon
    apps.draw_label()

    # draw hints for the active page
    apps.draw_pagination()

    if alpha <= MAX_ALPHA:
        screen.pen = color.rgb(0, 0, 0, 255 - alpha)
        screen.clear()
        alpha += 30

    return None


if __name__ == "__main__":
    run(update)
