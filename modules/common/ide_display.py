import badgeware


def hold():
    badge.mode(HIRES)
    screen.pen = color.black
    screen.clear()
    badgeware.message("Connected", "The Badgeware IDE is updating files.\n\nPress any button to cancel.")
    display.update()


def safe_mode():
    badge.mode(HIRES)
    screen.pen = color.black
    screen.clear()
    badgeware.message("Safe Mode", "Connect to the Badgeware IDE to repair your badge.\n\nPress RESET to restart.")
    display.update()


def error(_title, _message):
    pass
