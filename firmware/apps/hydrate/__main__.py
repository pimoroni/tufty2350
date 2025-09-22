import tufty2350
from tufty2350 import WIDTH, HEIGHT
from picovector import ANTIALIAS_BEST, PicoVector, Polygon, Transform, HALIGN_CENTER
import tufty_os
import time

display = tufty2350.Tufty2350()
# display.led(0)
display.set_thickness(2)

# Pico Vector
vector = PicoVector(display.display)
vector.set_antialiasing(ANTIALIAS_BEST)
vector.set_font("Roboto-Medium-With-Material-Symbols.af", 20)
vector.set_font_align(HALIGN_CENTER)
t = Transform()

# Vector Elements
TITLE_BAR = Polygon()
TITLE_BAR.rectangle(2, 2, WIDTH - 4, 16, (8, 8, 8, 8))
TITLE_BAR.circle(WIDTH - 10, 10, 4)
TEXT_BOX = Polygon()
TEXT_BOX.rectangle(2, 30, 260, 125, (8, 8, 8, 8))
BUTTON_BOX = Polygon()
BUTTON_BOX.rectangle(0, 0, 50, 20, (8, 8, 8, 8))

# Position of the buttons on the X axis
BUTTON_X_POS = [34, 134, 234]

# Centre point of the X axis
CENTRE_X = WIDTH // 2

# ------------------------------
#      User Settings
# ------------------------------
# Your daily goal and measurements
# Adjust these values to match your cup, bottle size or whatever suits you best :)
GOAL = 2000
WATER_MEASUREMENTS = [250, 500, 750]
MEASUREMENT_UNIT = "ml"

# Colours
BACKGROUND = display.create_pen(154, 203, 208)
FOREGROUND = display.create_pen(242, 239, 231)
HIGHLIGHT = display.create_pen(72, 166, 167)

# Setup and load the state
state = {
    "goal": GOAL,
    "unit": MEASUREMENT_UNIT,
    "total": 0
}
tufty_os.state_load("hydrate", state)

changed = False

woken_by_button = tufty2350.woken_by_button()


def wait_for_user_to_release_buttons():
    while display.pressed_any():
        time.sleep(0.01)


def render():

    # display.led(128)

    # Clear to white
    display.set_pen(BACKGROUND)
    display.clear()

    # Draw our title bar
    display.set_font("bitmap8")
    display.set_pen(FOREGROUND)
    vector.draw(TITLE_BAR)
    display.set_pen(HIGHLIGHT)
    display.text("tuftyOS", 7, 6, WIDTH, 1.0)
    display.text("Hydrate", WIDTH - 55, 6, WIDTH, 1)
    goal_width = display.measure_text(f"Goal: {GOAL}{MEASUREMENT_UNIT}", 1)
    goal_width //= 2
    display.text(f"Goal: {GOAL}{MEASUREMENT_UNIT}", CENTRE_X - goal_width, 6, WIDTH, 1)

    # Draw the 3 buttons and labels
    for i in range(3):
        display.set_pen(FOREGROUND)
        vector.set_transform(t)
        t.translate(BUTTON_X_POS[i], HEIGHT - 25)
        vector.draw(BUTTON_BOX)
        display.set_pen(HIGHLIGHT)
        measurement_string = f"{WATER_MEASUREMENTS[i]}{MEASUREMENT_UNIT}"
        measurement_offset = display.measure_text(measurement_string, 1)
        measurement_offset //= 2
        display.text(measurement_string, BUTTON_X_POS[i] + measurement_offset, HEIGHT - 18, WIDTH, 1)
        t.reset()

    display.set_pen(FOREGROUND)

    # Draw the title
    vector.set_font_size(40)
    today_string = "Today:"
    today_offset = int(vector.measure_text(today_string)[2] // 2)
    vector.text(today_string, CENTRE_X - today_offset, 95)

    # Draw the current total
    vector.set_font_size(80)
    total_string = f"{state["total"]}{MEASUREMENT_UNIT}"
    total_offset = int(vector.measure_text(total_string)[2] // 2)
    vector.text(total_string, CENTRE_X - total_offset, 155)

    # Update the screen!
    display.update()
    #  display.led(0)


def button(pin):
    global changed
    changed = True

    if pin == tufty2350.BUTTON_A:
        state["total"] += WATER_MEASUREMENTS[0]

    if pin == tufty2350.BUTTON_B:
        state["total"] += WATER_MEASUREMENTS[1]

    if pin == tufty2350.BUTTON_C:
        state["total"] += WATER_MEASUREMENTS[2]

    # Press up to reset the total.
    if pin == tufty2350.BUTTON_UP:
        state["total"] = 0

    if pin == tufty2350.BUTTON_DOWN:
        pass

    if pin == tufty2350.BUTTON_USER:
        pass

    wait_for_user_to_release_buttons()


if not woken_by_button:
    changed = True

while True:

    if display.pressed(tufty2350.BUTTON_A):
        button(tufty2350.BUTTON_A)
    if display.pressed(tufty2350.BUTTON_B):
        button(tufty2350.BUTTON_B)
    if display.pressed(tufty2350.BUTTON_C):
        button(tufty2350.BUTTON_C)

    if display.pressed(tufty2350.BUTTON_UP):
        button(tufty2350.BUTTON_UP)
    if display.pressed(tufty2350.BUTTON_DOWN):
        button(tufty2350.BUTTON_DOWN)

    if changed:
        changed = False
        tufty_os.state_save("hydrate", state)
        render()
