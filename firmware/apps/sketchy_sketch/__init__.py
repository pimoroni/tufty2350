import time
import tufty2350
from picovector import (ANTIALIAS_BEST, HALIGN_CENTER, PicoVector, Polygon,
                        Transform)

# Display Setup
display = tufty2350.Tufty2350()
# display.led(128)
display.set_backlight(1.0)

# Pico Vector
vector = PicoVector(display.display)
vector.set_antialiasing(ANTIALIAS_BEST)
t = Transform()
vector.set_font("Roboto-Medium-With-Material-Symbols.af", 20)
vector.set_font_align(HALIGN_CENTER)
vector.set_transform(t)

DRAW_AREA = Polygon()
DRAW_AREA.rectangle(25, 25, 270, 180, (8, 8, 8, 8))


def draw_area():
    display.set_pen(display.create_pen(200, 0, 0))
    display.clear()

    display.set_pen(display.create_pen(255, 215, 0))
    vector.text("Sketchy-Sketch", 105, 17)

    # draw main surface
    display.set_pen(display.create_pen(205, 205, 205))
    vector.draw(DRAW_AREA)

    # draw knobs
    display.set_pen(display.create_pen(150, 50, 50))
    display.circle(25 + 5, 225 + 5, 20)
    display.circle(295 + 5, 225 + 5, 20)
    display.set_pen(display.create_pen(255, 255, 255))
    display.circle(25 - 1, 225 - 1, 16)
    display.circle(295 - 1, 225 - 1, 16)
    display.set_pen(display.create_pen(155, 155, 155))
    display.circle(25 + 1, 225 + 1, 16)
    display.circle(295 + 1, 225 + 1, 16)
    display.set_pen(display.create_pen(205, 205, 205))
    display.circle(25, 225, 15)
    display.circle(295, 225, 15)


# start position for drawing cursor
position_x = 160
position_y = 110

# draw the sketchy sketch
draw_area()

while True:
    # check for user input and update cursor position as needed
    if display.pressed(tufty2350.BUTTON_C) and position_x < 290:
        position_x += 1

    if display.pressed(tufty2350.BUTTON_A) and position_x > 30:
        position_x -= 1

    if display.pressed(tufty2350.BUTTON_UP) and position_y > 30:
        position_y -= 1

    if display.pressed(tufty2350.BUTTON_DOWN) and position_y < 200:
        position_y += 1

    if display.pressed(tufty2350.BUTTON_B):
        draw_area()

    # draw the line
    display.set_pen(display.create_pen(50, 50, 50))
    display.circle(position_x, position_y, 2)

    # update the screen contents
    display.update()

    time.sleep(0.005)
