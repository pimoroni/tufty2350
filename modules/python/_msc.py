import fatbridge
import random


# Disarm the home button to help mitigate unwanted resets in MSC mode
BUTTON_HOME.irq(None)


# Present the badge's littlefs storage to the host as a (synthesised) FAT drive.
# service() (each frame) commits host writes to littlefs and, when the disk is
# ejected, drains the cache and reboots the badge back to normal mode.
fatbridge.expose()

# fatbridge.service() status codes:
IDLE, READING, WRITING, COMMITTING, DONE = 0, 1, 2, 3, 4

# Base RGB for the activity colours (alpha applied per-star).
READ_RGB = (255, 176, 64)    # amber - data flowing OUT of the badge (host reads)
WRITE_RGB = (72, 200, 255)   # cyan  - data flowing IN to the badge (host writes)
IDLE_RGB = (255, 255, 255)
WARN_RGB = (255, 96, 64)     # ejected / committing
OK_RGB = (96, 220, 120)      # done

background = color.black
white = color.white
faded = color.rgb(235, 245, 255, 200)

try:
    small_font = rom_font.ark
    large_font = rom_font.absolute
except OSError:
    small_font = None
    large_font = None


def center_text(text, y):
    w, h = screen.measure_text(text)
    screen.text(text, 80 - (w / 2), y)


def wrap_text(text, x, y):
    for line in text.splitlines():
        _, h = screen.measure_text(line)
        screen.text(line, x, y)
        y += h * 0.8


class DiskMode():
    def __init__(self):
        self.stars = [[random.uniform(-80, 80), random.uniform(-60, 60), 0] for _ in range(400)]

    def _respawn(self, star, inward):
        if inward:  # spawn at a random edge, streak toward the centre
            if random.getrandbits(1):
                star[0] = random.choice((-80.0, 80.0))
                star[1] = random.uniform(-60, 60)
            else:
                star[0] = random.uniform(-80, 80)
                star[1] = random.choice((-60.0, 60.0))
        else:       # spawn near the centre, streak outward
            star[0] = random.uniform(-3, 3)
            star[1] = random.uniform(-3, 3)
        star[2] = 0

    def update(self, state):
        inward = state == WRITING
        active = state in (READING, WRITING)
        rate = badge.ticks_delta / (260 if active else 1100)  # faster during a transfer
        for s in self.stars:
            if inward:
                s[0] /= (1 + rate)
                s[1] /= (1 + rate)
                if abs(s[0]) < 2 and abs(s[1]) < 2:
                    self._respawn(s, True)
            else:
                s[0] *= (1 + rate)
                s[1] *= (1 + rate)
                if abs(s[0]) > 80 or abs(s[1]) > 60:
                    self._respawn(s, False)
            s[2] += 1

    def draw_stars(self, state):
        if state == READING:
            (r, g, b), bright = READ_RGB, 255
        elif state == WRITING:
            (r, g, b), bright = WRITE_RGB, 255
        else:
            (r, g, b), bright = IDLE_RGB, 110
        self.update(state)
        rect = shape.rectangle(0, 0, 1, 1)
        for s in self.stars:
            if int(s[0]) != 0 and int(s[1]) != 0:
                age = min(1, s[2] / 40)
                screen.pen = color.rgb(r, g, b, age * bright)
                rect.transform = mat3().translate(s[0], s[1]).translate(80, 60)
                screen.shape(rect)

    def draw(self, state):
        screen.pen = background
        screen.shape(shape.rectangle(0, 0, 160, 120))

        if state in (COMMITTING, DONE):
            self.draw_commit(state)
            return

        self.draw_stars(state)

        if large_font:
            screen.font = large_font
            screen.pen = white
            center_text("USB Disk Mode", 5)
            screen.text("1:", 10, 23)
            screen.text("2:", 10, 45)
            screen.text("3:", 10, 67)

            screen.font = small_font
            if state == READING:
                screen.pen = color.rgb(*READ_RGB)
            elif state == WRITING:
                screen.pen = color.rgb(*WRITE_RGB)
            else:
                screen.pen = faded
            wrap_text("Your badge is now\nmounted as a disk", 30, 24)
            wrap_text("Copy code onto\nit to experiment!", 30, 46)
            wrap_text("Eject the disk to\nreboot your badge", 30, 68)

            if state == WRITING:
                screen.pen = color.rgb(*WRITE_RGB)
                center_text("Receiving data...", 102)
            elif state == READING:
                screen.pen = color.rgb(*READ_RGB)
                center_text("Sending data...", 102)
            else:
                screen.pen = faded
                center_text("Waiting for data", 102)

    def draw_commit(self, state):
        accent = color.rgb(*(WARN_RGB if state == COMMITTING else OK_RGB))
        if large_font:
            screen.font = large_font
            screen.pen = accent
            center_text("Saving to badge", 16)
        if small_font:
            screen.font = small_font
            screen.pen = faded
            wrap_text("Disk ejected -\ndo NOT unplug!" if state == COMMITTING
                      else "All saved.\nRebooting...", 32, 38)

        p = 1.0 if state == DONE else fatbridge.commit_progress()
        bx, by, bw, bh = 24, 86, 112, 12
        screen.pen = color.rgb(60, 70, 80)
        screen.shape(shape.rectangle(bx, by, bw, bh))
        screen.pen = accent
        screen.shape(shape.rectangle(bx, by, max(1, int(bw * p)), bh))
        if small_font:
            screen.font = small_font
            screen.pen = white
            center_text("{}%".format(int(p * 100)), 100)


disk_mode = DiskMode()


def update():
    state = fatbridge.service()   # drives USB + commits; reboots on eject when done
    badge.caselights(1 if state in (READING, WRITING, COMMITTING) else 0)
    disk_mode.draw(state)


run(update)
