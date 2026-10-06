import gc
import math
import os
import sys

THEMES_DIR = "/system/apps/menu/themes"

sys.path.insert(0, THEMES_DIR)
sys.path.insert(0, "/system/apps/menu")
os.chdir("/system/apps/themes")

from app import Apps

# theme names from .py/.mpy files, skipping dotfiles and asset folders
names = sorted({
    f.rsplit(".", 1)[0] for f in os.listdir(THEMES_DIR)
    if f.endswith((".py", ".mpy")) and not f.startswith(("_", "."))
})

settings = {"theme": "default"}
State.load("theme", settings)

index = names.index(settings["theme"]) if settings["theme"] in names else 0

# preview data for the theme's render()
apps = Apps("/system/apps")
apps.activate(0)

# copy of the theme's full-screen frame, scaled into the panel
preview = image(160, 120)
PX, PW, PH = 66, 88, 66
PY = (120 - PH) // 2
ROWS = 7
ROW_H = 13
TOP = 18
CYCLE = 1500

background = color.rgb(16, 20, 32)
header = color.rgb(40, 50, 80)
highlight = color.rgb(80, 120, 220)
text = color.rgb(220, 230, 255)
dim = color.rgb(120, 130, 160)

theme = None
theme_name = None
error = None
cycled = 0


def select(name):
    global theme, theme_name, error

    # unload the previous theme so only one is in memory
    if theme_name in sys.modules:
        del sys.modules[theme_name]
    theme = None
    gc.collect()

    theme_name = name
    error = None
    try:
        theme = __import__(name)
    except Exception as e:  # noqa: BLE001
        error = str(e)


def title(name):
    return name[0].upper() + name[1:]


def draw_list():
    screen.font = font.sins
    first = max(0, min(index - ROWS // 2, len(names) - ROWS))
    for i in range(first, min(first + ROWS, len(names))):
        y = TOP + (i - first) * ROW_H
        if i == index:
            screen.pen = highlight
            screen.shape(shape.rounded_rectangle(3, y, 58, ROW_H - 1, 4))
        screen.pen = text if i == index else dim
        screen.text(title(names[i]), 7, y + 1)
        if names[i] == settings["theme"]:
            screen.pen = text if i == index else highlight
            screen.rectangle(56, y + 5, 2, 2)


# render the theme full screen as normal, then keep a copy of the frame
def capture():
    global error

    if error is not None:
        return
    try:
        theme.render(apps)
        screen.alpha = 255
        preview.blit(screen, vec2(0, 0))
    except Exception as e:  # noqa: BLE001
        error = str(e)


def draw_preview():
    # shadow and pulsing outline, as on the gallery thumbnails
    screen.pen = color.rgb(0, 0, 0, 50)
    screen.shape(shape.rectangle(PX + 2, PY + 2, PW, PH))
    brightness = (math.sin(badge.ticks / 200) * 127) + 127
    screen.pen = color.rgb(brightness, brightness, brightness, 150)
    screen.shape(shape.rectangle(PX - 1, PY - 1, PW + 2, PH + 2))

    if error is None:
        screen.blit(preview, rect(0, 0, 160, 120), rect(PX, PY, PW, PH), image.BILINEAR)
    else:
        screen.pen = color.black
        screen.rectangle(PX, PY, PW, PH)
        screen.font = font.sins
        screen.pen = color.rgb(255, 100, 100)
        screen.text(error, rect(PX + 3, PY + 3, PW - 6, PH - 6))

    screen.font = font.sins
    label = "In use" if theme_name == settings["theme"] else "B: use"
    w, _ = screen.measure_text(label)
    screen.pen = dim
    screen.text(label, PX + PW / 2 - w / 2, PY + PH + 6)


def update():
    global index, cycled

    if badge.pressed(BUTTON_DOWN):
        index = (index + 1) % len(names)
    if badge.pressed(BUTTON_UP):
        index = (index - 1) % len(names)

    if names[index] != theme_name:
        select(names[index])

    if badge.pressed(BUTTON_B) and error is None:
        settings["theme"] = theme_name
        State.save("theme", settings)

    # step through the apps so the preview shows the layout moving
    if badge.ticks - cycled > CYCLE:
        cycled = badge.ticks
        apps.activate((apps.active_index + 1) % len(apps))

    capture()

    screen.alpha = 255
    screen.pen = background
    screen.clear()

    screen.pen = header
    screen.shape(shape.rounded_rectangle(0, 0, 160, 15, 8))
    screen.rectangle(0, 8, 160, 7)
    screen.font = font.sins
    screen.pen = text
    screen.text("Themes", 5, 2)

    draw_list()
    draw_preview()

    return None


run(update)
