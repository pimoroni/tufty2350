import rp2
import random

import binascii
import uctypes


# Get a CRC of the FAT (first 16k of the user filesystem) ~16ms
CACHE_FILE = "/.fsbackup"

fat = uctypes.bytearray_at(0x10300000, 16 * 1024)
crc = f"{binascii.crc32(fat):08x}"

try:
    cached_crc = open(f"{CACHE_FILE}.crc32", "r").read().strip()
except OSError:
    cached_crc = ""

if cached_crc != crc:
    with open(f"{CACHE_FILE}.crc32", "w") as f:
        f.write(crc)
        f.flush()
    with open(CACHE_FILE, "wb") as f:
        f.write(fat)
        f.flush()


rp2.enable_msc()

background = color.rgb(35, 41, 37)
phosphor = color.rgb(211, 250, 55, 150)
white = color.rgb(235, 245, 255)
faded = color.rgb(235, 245, 255, 200)

try:
    small_font = rom_font.ark
    large_font = rom_font.absolute
except OSError:
    small_font = None
    large_font = None

class DiskMode():
  def __init__(self):
    self.stars = []
    self.transferring = False
    for _ in range(500):
      self.stars.append((random.randint(-80, 80), random.randint(-60, 60), 0))

  def update(self):
    speed = 500 if self.transferring else 1000
    for i in range(len(self.stars)):
      star = self.stars[i]
      dx = star[0] * (badge.ticks_delta / speed)
      dy = star[1] * (badge.ticks_delta / speed)
      age = star[2] + 1
      star = (star[0] + dx, star[1] + dy, age)

      if star[0] < -80 or star[1] < -60 or star[0] > 80 or star[1] > 60:
        self.stars[i] = (random.randint(-80, 80), random.randint(-60, 60), 0)
      else:
        self.stars[i] = star

  def draw(self):
    screen.pen = background
    screen.shape(shape.rectangle(0, 0, 160, 120))

    self.update()

    rect = shape.rectangle(0, 0, 1, 1)
    for i in range(len(self.stars)):
      star = self.stars[i]
      age = min(1, star[2] / 50)

      brightness = 100
      if self.transferring:
        brightness = 255

      if int(star[0]) != 0 and int(star[1]) != 0:
        screen.pen = color.rgb(255, 255, 255, age * brightness)
        rect.transform = mat3().translate(star[0], star[1]).translate(80, 60)
        screen.shape(rect)

    if large_font:
        screen.font = large_font
        screen.pen = white
        center_text("USB Disk Mode", 5)

        screen.text("1:", 10, 23)
        screen.text("2:", 10, 45)
        screen.text("3:", 10, 67)

        screen.pen = phosphor
        screen.font = small_font
        wrap_text("""Your badge is now\nmounted as a disk""", 30, 24)

        wrap_text("""Copy code onto\nit to experiment!""", 30, 46)

        wrap_text("""Eject the disk to\nreboot your badge""", 30, 68)

        screen.font = small_font
        if self.transferring:
            screen.pen = white
            center_text("Transferring data!", 102)
        else:
            screen.pen = faded
            center_text("Waiting for data", 102)

def center_text(text, y):
  w, h = screen.measure_text(text)
  screen.text(text, 80 - (w / 2), y)

def wrap_text(text, x, y):
  lines = text.splitlines()
  for line in lines:
    _, h = screen.measure_text(line)
    screen.text(line, x, y)
    y += h * 0.8


disk_mode = DiskMode()

def update():
  # set transfer state here
  disk_mode.transferring = rp2.is_msc_busy()

  badge.set_caselights(int(disk_mode.transferring))

  # draw the ui
  disk_mode.draw()


run(update)
