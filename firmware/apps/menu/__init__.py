import os
import sys

sys.path.insert(0, "/system/apps/menu")
sys.path.insert(0, "/")
os.chdir("/system/apps/menu")

# The mode has to be set before ui is imported, since that builds its gradients
# and wordmark geometry against the full resolution screen.
badge.mode(HIRES | VSYNC)
screen.antialias = image.X2

import ui

from app import Apps

# Aeonik is the Arm brand typeface, so the lockup and labels are set in it
brand_font = font.load("assets/AeonikFono-Regular.af")


# find installed apps and create apps
apps = Apps("/system/apps")

active = 0

MAX_ALPHA = 255
alpha = 30


def update():
    global active, apps, alpha

    # step through the carousel one card at a time
    if badge.pressed(BUTTON_C) or badge.pressed(BUTTON_DOWN):
        active = min(len(apps) - 1, active + 1)
    if badge.pressed(BUTTON_A) or badge.pressed(BUTTON_UP):
        active = max(0, active - 1)

    apps.activate(active)

    if badge.pressed(BUTTON_B):
        return apps.active.path

    screen.font = brand_font

    ui.draw_background()
    ui.draw_header()

    # draw the app cards and how far through them we are
    apps.draw_cards()
    apps.draw_progress()

    if alpha <= MAX_ALPHA:
        screen.pen = color.rgb(0, 0, 0, 255 - alpha)
        screen.rectangle(screen.clip)
        alpha += 30

    return None

# "on_exit" will be called if callable, else returned verbatim by `launch`
on_exit = run(update).result

# Hand back the default mode so apps that don't set one still get the low
# resolution screen they expect.
badge.mode(LORES | VSYNC)
