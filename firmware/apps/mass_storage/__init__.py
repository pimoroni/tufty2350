import machine
import time

# Enter USB Mass Storage mode from a *clean* boot rather than running it inline on
# top of the live badge framework (wifi/bt/display all still holding resources).
#
# We do this by faking a double-tap: powman keeps a "double-tap" flag in its
# always-on CHIP_RESET register that survives a reset. On the next boot
# powman_startup() sees the flag set after a software reset and reports a
# WAKE_DOUBLETAP wake reason, so main.py takes the exact same path as a physical
# double-tap and imports _msc.
#
# powman registers need the 0x5afe password in the top 16 bits; writing via the
# atomic set-bits alias (base + 0x2000) sets just the double-tap bit.
POWMAN_CHIP_RESET_SET = 0x40100000 + 0x2c + 0x2000
POWMAN_PASSWORD = 0x5afe0000
CHIP_RESET_DOUBLE_TAP = 0x00000001


def show_message():
    screen.pen = color.black
    screen.shape(shape.rectangle(0, 0, 160, 120))
    try:
        screen.font = rom_font.absolute
    except OSError:
        pass
    screen.pen = color.white
    for line, y in (("Switching to", 44), ("USB Disk Mode...", 60)):
        w, _ = screen.measure_text(line)
        screen.text(line, 80 - (w / 2), y)
    display.update()


show_message()
time.sleep(0.4)  # let the message land before we drop off the bus

machine.mem32[POWMAN_CHIP_RESET_SET] = POWMAN_PASSWORD | CHIP_RESET_DOUBLE_TAP
machine.reset()
