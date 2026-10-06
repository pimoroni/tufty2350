title_font = font.sins
label_font = font.absolute

top = color.rgb(5, 7, 15)
text = color.latte
dim = color.cyan
line = color.rgb(109, 194, 202, 128)

# night sky, darkest overhead
background = brush.gradient(
    brush.LINEAR, 0.5, 0.0, 0.5, 1.0,
    [(0.0, top), (0.5, color.rgb(15, 26, 51)), (1.0, color.rgb(34, 56, 94))],
    mat3().scale(160, 120),
)

CY = 56
SPACING = 44
# whole multiples of 24 so resting icons scale without uneven columns
ICON = 48
SMALL = 24

# target is unbounded so wrapping rolls onward instead of spinning back
target = 0
pos = 0.0
last = None


def navigate(active, count):
    global target
    if badge.pressed(BUTTON_C):
        target += 1
    if badge.pressed(BUTTON_A):
        target -= 1
    return target % count


def ease(count, active):
    global target, pos, last
    if target % count != active:
        target = pos = active
    now = badge.ticks
    dt = 0 if last is None else now - last
    last = now
    pos += (target - pos) * min(1, dt / 80)
    if abs(target - pos) < 0.01:
        pos = target


def fit(label, width):
    if screen.measure_text(label)[0] <= width:
        return label
    while len(label) > 1 and screen.measure_text(label + "..")[0] > width:
        label = label[:-1]
    return label.rstrip() + ".."


def draw_icon(apps, k):
    d = k - pos
    ad = abs(d)
    if ad > 2.6:
        return
    app = apps[k % len(apps)]
    x = 80 + d * SPACING
    size = round(ICON - min(ad, 1) * (ICON - SMALL))
    app.icon.alpha = int(255 * (1 - min(ad, 2.5) * 0.32))
    screen.blit(app.icon, rect(round(x - size / 2), round(CY - size / 2), size, size))
    app.icon.alpha = 255


def draw_battery():
    if badge.is_charging():
        level = (badge.ticks / 20) % 100
    else:
        level = badge.battery_level()
    x, y, w, h = 137, 4, 16, 8
    screen.pen = dim
    screen.shape(shape.rectangle(x, y, w, h))
    screen.shape(shape.rectangle(x + w, y + 2, 1, 4))
    screen.pen = top
    screen.shape(shape.rectangle(x + 1, y + 1, w - 2, h - 2))
    screen.pen = dim
    screen.shape(shape.rectangle(x + 2, y + 2, ((w - 4) / 100) * level, h - 4))


def render(apps):
    ease(len(apps), apps.active_index)

    # black corners behind the rounded screen, as in the default theme
    screen.pen = color.rgb(0, 0, 0)
    screen.rectangle(0, 0, 10, 10)
    screen.rectangle(150, 0, 10, 10)
    screen.rectangle(0, 110, 10, 10)
    screen.rectangle(150, 110, 10, 10)

    screen.pen = background
    screen.shape(shape.rounded_rectangle(0, 0, 160, 120, 8))

    screen.font = title_font
    screen.pen = dim
    screen.text("BadgeOS", 5, 2)
    draw_battery()

    # framing lines above and below the icon strip
    screen.pen = line
    screen.rectangle(6, CY - ICON / 2 - 4, 148, 1)
    screen.rectangle(6, CY + ICON / 2 + 3, 148, 1)

    base = round(pos)
    for k in range(base - 3, base + 4):
        draw_icon(apps, k)

    screen.font = label_font
    screen.pen = text
    label = fit(apps.active.name, 150)
    w, _ = screen.measure_text(label)
    screen.text(label, 80 - w / 2, 92)
