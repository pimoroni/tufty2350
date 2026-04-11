import sys
import os
import math

sys.path.insert(0, "/system/apps/badge")
os.chdir("/system/apps/badge")


CX = screen.width / 2
CY = screen.height / 2

screen.antialias = screen.X2

# details to be shown on the card
id_photo = image.load("avatar-squirrel.png")
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
lightness = 255
hue = 255
chroma = 0
background = color.oklch(lightness, chroma, hue)
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


def change_background(l = None, c = None, h = None):
    # a little helper to change the background color
    global background, lightness, chroma, hue

    changed = False

    if l:
        lightness += l
        lightness %= 255
        changed = True

    if c:
        chroma += c
        chroma = clamp(chroma, 0, 255)
        changed = True

    if h:
        hue += h
        hue %= 255
        changed = True

    if changed:
        background = color.oklch(lightness, chroma, hue)


def update():
    global flip, flip_start, rear_view, background, b_pressed

    # unpack the x and y for the card
    x, y = card_pos

    width = 1

    # clear the screen
    screen.pen = background
    screen.clear()

    # ripple effect
    draw_background()

    if badge.pressed (BUTTON_B):
        # If any other button is also pressed, the B button will be used as a
        # modifier.
        if not badge.held (BUTTON_UP) and not badge.held (BUTTON_DOWN) and \
           not badge.held (BUTTON_A)  and not badge.held (BUTTON_C):
            b_pressed = badge.ticks

    if badge.held (BUTTON_B):
        if b_pressed is not None:
            # If any other button is also pressed, we will use it as a
            # modifier.
            if badge.held (BUTTON_UP) or badge.held (BUTTON_DOWN) or \
               badge.held (BUTTON_A)  or badge.held (BUTTON_C):
                b_pressed = None

    if badge.released (BUTTON_B):
        # Once the B button is released, flip the badge, unless the button has
        # been used as a modifier for a different button.
        if b_pressed is not None:
            flip = True
            flip_start = badge.ticks
            rear_view = not rear_view

            b_pressed = None

    if badge.held (BUTTON_UP):
        if badge.held (BUTTON_B):
            change_background (l = -5)
        else:
            change_background (h = -5)

    if badge.held (BUTTON_DOWN):
        if badge.held (BUTTON_B):
            change_background (l = 5)
        else:
            change_background (h = 5)

    if badge.held (BUTTON_C):
        if badge.held (BUTTON_B):
            # Do nothing, this would be a modifier, but we currently do not
            # use it.
            pass
        else:
            change_background (c = 5)

    if badge.held (BUTTON_A):
        if badge.held (BUTTON_B):
            # Do nothing, this would be a modifier, but we currently do not
            # use it.
            pass
        else:
            change_background (c =- 5)

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
            for account in id_socials.items():
                screen.font = large_font
                y_offset = 1
                screen.pen = color.rgb(100, 100, 100)
                screen.shape(shape.rounded_rectangle(20, socials_y, 17, 17, 3))
                screen.blit(account[1]["icon"], vec2(20, socials_y))
                if 15 <= len (account[1]["handle"]):
                    screen.font = small_font
                    y_offset = 2
                shadow_text(account[1]["handle"], 40, socials_y + y_offset)
                socials_y += 21


def on_exit():
    pass


run(update)
