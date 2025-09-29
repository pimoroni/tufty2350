import badgeware
from badgeware import WIDTH, HEIGHT

display = badgeware.display
vector = badgeware.vector

vector.set_font("Roboto-Medium-With-Material-Symbols.af", 20)
vector.set_font_align(badgeware.HALIGN_CENTER)
t = badgeware.Transform()

class App:

    def init(self):
        # Vector Elements
        self.TITLE_BAR = badgeware.Polygon()
        self.TITLE_BAR.rectangle(2, 2, WIDTH - 4, 16, (8, 8, 8, 8))
        self.TITLE_BAR.circle(WIDTH - 10, 10, 4)
        self.TEXT_BOX = badgeware.Polygon()
        self.TEXT_BOX.rectangle(2, 30, 260, 125, (8, 8, 8, 8))
        self.BUTTON_BOX = badgeware.Polygon()
        self.BUTTON_BOX.rectangle(0, 0, 50, 20, (8, 8, 8, 8))

        # Position of the buttons on the X axis
        self.BUTTON_X_POS = [34, 134, 234]

        # Centre point of the X axis
        self.CENTRE_X = WIDTH // 2

        # ------------------------------
        #      User Settings
        # ------------------------------
        # Your daily goal and measurements
        # Adjust these values to match your cup, bottle size or whatever suits you best :)
        self.GOAL = 2000
        self.WATER_MEASUREMENTS = [250, 500, 750]
        self.MEASUREMENT_UNIT = "ml"

        # Colours
        self.BACKGROUND = display.create_pen(154, 203, 208)
        self.FOREGROUND = display.create_pen(242, 239, 231)
        self.HIGHLIGHT = display.create_pen(72, 166, 167)

        # Setup and load the state
        self.state = {
            "goal": self.GOAL,
            "unit": self.MEASUREMENT_UNIT,
            "total": 0
        }
        badgeware.state_load("hydrate", self.state)

        self.changed = False
        self.woken_by_button = badgeware.woken_by_button()
        if not self.woken_by_button:
            self.changed = True

    def update(self):

        if badgeware.pressed(badgeware.BUTTON_A):
            self.button(badgeware.BUTTON_A)
        if badgeware.pressed(badgeware.BUTTON_B):
            self.button(badgeware.BUTTON_B)
        if badgeware.pressed(badgeware.BUTTON_C):
            self.button(badgeware.BUTTON_C)

        if badgeware.pressed(badgeware.BUTTON_UP):
            self.button(badgeware.BUTTON_UP)
        if badgeware.pressed(badgeware.BUTTON_DOWN):
            self.button(badgeware.BUTTON_DOWN)

        if self.changed:
            self.changed = False
            badgeware.state_save("hydrate", self.state)

    def render(self):

        # Clear to white
        display.set_pen(self.BACKGROUND)
        display.clear()

        # Draw our title bar
        display.set_font("bitmap8")
        display.set_pen(self.FOREGROUND)
        vector.draw(self.TITLE_BAR)
        display.set_pen(self.HIGHLIGHT)
        display.text("tuftyOS", 7, 6, WIDTH, 1.0)
        display.text("Hydrate", WIDTH - 55, 6, WIDTH, 1)
        goal_width = display.measure_text(f"Goal: {self.GOAL}{self.MEASUREMENT_UNIT}", 1)
        goal_width //= 2
        display.text(f"Goal: {self.GOAL}{self.MEASUREMENT_UNIT}", self.CENTRE_X - goal_width, 6, WIDTH, 1)

        # Draw the 3 buttons and labels
        for i in range(3):
            display.set_pen(self.FOREGROUND)
            vector.set_transform(t)
            t.translate(self.BUTTON_X_POS[i], HEIGHT - 25)
            vector.draw(self.BUTTON_BOX)
            display.set_pen(self.HIGHLIGHT)
            measurement_string = f"{self.WATER_MEASUREMENTS[i]}{self.MEASUREMENT_UNIT}"
            measurement_offset = display.measure_text(measurement_string, 1)
            measurement_offset //= 2
            display.text(measurement_string, self.BUTTON_X_POS[i] + measurement_offset, HEIGHT - 18, WIDTH, 1)
            t.reset()

        display.set_pen(self.FOREGROUND)

        # Draw the title
        vector.set_font_size(40)
        today_string = "Today:"
        today_offset = int(vector.measure_text(today_string)[2] // 2)
        vector.text(today_string, self.CENTRE_X - today_offset, 95)

        # Draw the current total
        vector.set_font_size(80)
        total_string = f"{self.state["total"]}{self.MEASUREMENT_UNIT}"
        total_offset = int(vector.measure_text(total_string)[2] // 2)
        vector.text(total_string, self.CENTRE_X - total_offset, 155)

        # Update the screen!
        display.update()


    def button(self, pin):
        self.changed = True

        if pin == badgeware.BUTTON_A:
            self.state["total"] += self.WATER_MEASUREMENTS[0]

        if pin == badgeware.BUTTON_B:
            self.state["total"] += self.WATER_MEASUREMENTS[1]

        if pin == badgeware.BUTTON_C:
            self.state["total"] += self.WATER_MEASUREMENTS[2]

        # Press up to reset the total.
        if pin == badgeware.BUTTON_UP:
            self.state["total"] = 0

        if pin == badgeware.BUTTON_DOWN:
            pass

        if pin == badgeware.BUTTON_HOME:
            pass

        badgeware.wait_for_user_to_release_buttons()


app = App()
init = app.init
update = app.update
render = app.render
