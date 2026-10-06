import os
import sys

sys.path.insert(0, "/system/apps/menu/themes")
sys.path.insert(0, "/system/apps/menu")
sys.path.insert(0, "/")
os.chdir("/system/apps/menu")

from app import Apps


def load_theme(name):
    try:
        return __import__(name)
    except Exception as e:  # noqa: BLE001
        print(f"- theme '{name}' failed: {e}")
        return __import__("default")


settings = {"theme": "default"}
State.load("theme", settings)
theme = load_theme(settings["theme"])


# find installed apps and create apps
apps = Apps("/system/apps")

active = 0

MAX_ALPHA = 255
alpha = 30


# default 3x2 grid navigation, used when a theme has no navigate()
def grid_navigate(active, count):
    if badge.pressed(BUTTON_C):
        if (active % 3) < 2 and active < count - 1:
            active += 1
    if badge.pressed(BUTTON_A):
        if (active % 3) > 0 and active > 0:
            active -= 1
    if badge.pressed(BUTTON_UP) and active >= 3:
        active -= 3
    if badge.pressed(BUTTON_DOWN):
        active += 3
        if active >= count:
            active = count - 1
    return active


def update():
    global active, apps, alpha, theme

    # a broken theme must never lock the user out of the launcher
    try:
        active = getattr(theme, "navigate", grid_navigate)(active, len(apps))
        active = max(0, min(active, len(apps) - 1))
        apps.activate(active)

        if badge.pressed(BUTTON_B):
            return apps.active.path

        theme.render(apps)
    except Exception as e:  # noqa: BLE001
        print(f"- theme error: {e}")
        theme = __import__("default")
        return None

    if alpha <= MAX_ALPHA:
        screen.pen = color.rgb(0, 0, 0, 255 - alpha)
        screen.rectangle(screen.clip)
        alpha += 30

    return None

# "on_exit" will be called if callable, else returned verbatim by `launch`
on_exit = run(update).result
