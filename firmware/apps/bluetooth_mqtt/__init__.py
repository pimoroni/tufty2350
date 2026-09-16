import sys
import os

sys.path.insert(0, "/system/apps/bluetooth_mqtt")
os.chdir("/system/apps/bluetooth_mqtt")

import ble

DEVICE_NAME = "Tufty2350"
MAX_LOG_LINES = 6
LINE_HEIGHT = 12

try:
    screen.font = rom_font.sins
except (NameError, AttributeError):
    screen.font = font.sins

sent_count = 0
log = []


def add_log(line):
    global log
    log.append(line)
    log = log[-MAX_LOG_LINES:]


def draw_header():
    screen.pen = color.rgb(15, 30, 50)
    screen.clear()

    screen.pen = color.white
    screen.text("Bluetooth MQTT Relay", 10, 6)

    if ble.is_connected():
        screen.pen = color.rgb(120, 220, 120)
        status = "Connected"
    else:
        screen.pen = color.rgb(220, 190, 120)
        status = f"Advertising as {DEVICE_NAME}"
    screen.text(status, 10, 20)


def draw_log():
    y = 38
    for line in log:
        screen.pen = color.white
        screen.text(line[:26], 10, y)
        y += LINE_HEIGHT


def draw_footer():
    screen.pen = color.rgb(180, 180, 180)
    screen.text("A: send message to laptop", 10, screen.height - 12)


def init():
    ble.start(name=DEVICE_NAME)

_DATETIME_PREFIX_LEN = const(19)  # "YYYY-MM-DD HH:MM:SS"

def format_message(msg):
    prefix = msg[:_DATETIME_PREFIX_LEN]
    is_datetime = (
        len(prefix) == _DATETIME_PREFIX_LEN
        and prefix[4] == "-"
        and prefix[7] == "-"
        and prefix[10] == " "
        and prefix[13] == ":"
        and prefix[16] == ":"
        and prefix[:4].isdigit()
        and prefix[5:7].isdigit()
        and prefix[8:10].isdigit()
        and prefix[11:13].isdigit()
        and prefix[14:16].isdigit()
        and prefix[17:19].isdigit()
    )
    if is_datetime:
        return prefix[11:19] + msg[_DATETIME_PREFIX_LEN:]
    return msg

def update():
    global sent_count

    ble.poll()

    for message in ble.read():
        add_log(f"< {format_message(message)}")

    if badge.pressed(BUTTON_A) and ble.is_connected():
        sent_count += 1
        message = f"Hello from Tufty! ({sent_count})"
        ble.send(message)
        add_log(f"> {message}")

    if badge.pressed(BUTTON_B) and ble.is_connected():
        sent_count += 1
        message = f"I'm in MQTT lol"
        ble.send(message)
        add_log(f"> {message}")

    if badge.pressed(BUTTON_C) and ble.is_connected():
        sent_count += 1
        message = f"Who farted?  -- Nick Swardson"
        ble.send(message)
        add_log(f"> {message}")

    draw_header()
    draw_log()
    draw_footer()


def on_exit():
    ble.stop()


init()
run(update)
