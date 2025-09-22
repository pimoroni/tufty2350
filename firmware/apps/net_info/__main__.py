import ezwifi
from picovector import ANTIALIAS_BEST, PicoVector, Polygon, Transform

import tufty2350
from tufty2350 import HEIGHT, WIDTH

# Display Setup
display = tufty2350.Tufty2350()
# display.led(0)

# Pico Vector
vector = PicoVector(display.display)
vector.set_antialiasing(ANTIALIAS_BEST)
t = Transform()
vector.set_transform(t)

TITLE_BAR = Polygon()
TITLE_BAR.rectangle(2, 2, WIDTH - 4, 16, (8, 8, 8, 8))
TITLE_BAR.circle(WIDTH - 10, 10, 4)
IP_BAR = Polygon()
IP_BAR.rectangle(2, 113, WIDTH - 4, 40, (8, 8, 8, 8))

# Colours
BACKGROUND = display.create_pen(63, 79, 68)
FOREGROUND = display.create_pen(37, 95, 56)
HIGHLIGHT = display.create_pen(31, 125, 83)


def draw_header():

    # Page Header
    display.set_pen(BACKGROUND)
    display.clear()

    display.set_pen(FOREGROUND)
    vector.draw(TITLE_BAR)

    display.set_pen(HIGHLIGHT)
    display.text("tuftyOS", 7, 6, WIDTH, 1)
    display.text("Network Details", WIDTH - 100, 6, WIDTH, 1)


def connect_handler(wifi):
    # Make sure the LED is on to signal the WiFi has connected
    # display.led(128)

    # Draw the title header
    draw_header()

    display.set_pen(FOREGROUND)
    vector.draw(IP_BAR)

    ip = wifi.ipv4()

    text_w = display.measure_text(ip, 4)
    text_x = WIDTH // 2 - text_w // 2
    display.set_pen(HIGHLIGHT)
    display.text(ip, text_x, HEIGHT // 2, WIDTH, 4)

    display.text("Your local IP:", text_x, 95, WIDTH, 2)

    display.update()


def failed_handler(_wifi):
    # Make sure the LED is OFF to signal the WiFi has not connected
    # display.led(0)

    # Draw the title header
    draw_header()

    display.set_pen(FOREGROUND)
    vector.draw(IP_BAR)

    ip = "Unavailable"

    text_w = display.measure_text(ip, 4)
    text_x = WIDTH // 2 - text_w // 2
    display.set_pen(HIGHLIGHT)
    display.text(ip, text_x, HEIGHT // 2, WIDTH, 4)

    display.text("Your local IP:", text_x, 95, WIDTH, 2)

    display.text("Check Your 'secrets.py' and try again.", 5, 160, WIDTH - 15, 2)

    display.update()


# display.led(128)
draw_header()
display.set_pen(HIGHLIGHT)
display.text("Connecting...", 5, 120, WIDTH - 15, 2)
display.update()

ezwifi.connect(verbose=True, retries=3, connected=connect_handler, failed=failed_handler)

while True:
    pass
