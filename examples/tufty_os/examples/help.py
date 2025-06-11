# ICON help
# NAME Help
# DESC How to use your Tufty 2350.

from picovector import ANTIALIAS_BEST, PicoVector, Polygon, Transform

import tufty2350
from tufty2350 import WIDTH

LINE_HEIGHT = 20

display = tufty2350.Tufty2350()
display.led(128)

# Pico Vector
vector = PicoVector(display.display)
vector.set_antialiasing(ANTIALIAS_BEST)
t = Transform()

TITLE_BAR = Polygon()
TITLE_BAR.rectangle(2, 2, WIDTH - 4, 16, (8, 8, 8, 8))
TITLE_BAR.circle(WIDTH - 10, 10, 4)

TEXT_BOX = Polygon()
TEXT_BOX.rectangle(2, 65, WIDTH - 4, 130, (8, 8, 8, 8))

# Colours
BACKGROUND = display.create_pen(158, 188, 138)
FOREGROUND = display.create_pen(210, 208, 160)
HIGHLIGHT = display.create_pen(115, 148, 107)


while True:
    # Clear to white
    display.set_pen(BACKGROUND)
    display.clear()

    display.set_font("bitmap8")
    display.set_pen(FOREGROUND)
    vector.draw(TITLE_BAR)
    display.set_pen(HIGHLIGHT)
    display.text("TuftyOS", 7, 6, WIDTH, 1.0)
    display.text("help", WIDTH - 40, 6, WIDTH, 1)

    display.set_pen(FOREGROUND)
    vector.draw(TEXT_BOX)

    display.set_pen(HIGHLIGHT)
    TEXT_SIZE = 2.0
    y = 72 + int(LINE_HEIGHT / 2)
    x = 7

    display.set_font("bitmap8")
    display.text("Up/Down - Move up and down", x, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT
    display.text("a - Move left", x, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT
    display.text("b - Launch selected app", x, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT
    display.text("c - Move right", x, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT
    display.text("a & c - Exit app", x, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT

    display.update()
