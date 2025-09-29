import badgeware
from badgeware import WIDTH

display = badgeware.display
vector = badgeware.vector


class App:

    def init(self):
        self.TITLE_BAR = badgeware.Polygon()
        self.TITLE_BAR.rectangle(2, 2, WIDTH - 4, 16, (8, 8, 8, 8))
        self.TITLE_BAR.circle(WIDTH - 10, 10, 4)

        self.TEXT_BOX = badgeware.Polygon()
        self.TEXT_BOX.rectangle(2, 65, WIDTH - 4, 130, (8, 8, 8, 8))

        # Colours
        self.BACKGROUND = display.create_pen(158, 188, 138)
        self.FOREGROUND = display.create_pen(210, 208, 160)
        self.HIGHLIGHT = display.create_pen(115, 148, 107)

        self.LINE_HEIGHT = 20

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
        display.text("TuftyOS", 7, 6, WIDTH, 1.0)
        display.text("help", WIDTH - 40, 6, WIDTH, 1)

        display.set_pen(self.FOREGROUND)
        vector.draw(self.TEXT_BOX)

        display.set_pen(self.HIGHLIGHT)
        TEXT_SIZE = 2.0
        y = 72 + int(self.LINE_HEIGHT / 2)
        x = 7

        display.set_font("bitmap8")
        display.text("Up/Down - Move up and down", x, y, WIDTH, TEXT_SIZE)
        y += self.LINE_HEIGHT
        display.text("a - Move left", x, y, WIDTH, TEXT_SIZE)
        y += self.LINE_HEIGHT
        display.text("b - Launch selected app", x, y, WIDTH, TEXT_SIZE)
        y += self.LINE_HEIGHT
        display.text("c - Move right", x, y, WIDTH, TEXT_SIZE)
        y += self.LINE_HEIGHT
        display.text("HOME - Exit app", x, y, WIDTH, TEXT_SIZE)
        y += self.LINE_HEIGHT

        display.update()

app = App()
init = app.init
update = app.update
render = app.render
