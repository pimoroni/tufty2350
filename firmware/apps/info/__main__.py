import tufty2350
import version
from tufty2350 import WIDTH
from picovector import ANTIALIAS_BEST, PicoVector, Polygon, Transform

TEXT_SIZE = 1
LINE_HEIGHT = 15

version = version.BUILD

display = tufty2350.Tufty2350()
# display.led(128)

# Colours
BACKGROUND = display.create_pen(154, 203, 208)
FOREGROUND = display.create_pen(242, 239, 231)
HIGHLIGHT = display.create_pen(72, 166, 167)

# Pico Vector
vector = PicoVector(display.display)
vector.set_antialiasing(ANTIALIAS_BEST)
t = Transform()

TITLE_BAR = Polygon()
TITLE_BAR.rectangle(2, 2, WIDTH - 4, 16, (8, 8, 8, 8))
TITLE_BAR.circle(WIDTH - 10, 10, 4)

TEXT_BOX = Polygon()
TEXT_BOX.rectangle(2, 60, WIDTH - 4, 125, (8, 8, 8, 8))

while True:

    # Clear to white
    display.set_pen(BACKGROUND)
    display.clear()

    display.set_font("bitmap8")
    display.set_pen(FOREGROUND)
    vector.draw(TITLE_BAR)
    display.set_pen(HIGHLIGHT)
    display.text("tuftyOS", 7, 6, WIDTH, 1.0)
    display.text("info", WIDTH - 40, 6, WIDTH, 1)

    display.set_pen(HIGHLIGHT)
    vector.draw(TEXT_BOX)

    display.set_pen(FOREGROUND)

    y = 62 + int(LINE_HEIGHT / 2)

    display.text("Made by Pimoroni, powered by MicroPython", 5, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT
    display.text("Dual-core RP2350, Up to 150MHz with 520KB of SRAM", 5, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT
    display.text("16MB of QSPI flash", 5, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT
    display.text("320 x 240 pixel IPS LCD screen", 5, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT
    display.text("For more info:", 5, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT
    display.text("https://pimoroni.com/tufty2350", 5, y, WIDTH, TEXT_SIZE)
    y += LINE_HEIGHT
    display.text(f"\nTuftyOS OS {version}", 5, y, WIDTH, TEXT_SIZE)

    display.update()
