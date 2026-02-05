import time

import network
import powman
import st7789
from machine import ADC, I2C, Pin, Timer
from pcf85063a import PCF85063A
import gc
import os

display = st7789.ST7789()

"""
Hardware Error Codes:

E1 - Wireless scan fail - unable to detect networks.
E2 - Charging Fail
E3 - RTC Alarm was in a triggeered state in pre checks.
E4 - RTC Alarm didn't trigger after timer
E5 - VBUS DETECT Fail or timed out
E6 - VBUS Detect was in a triggered state in pre checks.
E7 - VBAT SENSE reading was out of range
E8 - SW_POWER_EN function test failed
E10 - MAC Address invalid
E11 - Time out during button test
E12 - Light sensor reading out of range
E14 - Missing secrets file for network connection
E15 - Failed to connect to network
E17 - Failed to start CYW43 (RM2 Module)
E18 - PSRAM Test Failure

"""

WHITE = color.rgb(255, 255, 255)
BLACK = color.rgb(0, 0, 0)
DARK_BLUE = color.rgb(0, 100, 150)
DARK_RED = color.rgb(150, 0, 0)
DARK_GREEN = color.rgb(0, 200, 0)
DARK_RED = color.rgb(150, 0, 0)

WIDTH, HEIGHT = 160, 120

CL = [Pin(0, Pin.OUT), Pin(1, Pin.OUT),
      Pin(2, Pin.OUT), Pin(3, Pin.OUT)]

charge_stat = Pin.board.CHARGE_STAT
charge_stat.init(mode=Pin.IN)
vbus_detect = Pin.board.VBUS_DETECT
sw_int = Pin.board.BUTTON_INT
rtc_alarm = Pin.board.RTC_ALARM
vbat = ADC(Pin.board.VBAT_SENSE)

up = Pin.board.BUTTON_UP
down = Pin.board.BUTTON_DOWN
a = Pin.board.BUTTON_A
b = Pin.board.BUTTON_B
c = Pin.board.BUTTON_C
home = Pin.board.BUTTON_HOME
power = Pin.board.POWER_EN
LIGHT_SENSOR = ADC(Pin.board.LIGHT_SENSE)

font_ignore = pixel_font.load("/system/assets/fonts/ignore.ppf")
screen.font = font_ignore

TEXT_SIZE = 12
screen.antialias = image.X4


def get_light():
    return LIGHT_SENSOR.read_u16()


def wrap_and_measure(image, text, size, max_width):
    result = []

    for line in text.splitlines():
        # if max_width is specified then perform word wrapping
        if max_width:
            # setup a start and end cursor to traverse the text
            start, end = 0, 0
            while True:
                # search for the next space
                end = line.find(" ", end)
                if end == -1:
                    end = len(line)

                # measure the text up to the space
                width, _ = image.measure_text(line[start:end], size)
                if width > max_width:
                    # line exceeded max length
                    end = line.rfind(" ", start, end)
                    result.append((line[start:end], width))
                    start = end + 1
                elif end == len(line):
                    # reached the end of the string
                    result.append((line[start:end], width))
                    break

                # step past the last space
                end += 1
        else:
            # no wrapping needed, just return the original line with its width
            width, _ = image.measure_text(line, size)
            result.append((line, width))

    return result


class Tests:
    def __init__(self):

        self.wifi_pass = None
        self.buttons_pass = False
        self.vbus_pass = False
        self.rtc_pass = None

        sw_int.irq(self.btn_handler)

        # RTC Setup
        self.rtc = PCF85063A(I2C())
        self.rtc.clear_timer_flag()
        self.rtc.enable_timer_interrupt(True)
        self.rtc_start = time.time()

        # Toggle the case lights once every second
        self.cl_timer = Timer()
        self.cl_timer.init(mode=Timer.PERIODIC, period=1000, callback=self.cl_toggle)

        # We want to check the RTC alarm has trigger
        self.rtc_timer = Timer()

        # Raspberry Pi Vendor ID
        self.vendor = "28:CD:C1"

        # a dict to store the button name, state and label location on screen
        self.buttons = {"A": [False, (24, 107)], "B": [False, (73, 107)],
                        "C": [False, (123, 107)], "UP": [False, (WIDTH - 13, 30)],
                        "DOWN": [False, (WIDTH - 13, 82)], "HOME": [False, (WIDTH // 2 - 7, 5)]}

    def test_wireless(self):

        self.wlan = network.WLAN(network.WLAN.IF_STA)
        self.wlan.active(True)
        self.mac = self.wlan.config("mac")

        try:
            if self.wifi_pass is None:
                data = ":".join([f"{b:02X}" for b in self.mac])
                print(self.wlan.config("mac"))
                results = self.wlan.scan()

                if len(results) == 0:
                    raise Exception("E1")

                if data[:8] != self.vendor:
                    raise Exception("E10")

                self.wifi_pass = True
        except OSError:
            raise Exception("E17") from None

    def display_error(self, error):
        screen.pen = DARK_RED
        screen.clear()

        tw, th = screen.measure_text(str(error))

        screen.pen = WHITE
        screen.text(str(error), WIDTH / 2 - (tw / 2), HEIGHT / 2 - th / 2)
        display.update()

    def test_buttons(self):
        # Check if all buttons have been pressed
        if not self.buttons_pass:
            for button in self.buttons:
                if not self.buttons[button][0]:
                    return

            self.buttons_pass = True
            print("BUTTONS: OK!")

    def test_charge_stat(self):
        # if battery charging is not detected
        # raise an exception and end the test
        print(charge_stat.value())
        if charge_stat.value() == 1:
            raise Exception("E2")

    def test_vbat(self):
        voltage = vbat.read_u16() * (3.3 / 65536) * 2
        print(voltage)
        if voltage > 4.2 or voltage < 3.6:
            raise Exception("E7")

    def test_light(self):
        reading = get_light()
        if reading < 100 or reading > 2000:
            raise Exception("E12")

    def test_psram(self):
        ram_free = round(gc.mem_free() / 1000000, 1)

        if ram_free < 6.0 or not powman._test_psram_cs():  # noqa: SLF001
            raise Exception("E18")

    # Toggle the case lights on the back of the badge
    def cl_toggle(self, _t):
        for led in CL:
            led.toggle()
        time.sleep(0.2)

    def clear_flag(self):
        # Now the test has complete, we can remove the flag.
        try:
            os.remove("hardware_test.txt")
        except OSError:
            pass

    # Handle the user exiting the test
    # This is only enabled once the function tests have passed
    def exit_handler(self, _pin):
        # The test has passed so we can clear the flag.
        self.clear_flag()

        # Time to sleep now!
        # This mode disables all front buttons to stop the unit waking in transit.
        powman.shipping_mode()

    def run(self):

        try:

            self.test_charge_stat()

            # We want to check we can toggle the SW_POWER_EN pin.
            # We're going to do it here before the rest of test starts
            power.off()
            if power.value():
                # Not that you'd see this error with no LED power xD
                raise Exception("E8")

            power.on()
            if not power.value():
                raise Exception("E8")

            self.test_psram()

            # Set the timers for the RTC test
            self.rtc.set_timer(2)
            self.rtc_timer.init(mode=Timer.ONE_SHOT, period=2100, callback=self.test_rtc)

            # If the pin for RTC alarm is already low, there's a problem.
            if rtc_alarm.value() == 0:
                raise Exception("E3")

            # If the pin for VBUS DETECT is already low, there's a problem.
            if vbus_detect.value() == 0:
                raise Exception("E6")

            self.test_wireless()

            if not self.vbus_pass:
                self.test_vbus()

            if self.rtc_pass is False:
                raise Exception("E4")

            self.test_light()

            button_timeout = time.time()
            while True:
                if time.time() - button_timeout > 10:
                    raise Exception("E11")

                self.test_buttons()

                # Home button can't interrupt so we check it here.
                if not int(home.value()):
                    self.buttons["HOME"][0] = True

                if self.buttons_pass:
                    break

                self.draw()

        except Exception as e:   # noqa BLE001
            print(e)
            while True:
                self.display_error(e)
                time.sleep(0.1)

        badge.poll()

        # The test has passed now, we'll just stay here a while.
        while True:
            badge.poll()
            screen.pen = DARK_GREEN
            screen.clear()
            screen.pen = WHITE
            t = "Pass!"
            tw, _ = screen.measure_text(t)
            screen.text(t, 80 - (tw / 2), 5)
            text_lines = wrap_and_measure(screen, "Press B to sleep", TEXT_SIZE - 1, 150)
            y = 40
            for line, _width in text_lines:
                screen.text(line, 5, y, TEXT_SIZE - 1)
                y += 22
            display.update()

            if badge.pressed(BUTTON_B):
                # Now the test has complete, we can remove the flag.
                try:
                    os.remove("hardware_test.txt")
                except OSError as e:
                    print(e)
                powman.shipping_mode()


    # Interrupt based button testing checks the button gpio
    # and that each button is able to trigger sw_int
    def btn_handler(self, _pin):
        if not int(a.value()):
            self.buttons["A"][0] = True

        if not int(b.value()):
            self.buttons["B"][0] = True

        if not int(c.value()):
            self.buttons["C"][0] = True

        if not int(up.value()):
            self.buttons["UP"][0] = True

        if not int(down.value()):
            self.buttons["DOWN"][0] = True

    def test_rtc(self, _t):
        # By the time this handler is used
        # the RTC alarm should have triggered
        self.rtc_pass = not rtc_alarm.value()
        self.rtc_timer.deinit()

    def test_vbus(self):
        start_time = time.time()

        while True:
            screen.pen = DARK_BLUE
            screen.clear()
            screen.pen = WHITE
            text_lines = wrap_and_measure(screen, "< Remove USB to continue.", TEXT_SIZE, 150)
            y = 40
            for line, _width in text_lines:
                screen.text(line, 5, y, TEXT_SIZE)
                y += 15
            display.update()
            # Time out to catch the user not removing the USB
            # Or to end the test if there's a failure on VBUS_DETECT
            if time.time() - start_time < 5:
                # We're checking status of the USB connection here.
                # If it changes we're going to assume the user removed it.
                if vbus_detect.value() == 0:
                    self.test_vbat()
                    self.vbus_pass = True
                    # little sleep here so we can read the charge status
                    time.sleep(0.2)
                    break
            else:
                raise Exception("E5")

    def draw(self):
        # Clear screen and display title
        screen.pen = DARK_BLUE
        screen.clear()
        screen.pen = WHITE

        text_lines = wrap_and_measure(screen, "Press all face buttons + HOME", TEXT_SIZE, 150)
        y = 25
        for line, _width in text_lines:
            screen.text(line, 5, y)
            y += 20

        # Draw button presses
        for button in sorted(self.buttons):
            pressed = self.buttons[button][0]
            if not pressed:
                x, y = self.buttons[button][1]
                screen.shape(shape.rounded_rectangle(x, y, 10, 10, 3))

        display.update()


t = Tests()
t.run()
