title_font = font.ark
label_font = font.sins

black = color.rgb(0, 0, 0)
background = color.rgb(16, 20, 32)
header = color.rgb(40, 50, 80)
highlight = color.rgb(80, 120, 220)
text = color.rgb(220, 230, 255)
dim = color.rgb(120, 130, 160)

TOP = 17
ROW_H = 25
ROWS = 4


def navigate(active, count):
    if badge.pressed(BUTTON_UP) and active > 0:
        active -= 1
    if badge.pressed(BUTTON_DOWN) and active < count - 1:
        active += 1
    return active


# cut at the last whole word that fits, or mid-word if even the first is too long
def shorten(name, width):
    if screen.measure_text(name)[0] <= width:
        return name
    words = name.split(" ")
    for n in range(len(words) - 1, 0, -1):
        label = " ".join(words[:n]) + "..."
        if screen.measure_text(label)[0] <= width:
            return label
    label = name
    while len(label) > 1 and screen.measure_text(label + "...")[0] > width:
        label = label[:-1]
    return label.rstrip() + "..."


def render(apps):
    count = len(apps)
    active = apps.active_index

    # black corners behind the rounded screen, as in the default theme
    screen.pen = black
    screen.rectangle(0, 0, 10, 10)
    screen.rectangle(150, 0, 10, 10)
    screen.rectangle(0, 110, 10, 10)
    screen.rectangle(150, 110, 10, 10)

    screen.pen = background
    screen.shape(shape.rounded_rectangle(0, 0, 160, 120, 8))

    # rounded along the top only
    screen.pen = header
    screen.shape(shape.rounded_rectangle(0, 0, 160, 15, 8))
    screen.rectangle(0, 8, 160, 7)
    screen.font = title_font
    screen.pen = text
    screen.text("Apps", 5, 2)

    # keep the active row centred where possible
    first = max(0, min(active - ROWS // 2, count - ROWS))

    screen.font = label_font
    for i in range(first, min(first + ROWS, count)):
        app = apps[i]
        y = TOP + (i - first) * ROW_H
        selected = i == active

        if selected:
            screen.pen = highlight
            screen.shape(shape.rounded_rectangle(3, y, 150, ROW_H - 1, 6))

        app.icon.alpha = 255 if selected else 150
        screen.blit(app.icon, rect(6, y, 24, 24))

        screen.pen = text if selected else dim
        screen.text(shorten(app.name, 116), 34, y + 5)

    if count > ROWS:
        # track stops short of the rounded bottom corner
        h = 94 * ROWS / count
        y = TOP + (94 - h) * first / (count - ROWS)
        screen.pen = dim
        screen.rectangle(156, y, 2, h)
