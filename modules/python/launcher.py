import gc
import math
import time

import badgeware

display = badgeware.display
display.set_font("bitmap8")
WIDTH, HEIGHT = badgeware.WIDTH, badgeware.HEIGHT

# Pico Vector
vector = badgeware.vector
vector.set_font("Roboto-Medium-With-Material-Symbols.af", 20)
vector.set_font_align(badgeware.HALIGN_CENTER)
t = badgeware.Transform()


class Launcher:
    def init(self):
        # Fade in the backlight
        i = 0
        while i < 15:
            i += 1
            display.set_backlight(i / 15)
            time.sleep(1.0 / 60)

        self.FONT_SIZE = 1

        self.state = {
            "selected_icon": "ebook",
            "running": "launcher",
            "selected_file": 0,
            "page": 0,
            "colours": [(24, 59, 78), (245, 238, 220), (255, 135, 0)]
        }

        badgeware.state_load("launcher", self.state)

        if self.state["running"] != "launcher":
            badgeware.launch(self.state["running"])

        self.apps = badgeware.apps

        # Colours
        self.BACKGROUND = display.create_pen(*self.state["colours"][0])
        self.FOREGROUND = display.create_pen(*self.state["colours"][1])
        self.HIGHLIGHT = display.create_pen(*self.state["colours"][2])
        self.RED = display.create_pen(255, 0, 0)
        self.YELLOW = display.create_pen(255, 255, 0)

        # Vector shapes
        self.TITLE_BAR = badgeware.Polygon()
        self.TITLE_BAR.rectangle(2, 2, 316, 16, (8, 8, 8, 8))
        self.TITLE_BAR.circle(308, 10, 4)
        self.SELECTED_BORDER = badgeware.Polygon()
        self.SELECTED_BORDER.rectangle(0, 0, 90, 90, (10, 10, 10, 10), 5)

        self.MAX_PER_ROW = 3
        self.MAX_PER_PAGE = self.MAX_PER_ROW * 2
        self.ICONS_TOTAL = len(self.apps)
        self.MAX_PAGE = math.ceil(self.ICONS_TOTAL / self.MAX_PER_PAGE)

        # Page layout
        self.centers = [[50, 65], [162, 65], [WIDTH - 50, 65], [50, 170], [162, 170], [WIDTH - 50, 170]]

        self.selected_index = self.app_index(self.state["selected_file"])

        self.changed = True

    def update(self):
        if badgeware.pressed(badgeware.BUTTON_A):
            if (self.selected_index % self.MAX_PER_ROW) > 0:
                self.selected_index -= 1
                self.changed = True

        if badgeware.pressed(badgeware.BUTTON_B):
            badgeware.launch(self.state["selected_file"])
            self.changed = True

        if badgeware.pressed(badgeware.BUTTON_C):
            if (self.selected_index % self.MAX_PER_ROW) < self.MAX_PER_ROW - 1:
                self.selected_index += 1
                self.selected_index = min(self.selected_index, self.ICONS_TOTAL - 1)
                self.changed = True

        if badgeware.pressed(badgeware.BUTTON_UP):
            if self.selected_index >= self.MAX_PER_ROW:
                self.selected_index -= self.MAX_PER_ROW
                self.changed = True

        if badgeware.pressed(badgeware.BUTTON_DOWN):
            if self.selected_index < self.ICONS_TOTAL - 1:
                self.selected_index += self.MAX_PER_ROW
                self.selected_index = min(self.selected_index, self.ICONS_TOTAL - 1)
                self.changed = True

        self.state["selected_file"] = self.apps[self.selected_index].path

        if self.changed:
            badgeware.state_save("launcher", self.state)
            self.changed = False
            badgeware.wait_for_user_to_release_buttons()

    def render(self):

        display.set_pen(self.BACKGROUND)
        display.clear()

        selected_page = self.selected_index // self.MAX_PER_PAGE

        icons = self.apps[selected_page * 6:selected_page * 6 + self.MAX_PER_PAGE]

        for index, app in enumerate(icons):
            x, y = self.centers[index]

            app.read_metadata()

            display.set_pen(self.FOREGROUND)
            vector.set_font_size(28)
            vector.set_transform(t)
            vector.text(app.icon, x, y)
            t.translate(x, y)
            t.scale(1.0, 1.0)

            if self.selected_index % self.MAX_PER_PAGE == index:
                display.set_pen(self.HIGHLIGHT)
                t.translate(-45, -36)
                t.scale(1.0, 1.0)
                vector.draw(self.SELECTED_BORDER)
            t.reset()

            display.set_pen(self.FOREGROUND)
            vector.set_font_size(18)
            w = vector.measure_text(app.name)[2]
            vector.text(app.name, int(x - (w / 2)), y + 45)

        for i in range(self.MAX_PAGE):
            x = 310
            y = int((240 / 2) - (self.MAX_PAGE * 10 / 2) + (i * 10))
            display.set_pen(self.HIGHLIGHT)
            display.rectangle(x, y, 8, 8)
            if self.state["page"] != i:
                display.set_pen(self.FOREGROUND)
                display.rectangle(x + 1, y + 1, 6, 6)

        display.set_pen(self.HIGHLIGHT)
        vector.draw(self.TITLE_BAR)

        self.draw_disk_usage(130)
        self.draw_battery_remaining(265)

        display.set_pen(self.FOREGROUND)
        vector.set_font_size(14)
        vector.text("TuftyOS", 7, 14)

        display.update()
        gc.collect()

    def draw_disk_usage(self, x):
        _, f_used, _ = badgeware.get_disk_usage()

        display.set_pen(self.FOREGROUND)

        badgeware.image(
            bytearray(
                (
                    0b00000000,
                    0b00111100,
                    0b00111100,
                    0b00111100,
                    0b00111000,
                    0b00000000,
                    0b00000000,
                    0b00000001,
                )
            ),
            8,
            8,
            x,
            6,
        )

        display.rectangle(x + 10, 5, 45, 10)
        display.set_pen(self.BACKGROUND)
        display.rectangle(x + 11, 6, 43, 8)
        display.set_pen(self.HIGHLIGHT)
        display.rectangle(x + 12, 7, int(41 / 100.0 * f_used), 6)

    def draw_battery_remaining(self, x):

        percentage = badgeware.get_battery_level()

        if badgeware.is_charging():
            display.set_pen(self.YELLOW)
        elif percentage <= 10:
            display.set_pen(self.RED)
        else:
            display.set_pen(self.FOREGROUND)

        display.rectangle(x + 10, 5, 20, 10)
        display.rectangle(x + 30, 8, 2, 4)
        display.set_pen(self.BACKGROUND)
        display.rectangle(x + 11, 6, 18, 8)
        display.set_pen(self.HIGHLIGHT)
        display.rectangle(x + 12, 7, int(16 / 100 * percentage), 6)

    def button(self, pin):
        self.changed = True

        if pin == badgeware.BUTTON_A:
            if (self.selected_file % self.MAX_PER_ROW) > 0:
                self.selected_file -= 1

        if pin == badgeware.BUTTON_B:
            badgeware.launch((self.state["page"] * self.MAX_PER_PAGE) + self.selected_file)

        if pin == badgeware.BUTTON_C:
            if (self.selected_file % self.MAX_PER_ROW) < self.MAX_PER_ROW - 1:
                self.selected_file += 1

        if pin == badgeware.BUTTON_UP:
            if self.selected_file >= self.MAX_PER_ROW:
                self.selected_file -= self.MAX_PER_ROW
            else:
                self.state["page"] = (self.state["page"] - 1) % self.MAX_PAGE
                self.selected_file += self.MAX_PER_ROW

        if pin == badgeware.BUTTON_DOWN:
            if self.selected_file < self.MAX_PER_ROW and self.icons_total > self.MAX_PER_ROW:
                self.selected_file += self.MAX_PER_ROW
            elif self.selected_file >= self.MAX_PER_ROW or self.icons_total < self.MAX_PER_ROW + 1:
                self.state["page"] = (self.state["page"] + 1) % self.MAX_PAGE
                self.selected_file %= self.MAX_PER_ROW

    def app_index(self, file):
        index = 0
        for app in self.apps:
            if app.path == file:
                return index
            index += 1
        return 0


launcher = Launcher()
launcher.init()

while True:
    launcher.update()
    launcher.render()
