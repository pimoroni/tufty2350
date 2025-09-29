import badgeware
from badgeware import WIDTH

display = badgeware.display
vector = badgeware.vector
t = badgeware.Transform()


class App:
    def init(self):
        # Colours
        self.BACKGROUND = display.create_pen(154, 203, 208)
        self.FOREGROUND = display.create_pen(242, 239, 231)
        self.HIGHLIGHT = display.create_pen(72, 166, 167)

        self.TEXT_SIZE = 1
        self.LINE_HEIGHT = 15

        self.TITLE_BAR = badgeware.Polygon()
        self.TITLE_BAR.rectangle(2, 2, WIDTH - 4, 16, (8, 8, 8, 8))
        self.TITLE_BAR.circle(WIDTH - 10, 10, 4)

        self.TEXT_BOX = badgeware.Polygon()
        self.TEXT_BOX.rectangle(2, 60, WIDTH - 4, 125, (8, 8, 8, 8))

    def update(self):
        pass

    def render(self):

        # Clear to white
        display.set_pen(self.BACKGROUND)
        display.clear()

        display.set_font("bitmap8")
        display.set_pen(self.FOREGROUND)
        vector.draw(self.TITLE_BAR)
        display.set_pen(self.HIGHLIGHT)
        display.text("tuftyOS", 7, 6, WIDTH, 1.0)
        display.text("info", WIDTH - 40, 6, WIDTH, 1)

        display.set_pen(self.HIGHLIGHT)
        vector.draw(self.TEXT_BOX)

        display.set_pen(self.FOREGROUND)

        y = 62 + int(self.LINE_HEIGHT / 2)

        display.text("Made by Pimoroni, powered by MicroPython", 5, y, WIDTH, self.TEXT_SIZE)
        y += self.LINE_HEIGHT
        display.text("Dual-core RP2350, Up to 150MHz with 520KB of SRAM", 5, y, WIDTH, self.TEXT_SIZE)
        y += self.LINE_HEIGHT
        display.text("16MB of QSPI flash", 5, y, WIDTH, self.TEXT_SIZE)
        y += self.LINE_HEIGHT
        display.text("320 x 240 pixel IPS LCD screen", 5, y, WIDTH, self.TEXT_SIZE)
        y += self.LINE_HEIGHT
        display.text("For more info:", 5, y, WIDTH, self.TEXT_SIZE)
        y += self.LINE_HEIGHT
        display.text("https://pimoroni.com/badgeware", 5, y, WIDTH, self.TEXT_SIZE)
        y += self.LINE_HEIGHT
        display.text("\nBadgewareOS", 5, y, WIDTH, self.TEXT_SIZE)

        display.update()


app = App()
init = app.init
update = app.update
render = app.render
