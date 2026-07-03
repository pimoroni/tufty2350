import fatlfs
import math


# Disarm the home button to help mitigate unwanted resets in MSC mode
BUTTON_HOME.irq(None)

# Hi-res (320x240) - roomier layout for the gauges.
badge.mode(HIRES)
W, H = screen.width, screen.height


# Present the badge's littlefs storage to the host as a FAT32 drive. service()
# (each frame) drives USB and relieves RAM pressure; when the disk is ejected it
# commits every staged write to littlefs and reboots the badge to normal mode.
fatlfs.expose()

# fatlfs.service() status codes:
IDLE, READING, WRITING, COMMITTING, DONE, ERROR = 0, 1, 2, 3, 4, 5

COLOR_READ = color.rgb(255, 176, 64)    # data flowing OUT of the badge (host reads)
COLOR_WRITE = color.rgb(96, 200, 255)   # data flowing IN to the badge (host writes)
COLOR_IDLE = color.rgb(110, 128, 148)
COLOR_WARN = color.rgb(255, 96, 64)
COLOR_OK = color.rgb(96, 220, 120)
COLOR_ERROR = color.rgb(255, 48, 48)

COLOR_MEM = color.rgb(255, 168, 64)      # RAM staging (host writes not yet on flash)
COLOR_DISK = color.rgb(96, 158, 224)     # real littlefs usage

background = color.black
white = color.white
faded = color.rgb(210, 224, 240)
label_col = color.rgb(150, 168, 188)

try:
    small_font = rom_font.ark
    large_font = rom_font.absolute
except OSError:
    small_font = None
    large_font = None

# Left/right margins for the gauges.
GX = 12
GRIGHT = W - 12
# USB direction indicator
USB_CX, USB_CY = W // 2, 160

BAR_TRACK = color.rgb(40, 46, 56)


def center_text(text, y, cx=W // 2):
    w, _ = screen.measure_text(text)
    screen.text(text, cx - (w / 2), y)


def fmt_mb(n):
    return "{:.1f}MB".format(n / (1024 * 1024))


class DiskMode():
    def draw_usb(self, state):
        # A single arrow by the USB port: IDLE (dim plug) / READ (out) / WRITE (in).
        pulse = int(150 + 90 * math.sin(badge.ticks / 180))
        if state == WRITING:
            screen.alpha = pulse
            self.draw_arrow(1, COLOR_WRITE)
            cap = "Receiving"
        elif state == READING:
            screen.alpha = pulse
            self.draw_arrow(-1, COLOR_READ)
            cap = "Sending"
        else:
            screen.alpha = 255
            screen.pen = COLOR_IDLE
            cap = "Idle"
        if small_font:
            screen.font = small_font
            center_text(cap, USB_CY + 12, USB_CX)
        screen.alpha = 255

    def draw_arrow(self, direction, col):
        cx, cy, s = USB_CX, USB_CY, 11
        screen.pen = col
        screen.rectangle(cx - s, cy - 2, s * 2 + 1, 4)
        tip = cx + s * direction
        screen.triangle(tip, cy - 8, tip + direction * 8, cy, tip, cy + 8)

    def draw_bar(self, y, label, used, total, col):
        frac = 0 if total == 0 else used / total
        if frac > 1.0:
            frac = 1.0
        if small_font:
            screen.font = small_font
        screen.pen = label_col
        screen.text(label, GX, y - 1)
        lw, _ = screen.measure_text("Storage")  # slight hack to line the bars up
        bx = GX + lw + 8
        pct = "{} / {}".format(fmt_mb(used), fmt_mb(total))
        pw, _ = screen.measure_text(pct)
        bw = GRIGHT - pw - 6 - bx
        bh = 9
        screen.pen = BAR_TRACK
        screen.rectangle(bx, y, bw, bh)
        screen.pen = col
        screen.rectangle(bx, y, max(1, int(bw * frac)), bh)
        screen.pen = faded
        screen.text(pct, GRIGHT - pw, y - 1)

    def draw(self, state):
        # badge.clear() already wipes the screen each frame; no full-screen fill.
        if state in (COMMITTING, DONE, ERROR):
            self.draw_commit(state)
            return

        if large_font:
            screen.font = large_font
            screen.pen = white
            center_text("USB Disk Mode", 6)

        if small_font:
            screen.font = small_font
            screen.pen = faded
            screen.text("1: Your badge is mounted", 8, 30, 2)
            screen.text("as a USB disk", 34, 48, 2)

            screen.text("2: Copy code onto it", 8, 70, 2)
            screen.text("to experiment!", 34, 88, 2)

            screen.text("3: Eject the disk to", 8, 110, 2)
            screen.text("reboot your badge", 34, 128, 2)

        self.draw_usb(state)
        # RAM staging: how much of a copy is buffered but not yet flushed. It fills
        # as the host writes and empties once committed at eject.
        staged, cap = fatlfs.mem_usage()
        self.draw_bar(H - 44, "Buffer", staged, cap, COLOR_MEM)
        # Real littlefs usage - how full the badge actually is.
        used, total = fatlfs.disk_usage()
        self.draw_bar(H - 22, "Storage", used, total, COLOR_DISK)

    def draw_commit(self, state):
        if state == COMMITTING:
            accent = COLOR_WARN
            title, caption = "Saving to badge", "Disk ejected - do NOT unplug!"
        elif state == ERROR:
            accent = COLOR_ERROR
            title, caption = "Save FAILED", "Badge disk may be full. Rebooting..."
        else:
            accent = COLOR_OK
            title, caption = "Saving to badge", "All saved. Rebooting..."
        if large_font:
            screen.font = large_font
            screen.pen = accent
            center_text(title, 60)
        if small_font:
            screen.font = small_font
            screen.pen = faded
            center_text(caption, 92)

        bw, bh = 220, 16
        bx = (W - bw) // 2
        by = 130
        screen.pen = BAR_TRACK
        screen.rectangle(bx, by, bw, bh)
        screen.pen = accent
        if state in (DONE, ERROR):
            screen.rectangle(bx, by, bw, bh)
        else:
            # Indeterminate sweep - the commit is a single atomic flush.
            sw = 60
            sx = bx + int((math.sin(badge.ticks / 200) * 0.5 + 0.5) * (bw - sw))
            screen.rectangle(sx, by, sw, bh)


disk_mode = DiskMode()


# Custom loop instead of run(): service() (USB + pressure relief) is pumped EVERY
# iteration, but the heavy hi-res draw + display.update() only run every few
# iterations. Per-frame drawing would starve the USB task and stall copies; this
# keeps the USB duty cycle high while still refreshing the screen ~10 fps.
DRAW_EVERY = 8


def main_loop():
    frame = 0
    while True:
        state = fatlfs.service()   # drives USB + commits; reboots on eject
        badge.caselights(1 if state in (READING, WRITING, COMMITTING) else 0)
        frame += 1
        if state in (COMMITTING, DONE, ERROR) or frame % DRAW_EVERY == 0:
            disk_mode.draw(state)
            badge.update()


main_loop()
