"""
Free-roaming snake with tank controls. Steer with A (left) and C (right); the
snake always creeps forward and traces its own path exactly. Eat the dot to grow.
Touching a wall or your own body ends the run.

Controls:
* A = Steer left
* C = Steer right
* B = Start / restart
"""

import os
import sys

sys.path.insert(0, "/system/apps/snake")
os.chdir("/system/apps/snake")

import math
import micropython
import random


class GameState:
    INTRO = 1
    PLAYING = 2
    GAME_OVER = 3


# High resolution, unlocked framerate.
screen.pen = color.rgb(0, 0, 0)
badge.mode(HIRES)
screen.antialias = image.X2

CX, CY = screen.width / 2, screen.height / 2

small_font = font.nope
title_font = font.load("assets/AeonikFono-Regular.af")

# Sizes for the Aeonik vector font (size == pixel height).
TITLE_SIZE = 44
HEADING_SIZE = 30
BAR_TITLE_SIZE = 22
PROMPT_SIZE = 14

# Test: blit a pre-rendered 16px icon in place of the apple.
APPLE_ICON = image.load("assets/cloud_ai_16.png")
APPLE_SIZE = 16

# Palette drawn from the Arm design system: cyan snake, orange apple, white text.
ARM_CYAN = color.rgb(0, 193, 222)       # --arm-light-blue
ARM_DARK_BLUE = color.rgb(0, 43, 73)    # --arm-dark-blue
ARM_ORANGE = color.rgb(255, 107, 0)     # --arm-orange
ARM_YELLOW = color.rgb(255, 199, 0)     # --arm-yellow
ARM_WHITE = color.rgb(255, 255, 255)

BACKGROUND = color.rgb(0, 0, 0)
SNAKE = color.rgb(2, 234, 234)
EYE = ARM_DARK_BLUE
APPLE = color.rgb(114, 51, 247)
APPLE_CORE = color.rgb(210, 190, 255)
WALL = color.rgb(0, 87, 255)
TEXT = ARM_WHITE
TEXT_SHADOW = color.rgb(0, 0, 0, 120)

HUD_H = 28                  # height of the top HUD bar; play area starts below

# Subtle magenta perspective grid filling the play area. The vanishing point
# sits above the screen so the columns fan out without fully converging, and
# the grid parallax-scrolls with the snake's position. Its luminance sits below
# the bloom threshold so it stays crisp.
GRID = color.rgb(72, 10, 66)
GRID_VP_Y = -100            # vanishing point y, above the screen
GRID_COLS = 10              # converging columns either side of centre
GRID_COL_SPACING = 40       # column spread along the bottom edge
GRID_ROWS = 14              # perspective depth lines (enough to fill to the top)
GRID_ROW_RATIO = 0.905      # geometric row spacing (closer to 1 = denser)
GRID_PAR_X = 0.35           # lateral parallax vs snake x
GRID_PAR_Y = 0.009          # depth parallax vs snake y

# Movement, in units per millisecond so motion is framerate independent.
SPEED = 0.075                # forward pixels per ms
TURN = 0.0045                # radians per ms
SPACING = 4.0                # distance between recorded path points
START_POINTS = 14            # body length, in path points
GROW_POINTS = 6              # points added per apple
MAX_DT = 50                  # clamp long frames so a stall can't teleport us

# Snake body outline half-widths (a slender body with a subtly bulbous head).
BODY_HALF = 2.6
HEAD_EXTRA = 2.1
WALL_MARGIN = 4             # play-area inset used for collision
WALL_THICK = 1             # drawn wall thickness
EAT_RADIUS = 11
NECK_SKIP = 8                # body points near the head ignored for self-collision

# Bloom post-process: bloom(threshold, intensity, radius, strength). Threshold
# sits above the grid's luminance (so it stays crisp) and below the apple's.
BLOOM_ARGS = (60, 255, 7.5, 3.0)

_sqrt = math.sqrt


@micropython.native
def build_ribbon(head, path, buf, body_half, head_extra):
    # Write the closed body outline into the preallocated `buf` (2n vec2). For
    # centreline point i the left vertex goes to buf[i] and the right vertex to
    # buf[2n-1-i], so one pass fills both sides of the ribbon. Existing vec2
    # objects are mutated rather than reallocated. Hot path, hence native.
    n = len(path) + 1
    total = n + n
    for i in range(n):
        if i == 0:
            cur = head
            a = head
        else:
            cur = path[i - 1]
            a = head if i == 1 else path[i - 2]
        b = path[i] if i < n - 1 else cur

        cx = cur.x
        cy = cur.y
        tx = a.x - b.x
        ty = a.y - b.y
        length = _sqrt(tx * tx + ty * ty)
        if length > 0.0:
            nx = -ty / length
            ny = tx / length
        else:
            nx = 0.0
            ny = 0.0

        # Width profile: pointed nose, a bulge behind it, tapered tail.
        nose = (i + 0.3) * 0.5
        if nose > 1.0:
            nose = 1.0
        tail = (n - 1 - i) * 0.25 + 0.25
        if tail > 1.0:
            tail = 1.0
        d = i - 3
        if d < 0:
            d = -d
        bulge = 1.0 - d / 3.0
        if bulge < 0.0:
            bulge = 0.0
        m = nose if nose < tail else tail
        half = (body_half + head_extra * bulge) * m

        ox = nx * half
        oy = ny * half
        lp = buf[i]
        lp.x = cx + ox
        lp.y = cy + oy
        rp = buf[total - 1 - i]
        rp.x = cx - ox
        rp.y = cy - oy


class Snake:
    def __init__(self):
        self.reset()

    def reset(self):
        self.heading = -math.pi / 2
        self.head = vec2(CX, CY + 40)
        self.target_points = START_POINTS
        self._buf = []  # reused ribbon vertex buffer (list of vec2)
        # Seed the trailing path so the snake starts at full length.
        dx = -math.cos(self.heading) * SPACING
        dy = -math.sin(self.heading) * SPACING
        self.path = [vec2(self.head.x + dx * i, self.head.y + dy * i)
                     for i in range(1, self.target_points + 1)]

    def update(self, dt):
        if badge.held(BUTTON_A):
            self.heading -= TURN * dt
        if badge.held(BUTTON_C):
            self.heading += TURN * dt

        step = SPEED * dt
        self.head = vec2(self.head.x + math.cos(self.heading) * step,
                         self.head.y + math.sin(self.heading) * step)

        # Record a new path point once we've travelled far enough from the last.
        front = self.path[0]
        if (self.head.x - front.x) ** 2 + (self.head.y - front.y) ** 2 >= SPACING * SPACING:
            self.path.insert(0, vec2(self.head.x, self.head.y))

        while len(self.path) > self.target_points:
            self.path.pop()

    def grow(self):
        self.target_points += GROW_POINTS

    def wander(self, dt):
        # Attract-mode autopilot: look ahead and, when nearing a wall, steer
        # back toward the centre; otherwise drift gently.
        dx, dy = math.cos(self.heading), math.sin(self.heading)
        ax = self.head.x + dx * 46
        ay = self.head.y + dy * 46
        m = WALL_MARGIN + 34
        if (ax < m or ax > screen.width - m
                or ay < m or ay > screen.height - m):
            # Turn toward the centre, choosing the shorter way round.
            cross = dx * (CY - self.head.y) - dy * (CX - self.head.x)
            rate = TURN * dt * 1.6
            self.heading += rate if cross > 0 else -rate
        else:
            self.heading += math.sin(badge.ticks / 800.0) * TURN * dt * 0.25

    def hit_wall(self):
        return (self.head.x < WALL_MARGIN or self.head.x > screen.width - WALL_MARGIN
                or self.head.y < HUD_H + WALL_MARGIN or self.head.y > screen.height - WALL_MARGIN)

    def hit_self(self):
        limit = (BODY_HALF * 2) ** 2
        for point in self.path[NECK_SKIP:]:
            if (self.head.x - point.x) ** 2 + (self.head.y - point.y) ** 2 < limit:
                return True
        return False

    def draw(self):
        n = len(self.path) + 1
        if n < 2:
            return

        # Reuse the ribbon buffer; only grow/shrink it when the length changes.
        total = n + n
        buf = self._buf
        while len(buf) < total:
            buf.append(vec2(0.0, 0.0))
        if len(buf) > total:
            del buf[total:]

        build_ribbon(self.head, self.path, buf, BODY_HALF, HEAD_EXTRA)

        screen.pen = SNAKE
        screen.shape(shape.custom(buf))

        self._draw_head(self.head, self.path[0])

    def _draw_head(self, nose, behind):
        dx, dy = nose.x - behind.x, nose.y - behind.y
        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            return
        dx, dy = dx / length, dy / length
        nx, ny = -dy, dx

        # Two subtle eyes set back from the nose, one either side of the spine.
        ex = nose.x - dx * 3.0
        ey = nose.y - dy * 3.0
        screen.pen = EYE
        for side in (-1, 1):
            screen.shape(shape.circle(ex + nx * 1.9 * side, ey + ny * 1.9 * side, 1.2))


class Apple:
    def __init__(self):
        self.position = vec2(CX, CY)
        self.respawn(None)

    def respawn(self, snake):
        # Keep clear of the walls and the HUD bar.
        m = WALL_MARGIN + 12
        x0, x1 = m, screen.width - m
        y0, y1 = HUD_H + m, screen.height - m
        for _ in range(30):
            candidate = vec2(random.randint(x0, x1), random.randint(y0, y1))
            if snake is None:
                self.position = candidate
                return
            dx = candidate.x - snake.head.x
            dy = candidate.y - snake.head.y
            if dx * dx + dy * dy > 60 * 60:
                self.position = candidate
                return
        self.position = candidate

    def draw(self):
        # White rounded-rect tile so the dark icon reads, then the icon blitted
        # 1:1 (it is pre-rendered at 16px, so no runtime scaling).
        half = APPLE_SIZE / 2
        tile = APPLE_SIZE + 4
        th = tile / 2
        screen.pen = ARM_WHITE
        screen.shape(shape.rounded_rectangle(self.position.x - th, self.position.y - th,
                                             tile, tile, 4))
        screen.blit(APPLE_ICON, int(self.position.x - half), int(self.position.y - half))


HUD_LABEL = color.rgb(120, 132, 140)
HUD_RULE = color.rgb(60, 70, 78)


def color_text(t, x, y, pen, size=None):
    screen.pen = TEXT_SHADOW
    if size is None:
        screen.text(t, x + 1, y + 1)
    else:
        screen.text(t, x + 1, y + 1, size)
    screen.pen = pen
    if size is None:
        screen.text(t, x, y)
    else:
        screen.text(t, x, y, size)


def shadow_text(t, x, y, size=None):
    color_text(t, x, y, TEXT, size)


def center_text(t, y, size=None):
    w, _ = screen.measure_text(t) if size is None else screen.measure_text(t, size)
    shadow_text(t, CX - w / 2, y, size)


def level():
    return score + 1


def play_top():
    # The play area starts below the HUD bar, except on the intro screen which
    # has no bar, so the grid and walls run to the very top there.
    return 0 if state == GameState.INTRO else HUD_H


def draw_top_bar():
    # Classic arcade strip: stacked label/value columns with the title centred.
    screen.font = small_font
    color_text("SCORE", 6, 3, HUD_LABEL)
    color_text("%04d" % score, 6, 14, TEXT)

    lw, _ = screen.measure_text("LEVEL")
    color_text("LEVEL", screen.width - lw - 6, 3, HUD_LABEL)
    lv = "%02d" % level()
    vw, _ = screen.measure_text(lv)
    color_text(lv, screen.width - vw - 6, 14, TEXT)

    screen.font = title_font
    name = "SNAKE"
    nw, _ = screen.measure_text(name, BAR_TITLE_SIZE)
    color_text(name, CX - nw / 2, 3, TEXT, BAR_TITLE_SIZE)

    screen.pen = HUD_RULE
    screen.shape(shape.rectangle(0, 27, screen.width, 1))


def draw_grid():
    # Perspective floor grid filling the play area. Columns pivot around an
    # off-screen vanishing point (so they fan without meeting) and pan with the
    # snake's x; depth rows are geometrically spaced and scroll with its y.
    # screen.line is a fast 1px primitive, far cheaper than vector shapes.
    screen.pen = GRID
    W, H = screen.width, screen.height
    pt = play_top()
    span = H - GRID_VP_Y
    top_ratio = (pt - GRID_VP_Y) / span

    ox = (snake.head.x * GRID_PAR_X) % GRID_COL_SPACING
    for k in range(-GRID_COLS, GRID_COLS + 1):
        bx = CX + k * GRID_COL_SPACING - ox
        x_top = CX + (bx - CX) * top_ratio
        screen.line(int(x_top), pt, int(bx), H)

    frac = (snake.head.y * GRID_PAR_Y) % 1.0
    for i in range(GRID_ROWS):
        y = GRID_VP_Y + span * (GRID_ROW_RATIO ** (i + frac))
        if y >= pt:
            screen.line(0, int(y), W, int(y))


def draw_walls():
    screen.pen = WALL
    W, H = screen.width, screen.height
    pt = play_top()
    t = WALL_THICK
    screen.rectangle(0, pt, W, t)
    screen.rectangle(0, H - t, W, t)
    screen.rectangle(0, pt, t, H - pt)
    screen.rectangle(W - t, pt, t, H - pt)


snake = Snake()
apple = Apple()
score = 0
state = GameState.INTRO


def start_game():
    global score, state
    snake.reset()
    apple.respawn(snake)
    score = 0
    state = GameState.PLAYING


# Each state is split into a world layer (snake + apple, which the bloom acts
# on) and a text layer, drawn after the bloom so the HUD stays crisp.

def intro_world():
    dt = min(badge.ticks_delta, MAX_DT)
    snake.wander(dt)
    snake.update(dt)
    snake.draw()


def intro_text():
    screen.font = title_font
    center_text("SNAKE", CY - 74, TITLE_SIZE)
    center_text("A / C to steer, chase the dot", CY - 12, PROMPT_SIZE)
    if int(badge.ticks / 500) % 2:
        center_text("Press B to start", CY + 18, PROMPT_SIZE)

    if badge.pressed(BUTTON_B):
        start_game()


def playing_world():
    global state, score
    dt = min(badge.ticks_delta, MAX_DT)
    snake.update(dt)

    dx = snake.head.x - apple.position.x
    dy = snake.head.y - apple.position.y
    if dx * dx + dy * dy < EAT_RADIUS * EAT_RADIUS:
        snake.grow()
        score += 1
        apple.respawn(snake)

    if snake.hit_wall() or snake.hit_self():
        state = GameState.GAME_OVER

    snake.draw()


def playing_text():
    draw_top_bar()
    screen.font = small_font
    shadow_text(f"{len(snake.path) + 1} pts", 6, screen.height - 11)


def game_over_world():
    snake.draw()


def game_over_text():
    draw_top_bar()
    screen.font = title_font
    center_text("GAME OVER", CY - 34, HEADING_SIZE)
    center_text(f"Level {level()} reached", CY + 4, PROMPT_SIZE)
    if int(badge.ticks / 500) % 2:
        center_text("Press B to play again", CY + 28, PROMPT_SIZE)

    if badge.pressed(BUTTON_B):
        start_game()


def init():
    pass


fps = 0.0


def draw_fps():
    global fps
    dt = badge.ticks_delta
    if dt > 0:
        # Smooth the per-frame rate so the readout doesn't jitter.
        fps += (1000.0 / dt - fps) * 0.1
    label = f"{fps:.0f} fps"
    screen.font = small_font
    w, _ = screen.measure_text(label)
    shadow_text(label, screen.width - w - 6, screen.height - 11)


def update():
    screen.pen = BACKGROUND
    screen.clear()

    # World layer: grid + snake + apple, so the bloom acts on those.
    draw_grid()
    if state == GameState.INTRO:
        intro_world()
    elif state == GameState.PLAYING:
        playing_world()
    elif state == GameState.GAME_OVER:
        game_over_world()

    screen.bloom(*BLOOM_ARGS)

    # Crisp overlay (not bloomed): walls, apple icon, then text.
    draw_walls()
    if state != GameState.INTRO:
        apple.draw()
    if state == GameState.INTRO:
        intro_text()
    elif state == GameState.PLAYING:
        playing_text()
    elif state == GameState.GAME_OVER:
        game_over_text()

    draw_fps()


def on_exit():
    pass


init()
run(update)
