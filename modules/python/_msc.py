from picographics import PicoGraphics, DISPLAY_EXPLORER
display = PicoGraphics(DISPLAY_EXPLORER, rotate=180)
display.set_pen(0)
display.clear()
display.set_pen(0x22)
display.text("USB\nDisk\nMode", 1, 0, scale=4)
display.update()
