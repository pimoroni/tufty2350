import sys
import os
import math

sys.path.insert(0, "/system/apps/badge")
os.chdir("/system/apps/badge")


CX = screen.width / 2
CY = screen.height / 2

screen.antialias = screen.X2

# details to be shown on the card
id_photo = image.load("avatar.png")
id_name = "Your Name"
id_role = "Job title"

# see the 'assets/social' folder to see what's supported
id_socials = {"bluesky": {"icon": None, "handle": ""},
              "instagram": {"icon": None, "handle": ""},
              "github": {"icon": None, "handle": ""},
              "discord": {"icon": None, "handle": ""}
              }

# load in the social icons
for key in id_socials.keys():
    id_socials[key]["icon"] = image.load(f"assets/socials/{key}.png")

# id card variables
id_body = shape.rounded_rectangle(0, 0, 140, 100, 7)
id_outline = shape.rounded_rectangle(0, 0, 140, 100, 7).stroke(2)
hue = 255
chroma = 0
background = color.rgb(255, 255, 255)
flip = False
flip_start = 0
rear_view = False
card_pos = (10, 10)

small_font = pixel_font.load("/system/assets/fonts/winds.ppf")
large_font = pixel_font.load("/system/assets/fonts/nope.ppf")


def draw_background():
    # ripple effect background
    cy = CY - 8
    cx = CX

    y = 0
    for _row in range(12):
        x = 0
        for _col in range(16):
            dist = math.sqrt((x + 5 - cx) ** 2 + (y + 5 - cy) ** 2)
            pulse = (math.sin(-badge.ticks / 400 + (dist / 6)) / 2) + 0.5
            pulse = 0.8 + (pulse / 2)
            screen.pen = color.rgb(0, 0, 0, 100 * pulse)
            screen.rectangle(x, y, 10, 10)
            x += 10
        y += 10


def shadow_text(text, x, y):
    screen.pen = color.rgb(20, 40, 60, 100)
    screen.text(text, x + 1, y + 1)
    screen.pen = color.rgb(0, 0, 0)
    screen.text(text, x, y)


def center_text(text, y):
    w, _ = screen.measure_text(text)
    shadow_text(text, (screen.width / 2) - (w / 2), y)


def init():
    pass


def change_background(h=None, c=None):
    # a little helper to change the background color
    global background, hue, chroma

    if h:
        hue += h
        hue = hue % 255
        background = color.oklch(255, chroma, hue)

    if c:
        chroma += c
        chroma = clamp(chroma, 0, 255)
        background = color.oklch(255, chroma, hue)


def update():
    global flip, flip_start, rear_view, background_hue, background

    # unpack the x and y for the card
    x, y = card_pos

    width = 1

    # clear the screen
    screen.pen = background
    screen.clear()

    # ripple effect
    draw_background()

    if badge.pressed(BUTTON_B):
        flip = True
        flip_start = badge.ticks
        rear_view = not rear_view

    if badge.held(BUTTON_UP):
        change_background(h=5)

    if badge.held(BUTTON_DOWN):
        change_background(h=5)

    if badge.held(BUTTON_C):
        change_background(c=5)

    if badge.held(BUTTON_A):
        change_background(c=-5)

    if flip:
        # create a spin animation that runs over 100ms
        speed = 95
        frame = badge.ticks - flip_start

        # calculate the width of the tile during this part of the animation
        width = round(math.cos(frame / speed) * 3) / 3

        # ensure the width never reduces to zero or the icon disappears
        width = max(0.1, width) if width > 0 else min(-0.1, width)

        # once the animation has completed unset the spin flag
        if frame > (speed * 3):
            flip = False

    # draw the card
    id_body.transform = mat3().translate(CX, y).scale(width, 1)
    id_outline.transform = mat3().translate(CX, y).scale(width, 1)
    id_body.transform = id_body.transform.translate(-70, 0)
    id_outline.transform = id_outline.transform.translate(-70, 0)

    screen.pen = color.rgb(50, 50, 50, 100)
    id_body.transform = id_body.transform.translate(4, 4)
    screen.shape(id_body)

    screen.pen = color.rgb(255, 255, 255, 90)
    id_body.transform = id_body.transform.translate(-4, -4)
    screen.shape(id_body)
    screen.pen = color.rgb(0, 0, 0, 100)
    screen.shape(id_outline)

    photo_y = y + 15 + id_photo.height
    socials_y = 22

    if not flip:
        # Draw the card information
        screen.pen = color.rgb(0, 0, 0)
        if not rear_view:
            screen.font = large_font
            screen.blit(id_photo, vec2(CX - id_photo.width / 2, y + 10))
            center_text(id_name, photo_y)
            screen.font = small_font
            center_text(id_role, photo_y + 12)
        else:
            screen.font = large_font
            for account in id_socials.items():
                screen.pen = color.rgb(100, 100, 100)
                screen.shape(shape.rounded_rectangle(20, socials_y, 17, 17, 3))
                screen.blit(account[1]["icon"], vec2(20, socials_y))
                shadow_text(account[1]["handle"], 40, socials_y)
                socials_y += 21


def on_exit():
    pass


if __name__ == "__main__":
    run(update)
