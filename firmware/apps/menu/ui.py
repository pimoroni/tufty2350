import armmark

# Arm design system palette
black = color.rgb(0, 0, 0)
dark_blue = color.rgb(0, 43, 73)        # --arm-dark-blue
cyan = color.rgb(0, 193, 222)           # --arm-light-blue
green = color.rgb(149, 214, 0)          # the lime end of the icon gradients
blue = color.rgb(0, 145, 189)           # brand blue, Pantone 313 C
white = color.rgb(255, 255, 255)
muted = color.rgb(122, 142, 158)

WIDTH, HEIGHT = 320, 240
HEADER_HEIGHT = 40
WORDMARK_HEIGHT = 20
LOCKUP_SIZE = 18
LABEL_SIZE = 18

# The wordmark sits at a fixed spot in the header, so bake the position into the
# geometry once at import and reuse the shapes every frame.
wordmark, wordmark_counter = armmark.build(14, 11, WORDMARK_HEIGHT)
LOCKUP_X = 14 + armmark.width_for(WORDMARK_HEIGHT) + 10

# Dark washes over the black ground, standing in for the site's background
# gradients. Both are drawn only where they show, to keep the fill cost down.
wash_top = brush.gradient(
    brush.RADIAL, 40, 24, 0, 250,
    ((0.0, color.rgb(0, 66, 104, 80)), (1.0, color.rgb(0, 43, 73, 0)))
)
wash_bottom = brush.gradient(
    brush.RADIAL, 300, 236, 0, 210,
    ((0.0, color.rgb(0, 104, 132, 52)), (1.0, color.rgb(0, 43, 73, 0)))
)
# the nav rule fades out to the right rather than running edge to edge
rule = brush.gradient(
    brush.LINEAR, 0, 0, WIDTH, 0,
    ((0.0, color.rgb(0, 193, 222, 190)), (1.0, color.rgb(0, 193, 222, 0)))
)


def draw_background():
    screen.pen = black
    screen.clear()
    screen.pen = wash_top
    screen.rectangle(0, 0, WIDTH, 200)
    screen.pen = wash_bottom
    screen.rectangle(120, 80, 200, 160)


def draw_header():
    # The wordmark is drawn small enough that the curves need antialiasing to
    # hold their shape. screen.shapes() fills each subpath separately, so the
    # counter in the "a" is painted back in the ground colour.
    antialias = screen.antialias
    screen.antialias = image.X2
    screen.pen = white
    screen.shapes(wordmark)
    screen.pen = black
    screen.shapes(wordmark_counter)
    screen.antialias = antialias

    screen.pen = cyan
    screen.text("Developer", LOCKUP_X, 12, LOCKUP_SIZE)

    screen.pen = rule
    screen.rectangle(0, HEADER_HEIGHT - 1, WIDTH, 1)

    draw_battery()


def draw_battery():
    if badge.is_charging():
        level = (badge.ticks / 20) % 100
    else:
        level = badge.battery_level()

    pos = (274, 13)
    size = (32, 15)
    screen.pen = muted
    body = shape.rounded_rectangle(pos[0], pos[1], size[0], size[1], 3)
    screen.shape(body.stroke(-1))
    screen.shape(shape.rounded_rectangle(pos[0] + size[0], pos[1] + 4, 3, 7, 1))

    screen.pen = cyan
    width = ((size[0] - 6) / 100) * level
    screen.shape(shape.rounded_rectangle(pos[0] + 3, pos[1] + 3, width, size[1] - 6, 2))
