import time

import badgeware_os
from picovector import (ANTIALIAS_BEST, HALIGN_CENTER, PicoVector, Polygon,
                        Transform)

import tufty2350

display = tufty2350.Tufty2350()
WIDTH, HEIGHT = display.get_bounds()

# Pico Vector
vector = PicoVector(display.display)
vector.set_antialiasing(ANTIALIAS_BEST)
vector.set_font("Roboto-Medium-With-Material-Symbols.af", 28)
vector.set_font_align(HALIGN_CENTER)
t = Transform()
vector.set_transform(t)

# Vector Elements
TITLE_BAR = Polygon()
TITLE_BAR.rectangle(2, 2, WIDTH - 4, 16, (8, 8, 8, 8))
TITLE_BAR.circle(WIDTH - 10, 10, 4)

SELECTED_BAR = Polygon()
SELECTED_BAR.rectangle(0, 0, WIDTH - 8, 33, (8, 8, 8, 8))

OK_BUTTON = Polygon()
OK_BUTTON.rectangle(144, HEIGHT - 25, 30, 20, (8, 8, 8, 8))

state = {}

badgeware_os.state_load("launcher", state)

# Colours
BACKGROUND = display.create_pen(*state["colours"][0])
FOREGROUND = display.create_pen(*state["colours"][1])
HIGHLIGHT = display.create_pen(*state["colours"][2])

PALETTES = {
    "Default": [(24, 59, 78), (245, 238, 220), (255, 135, 0)],
    "Plum": [(119, 67, 96), (231, 171, 121), (178, 80, 104)],
    "Slate": [(55, 55, 55), (201, 216, 232), (57, 91, 100)],
    "Sea": [(154, 203, 208), (242, 239, 231), (72, 166, 167)],
    "Mint": [(158, 188, 138), (210, 208, 160), (115, 148, 107)],
    "Coffee": [(111, 78, 55), (236, 177, 118), (166, 123, 91)]
}


def wait_for_user_to_release_buttons():
    while display.pressed_any():
        time.sleep(0.01)


def set_theme(palette):
    global BACKGROUND, FOREGROUND, HIGHLIGHT
    state["colours"] = palette
    badgeware_os.state_save("launcher", state)

    # Reload colours
    BACKGROUND = display.create_pen(*state["colours"][0])
    FOREGROUND = display.create_pen(*state["colours"][1])
    HIGHLIGHT = display.create_pen(*state["colours"][2])


class Menu(object):
    def __init__(self, items):
        self.items = items
        self.selected = 0
        self.cursor = "<<"

    # A function to draw only the menu elements.
    def draw_menu(self):

        vector.set_font_size(28)

        for item in range(len(self.items)):
            if self.selected == item:
                display.set_pen(HIGHLIGHT)
                t.translate(4, 25 + item * 30)
                vector.draw(SELECTED_BAR)
                t.reset()

            display.set_pen(FOREGROUND)
            vector.text(self.items[item], 10, 50 + item * 30)

    # Do a thing based on the currently selected menu item
    def process_selected(self):
        set_theme(PALETTES[self.items[self.selected]])

    def user_input(self):

        # Process the user input and update the currently selected item
        if display.pressed(tufty2350.BUTTON_DOWN):
            if self.selected + 1 < len(self.items):
                self.selected += 1
            else:
                self.selected = 0
            wait_for_user_to_release_buttons()  # debounce

        if display.pressed(tufty2350.BUTTON_UP):
            if self.selected > 0:
                self.selected -= 1
            else:
                self.selected = len(self.items) - 1
            wait_for_user_to_release_buttons()  # debounce

        if display.pressed(tufty2350.BUTTON_B):
            self.process_selected()
            wait_for_user_to_release_buttons()  # debounce


menu = Menu(list(PALETTES.keys()))

while True:

    # Page Header
    display.set_pen(BACKGROUND)
    display.clear()

    display.set_pen(FOREGROUND)
    vector.draw(TITLE_BAR)

    vector.draw(OK_BUTTON)
    display.set_pen(BACKGROUND)
    vector.set_font_size(16)
    vector.text("Set", 149, HEIGHT - 10)

    display.set_pen(HIGHLIGHT)
    display.text("tuftyOS", 7, 6, WIDTH, 1)
    display.text("Settings", WIDTH - 65, 6, WIDTH, 1)

    menu.draw_menu()
    menu.user_input()

    display.update()
