import os
import math
import random

import svg

import ui

ICON_DIR = "assets/icons"
ICON_SIZE = 34

# The Arm icons are shared out across the apps at random for now, so each is
# parsed and rasterised once and the sprite handed to whichever apps draw it.
# Rasterising into a square box letterboxes each icon rather than stretching
# it — the viewBoxes range from 53x32 to 72x72.
ICONS = [
    svg.load(f"{ICON_DIR}/{name}").rasterize(ICON_SIZE, ICON_SIZE)
    for name in sorted(os.listdir(ICON_DIR)) if name.endswith(".svg")
]

# Apps carry no description of their own unless the module opens with a
# docstring, so anything without one falls back to this.
FALLBACK_DESCRIPTION = "No description provided by this app."

# Proportions follow the site's cards: much wider than tall, a small icon at
# roughly an eighth of the card width, and a text column taking the rest. The
# card is narrow enough to leave a healthy slice of its neighbours showing.
CARD_W, CARD_H = 232, 104
CARD_RADIUS = 14
CARD_GAP = 12
CARD_PITCH = CARD_W + CARD_GAP
CARD_TOP = 78
OUTLINE = 1.5
PADDING_X = 14
PADDING_Y = 13
ICON_GAP = 14

TITLE_SIZE = 16
TITLE_LEADING = 3
DESC_SIZE = 11
DESC_LEADING = 2
BLOCK_GAP = 5

# the band the carousel is clipped to, keeping cards clear of the header
BAND_TOP = 62
BAND_HEIGHT = 136

# how quickly the carousel catches up to the selected card, in milliseconds
SCROLL_SETTLE = 90

# Card geometry is built once at the origin and each card's position comes from
# the shape's transform.
#
# stroke() consumes the shape it is called on, so the outline is taken from its
# own instance; sharing one would leave the fill drawing nothing. A positive
# thickness insets the stroke, keeping the card exactly CARD_W across.
card = shape.rounded_rectangle(-CARD_W / 2, -CARD_H / 2, CARD_W, CARD_H, CARD_RADIUS)
outline = shape.rounded_rectangle(
    -CARD_W / 2, -CARD_H / 2, CARD_W, CARD_H, CARD_RADIUS
).stroke(OUTLINE)

# State lives in the border and title colour; the panel stays black either way.
# The idle border sits well back from the selected one — just enough to read as
# an edge against black.
idle_outline = color.rgb(14, 38, 62)
body_text = color.rgb(201, 203, 206)


def read_description(path):
    """The app's module docstring, if it opens with one."""
    try:
        with open(f"{path}/__init__.py", "r") as handle:
            head = handle.read(600)
    except OSError:
        return FALLBACK_DESCRIPTION

    head = head.lstrip()
    for quote in ('"""', "'''"):
        if head.startswith(quote):
            end = head.find(quote, 3)
            if end > 0:
                return " ".join(head[3:end].split())
    return FALLBACK_DESCRIPTION


def wrap(text, size, width):
    """Break text into lines that fit within width."""
    lines = []
    line = ""
    for word in text.split():
        candidate = word if not line else line + " " + word
        if not line or screen.measure_text(candidate, size)[0] <= width:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


class App:
    def __init__(self, collection, name, path):
        self.active = False
        self.index = len(collection)
        self.icon = random.choice(ICONS)
        self.name = name
        self.path = path
        self.description = read_description(path)
        self.lines = None       # wrapped lazily, once the font is set

        collection.append(self)

    def activate(self, active):
        self.active = active

    def layout(self, width):
        title = wrap(self.name, TITLE_SIZE, width)
        body = wrap(self.description, DESC_SIZE, width)

        # keep the card from overflowing when an app is especially wordy
        room = CARD_H - 2 * PADDING_Y
        used = len(title) * (TITLE_SIZE + TITLE_LEADING) + BLOCK_GAP
        allowed = max(1, int((room - used) // (DESC_SIZE + DESC_LEADING)))
        if len(body) > allowed:
            body = body[:allowed]
            body[-1] = body[-1] + "..."

        self.lines = (title, body)
        return self.lines

    def draw(self, scroll):
        cx = ui.WIDTH / 2 + self.index * CARD_PITCH - scroll
        if cx + CARD_W / 2 < 0 or cx - CARD_W / 2 > ui.WIDTH:
            return

        cy = CARD_TOP + CARD_H / 2
        transform = mat3().translate(cx, cy)
        card.transform = transform
        outline.transform = transform

        screen.pen = ui.black
        screen.shape(card)
        screen.pen = ui.green if self.active else idle_outline
        screen.shape(outline)

        text_x = cx - CARD_W / 2 + PADDING_X + ICON_SIZE + ICON_GAP
        text_width = (cx + CARD_W / 2 - PADDING_X) - text_x

        title, body = self.lines or self.layout(text_width)

        # every card hangs its content from the top, so a short description
        # leaves the slack at the bottom rather than recentring the block
        y = CARD_TOP + PADDING_Y

        screen.blit(
            self.icon,
            rect(cx - CARD_W / 2 + PADDING_X, y, self.icon.width, self.icon.height),
        )

        screen.pen = ui.green if self.active else ui.cyan
        for line in title:
            screen.text(line, text_x, y, TITLE_SIZE)
            y += TITLE_SIZE + TITLE_LEADING

        y += BLOCK_GAP
        screen.pen = body_text
        for line in body:
            screen.text(line, text_x, y, DESC_SIZE)
            y += DESC_SIZE + DESC_LEADING


class Apps:
    def __init__(self, root):
        self.apps = []
        self.active_index = 0
        self.scroll = 0.0

        def capitalize(word):
            if len(word) <= 1:
                return word
            return word[0].upper() + word[1:]

        for path in sorted(os.listdir(root)):
            name = " ".join([capitalize(word) for word in path.split("_")])

            if is_dir(f"{root}/{path}"):
                if path != "menu" and (file_exists(f"{root}/{path}/__init__.py") or file_exists(f"{root}/{path}/__init__.mpy")):
                    App(self.apps, name, f"{root}/{path}")

    @property
    def active(self):
        return self.apps[self.active_index]

    def activate(self, index):
        self.active_index = index
        for app in self.apps:
            app.activate(app.index == index)

    def draw_cards(self):
        # slide the selected card to the middle, easing rather than jumping
        target = self.active_index * CARD_PITCH
        step = min(1.0, badge.ticks_delta / SCROLL_SETTLE)
        self.scroll += (target - self.scroll) * step
        if abs(target - self.scroll) < 0.5:
            self.scroll = target

        previous = screen.clip
        screen.clip = rect(0, BAND_TOP, ui.WIDTH, BAND_HEIGHT)
        for app in self.apps:
            app.draw(self.scroll)
        screen.clip = previous

    def draw_progress(self, y=222, height=3):
        """How far through the carousel we are."""
        if len(self.apps) < 2:
            return

        track = ui.WIDTH - 2 * PADDING_X
        width = max(20, track / len(self.apps))
        offset = (track - width) * (self.scroll / ((len(self.apps) - 1) * CARD_PITCH))

        screen.pen = color.rgb(24, 44, 66)
        screen.shape(shape.rounded_rectangle(PADDING_X, y, track, height, height / 2))
        screen.pen = ui.green
        screen.shape(shape.rounded_rectangle(PADDING_X + offset, y, width, height, height / 2))

    def __len__(self):
        return len(self.apps)

    def __getitem__(self, i):
        return self.apps[i]
