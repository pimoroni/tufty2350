import struct

from micropython import const
from machine import I2C

__version__ = "0.0.1"

# Constants
NUM_LEDS = const(4)
NUM_BUTTONS = const(10)

DEFAULT_ADDRESS = const(0x21)
ALT_ADDRESS_1 = const(0x23)
ALT_ADDRESS_2 = const(0x25)
ALT_ADDRESS_3 = const(0x27)
ADDRESSES = (DEFAULT_ADDRESS, ALT_ADDRESS_1, ALT_ADDRESS_2, ALT_ADDRESS_3)


class QwSTPad:
    # Registers
    INPUT_PORT0 = const(0x00)
    INPUT_PORT1 = const(0x01)
    OUTPUT_PORT0 = const(0x02)
    OUTPUT_PORT1 = const(0x03)
    POLARITY_PORT0 = const(0x04)
    POLARITY_PORT1 = const(0x05)
    CONFIGURATION_PORT0 = const(0x06)
    CONFIGURATION_PORT1 = const(0x07)

    BUTTON_A = 0xE
    BUTTON_B = 0xC
    BUTTON_X = 0xF
    BUTTON_Y = 0xD
    BUTTON_UP = 0x1
    BUTTON_DOWN = 0x4
    BUTTON_LEFT = 0x2
    BUTTON_RIGHT = 0x3
    BUTTON_PLUS = 0xB
    BUTTON_MINUS = 0x5

    # Mappings
    BUTTON_MAPPING = {"A": 0xE, "B": 0xC, "X": 0xF, "Y": 0xD,
                      "U": 0x1, "D": 0x4, "L": 0x2, "R": 0x3,
                      "+": 0xB, "-": 0x5}
    LED_MAPPING = (0x6, 0x7, 0x9, 0xA)

    def __init__(self, i2c=None, address=DEFAULT_ADDRESS, show_address=True):
        if address not in ADDRESSES:
            raise ValueError("address is not valid. Expected: 0x21, 0x23, 0x25, or 0x27")

        self.__i2c = i2c or I2C()
        self.__address = address

        # Set up the TCA9555 with the correct input and output pins
        self.__reg_write_uint16(self.__i2c, self.__address, self.CONFIGURATION_PORT0, 0b11111001_00111111)
        self.__reg_write_uint16(self.__i2c, self.__address, self.POLARITY_PORT0, 0b11111000_00111111)
        self.__reg_write_uint16(self.__i2c, self.__address, self.OUTPUT_PORT0, 0b00000110_11000000)

        self.__led_states = 0b0000
        if show_address:
            self.set_leds(self.address_code())

        self.__button_mask = 0
        for _, value in QwSTPad.BUTTON_MAPPING.items():
            self.__button_mask |= 1 << value

        self.buttons = self.read_buttons()
        self.__pressed = 0
        self.__released = 0
        self.__changed = 0
        self.__held = 0
        self.update_buttons()

    def address_code(self):
        return self.__change_bit(0x0000, ADDRESSES.index(self.__address), True)

    def read_buttons(self):
        return self.__reg_read_uint16(self.__i2c, self.__address, self.INPUT_PORT0) & self.__button_mask

    def set_leds(self, states):
        self.__led_states = states & 0b1111
        self.__update_leds()

    def set_led(self, led, state):
        if led < 1 or led > NUM_LEDS:
            raise ValueError("'led' out of range. Expected 1 to 4")

        self.__led_states = self.__change_bit(self.__led_states, led - 1, state)
        self.__update_leds()

    def clear_leds(self):
        self.__led_states = 0b0000
        self.__update_leds()

    def __update_leds(self):
        output = 0
        for i in range(NUM_LEDS):
            output = self.__change_bit(output, self.LED_MAPPING[i], not self.__get_bit(self.__led_states, i))
        self.__reg_write_uint16(self.__i2c, self.__address, self.OUTPUT_PORT0, output)

    def __get_bit(self, num, bit_pos):
        return (num & (1 << bit_pos)) != 0

    def __change_bit(self, num, bit_pos, state):
        return num | (1 << bit_pos) if state else num & ~(1 << bit_pos)

    def __reg_write_uint16(self, i2c, address, reg, value):
        buffer = struct.pack("<H", value)
        i2c.writeto_mem(address, reg, buffer)

    def __reg_read_uint16(self, i2c, address, reg):
        buffer = i2c.readfrom_mem(address, reg, 2)
        return struct.unpack("<H", buffer)[0]

    def update_buttons(self):
        old_values = self.buttons

        self.buttons = self.read_buttons()

        self.__changed = ~(old_values & self.buttons)
        self.__pressed = self.buttons & self.__changed
        self.__released = ~self.buttons & self.__changed
        self.__held = self.buttons

    def pressed(self, button=None):
        if button is None:
            return self.__pressed > 0
        return self.__pressed & (1 << QwSTPad.BUTTON_MAPPING[button])

    def released(self, button=None):
        if button is None:
            return self.__released > 0
        return self.__released & (1 << QwSTPad.BUTTON_MAPPING[button])

    def changed(self, button=None):
        if button is None:
            return self.__changed > 0
        return self.__changed & (1 << QwSTPad.BUTTON_MAPPING[button])

    def held(self, button=None):
        if button is None:
            return self.__held > 0
        return self.__held & (1 << QwSTPad.BUTTON_MAPPING[button])


class Gamepadhelper:
    def __init__(self, i2c=None):
        self.pads = []
        self.pads_count = 0
        self.__i2c = i2c
        self.get_gamepads()

    def get_gamepads(self):
        pads_count = 0

        # Create a player for each connected QwSTPad
        for i, addr in enumerate(ADDRESSES):
            try:
                self.pads.append(QwSTPad(self.__i2c, addr))
                print(f"P{i + 1}: Connected")
                pads_count += 1
            except OSError:
                self.pads.append(None)
                print(f"P{i + 1}: Not Connected")

        self.pads_count = pads_count

    def monkeypatch(self, gamepad):
        self.get_gamepads()
        _pad = self.pads[gamepad]
        if _pad is None:
            raise RuntimeError(f"Gamepad {gamepad} is not connected!")

        def _remap(button):
            return {
                BUTTON_A: "L",
                BUTTON_B: "B",
                BUTTON_C: "R",
                BUTTON_UP: "U",
                BUTTON_DOWN: "D",
            }[button]

        _badge_pressed = badge.pressed
        _badge_held = badge.held
        _badge_released = badge.released
        _badge_changed = badge.changed
        _badge_poll = badge.poll

        def _pressed(button=None):
            return _badge_pressed(button) or _pad.pressed(_remap(button))

        def _held(button=None):
            return _badge_held(button) or _pad.held(_remap(button))

        def _released(button=None):
            return _badge_released(button) or _pad.released(_remap(button))

        def _changed(button=None):
            return _badge_changed(button) or _pad.changed(_remap(button))

        def _poll():
            _badge_poll()
            _pad.update_buttons()

        badge.pressed = _pressed
        badge.held = _held
        badge.released = _released
        badge.changed = _changed
        badge.poll = _poll
