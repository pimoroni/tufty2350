import os
import sys

APP_DIR = "/system/apps/marble"
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

import math
import time
import pico3d
from world import (
    LEVELS, Game, palette, build_grid, build_wall, build_ring, build_ball_disc, build_gem,
    fit_distance, view_patch, camera_target, camera_eye, visible, env_streaks, env_horizon,
    depth_key,
    BALL_RADIUS, GEM_Y, GOAL_COL, BEACON_COL, HOLE_RADIUS, CAM_ELEV, WALL_H,
)

# Performance-testing knobs: HIRES = 320x240, LORES = 160x120.
MODE = HIRES
SHOW_FPS = True
SHOW_FLOOR = False      # the dim ground grid; off = walls float in the void
REFLECT = True          # regenerate the ball's matcap each frame from nearby walls
SHOW_MATCAP = False     # debug: blit the live reflection map into the top-left corner
# ── TEMPORARY dev instrumentation: report over USB serial ────────────────────
# PRINT_FPS echoes the on-screen frame time to stdout so it can be read without
# interrupting the app (mpremote exec soft-resets it). SHOT_AFTER dumps the
# framebuffer once, base64, so the result can be looked at off-device. Both off
# for anything but measurement - print() blocks if nothing drains the CDC.
PRINT_FPS = False
SHOT_AFTER = 0          # ms after start to dump one frame, or 0 for never

badge.mode(MODE)
pico3d.engine.cores(2)

S = screen.width / 160          # HUD scale factor (1 at LORES, 2 at HIRES)
FOV = 50.0
ASPECT = screen.width / screen.height
TILT_VISUAL = 0.35              # the board only hints at the physics tilt: a gentle 2.5D rock
CAM_FOLLOW = 5.0                # per-second rate the camera eases toward the ball
SHAKE_DECAY = 6.0               # per-second decay of the impact shake

# --- persistence ----------------------------------------------------------
saved = {"best": 0.0}
try:
    State.load("marble", saved)
except Exception:  # noqa: BLE001
    pass

game = Game(LEVELS, best=saved["best"])

# --- materials + shared props -------------------------------------------------
# everything is self-lit neon: no light, colours come straight from the vertices
unlit = pico3d.material(shading=pico3d.material.UNLIT)

bpos, buv, bidx = build_ball_disc()
ball_mesh = pico3d.mesh(positions=bpos, indices=bidx, uvs=buv)
# a glossy marble: the matcap bakes highlight + reflection into one image and is
# sampled per pixel by the interpolated normal, so the ball reads as shiny glass
# The matcap is a LIVE view onto this image: repainting it each frame changes
# what the ball reflects, with no material rebuild. matcap.png is the base coat
# (the ball's own shading); env_streaks paints the nearby walls on top.
matcap_base = image.load("matcap.png")
matcap = image(matcap_base.width, matcap_base.height)
matcap.antialias = OFF          # it is only sampled through a sphere; AA is wasted here
matcap.blit(matcap_base, vec2(0, 0))
# a plain textured disc: no matcap, no normals, no view matrix - the mapping is
# already the identity, so the map is simply the ball's picture
ball_mat = pico3d.material(texture=matcap, shading=pico3d.material.UNLIT,
                           filter=pico3d.material.BILINEAR, alpha_cutoff=0)
MC = matcap_base.width
MCH = MC * 0.5
# The ground plane's horizon in the matcap: inside is sky, outside is floor.
# It is an ellipse, so a unit circular annulus is squashed onto it by transform.
_HU, _HV, _HRX, _HRY = env_horizon()
FLOOR_RING = shape.arc(vec2(0, 0), 1.0, 6.0, 0, 360)
FLOOR_RING.transform = mat3().translate(_HU * MC, _HV * MC).scale(_HRX * MC, _HRY * MC)
# Translucent, NOT opaque: painting the floor solid black wiped the steel
# gradient off the outer third of the ball, which read as a dark border with
# the reflection inset inside it rather than as a sphere.
FLOOR_COL = color.rgb(3, 5, 10, 205)

# A sphere drawn with a matcap shows the matcap one-to-one, so the image itself
# has to look like a photo of a chrome ball or the ball reads as a flat sticker.
# Reflections are therefore painted semi-transparent (the steel gradient stays
# visible through them) and these three layers go back over the top afterwards:
# a darkening toward the silhouette, a bright rim, and a specular highlight.
STREAK_ALPHA = 210
RIM_LIGHT = shape.arc(vec2(MCH, MCH), MCH * 0.88, MCH * 0.99, 0, 360)
RIM_COL = color.rgb(190, 220, 240, 70)
# one small, tight highlight - a big soft blob reads as a second ball
HILITE = [(shape.circle(vec2(MC * 0.36, MC * 0.28), MCH * (0.15 - 0.05 * k)),
           color.rgb(255, 255, 255, 60 + 70 * k)) for k in range(2)]


def update_reflection(lvl, bx, by, bz, pal):
    """Repaint the ball's matcap: steel base coat, the dark floor below the
    horizon, then a streak per nearby wall. Batched into one shapes() call - the per-call marshalling dominates
    here, not the pixels, so seven separate shape() calls cost ~4ms and one
    batched call costs a fraction of that."""
    matcap.blit(matcap_base, vec2(0, 0))
    # everything below the horizon is the dark void the maze floats over
    matcap.pen = FLOOR_COL
    matcap.shape(FLOOR_RING)
    matcap.pen = color.rgb(pal[0] & 0xff, (pal[0] >> 8) & 0xff, (pal[0] >> 16) & 0xff, STREAK_ALPHA)
    batch = []
    for (u0, v0, u1, v1, wdt) in env_streaks(lvl, bx, by, bz):
        batch.append(shape.line(vec2(u0 * MC, v0 * MC), vec2(u1 * MC, v1 * MC), max(1.0, wdt * MC)))
    if batch:
        matcap.shapes(batch)
    # put the sphere back: a bright rim at grazing angles, then the highlight
    matcap.pen = RIM_COL
    matcap.shape(RIM_LIGHT)
    for (blob, col) in HILITE:
        matcap.pen = col
        matcap.shape(blob)

gpos, gcol, gidx = build_gem()
gem_mesh = pico3d.mesh(positions=gpos, indices=gidx, colors=gcol)
kpos, kcol, kidx = build_gem(size=0.2, color=BEACON_COL, tall=1.5)
beacon_mesh = pico3d.mesh(positions=kpos, indices=kidx, colors=kcol)

# Two ways to resolve depth, both here so they can be compared on a real frame.
#
# DEPTH_BANDS = 0: no depth buffer at all. Draw order IS the depth test, which
#   works because the scene is separate convex back-face-culled pieces, and the
#   order can be sorted ONCE per level (see Scene._order). Cheapest by some way.
# DEPTH_BANDS = N: a real 16-bit Z-buffer, N rows-bands at a time in a strip of
#   picovector's on-chip working buffer, with the geometry gathered into a scene
#   first (it has to be, since a band is rasterised against all of it). Exact,
#   order-independent, and at 320x240 it costs a strip of 51 KB rather than the
#   150 KB a full-screen buffer would take out of PSRAM - where a depth buffer
#   is ruinous, being read and written once a pixel for every pixel covered.
DEPTH_BANDS = 3

if DEPTH_BANDS:
    surface = pico3d.surface(screen, bands=DEPTH_BANDS)
    # Sized for the worst frame this game submits: the cull keeps ~80 meshes /
    # 1100 vertices / 600 triangles on screen, plus the ball, gems and beacon.
    # add() refuses rather than growing, so the headroom is deliberate.
    scene = pico3d.scene(surface, meshes=160, vertices=1700, triangles=1000)

    def draw_one(mesh, model, vproj, mat):
        scene.add(mesh, model, vproj, mat)
        return 0
else:
    surface = pico3d.surface(screen, depth=False)
    scene = None

    def draw_one(mesh, model, vproj, mat):
        return surface.render(mesh, model, vproj, mat, None)
projection = pico3d.mat4.perspective(FOV, ASPECT, 2.0, 80.0)
UP = pico3d.vec3(0.0, 1.0, 0.0)


# --- per-level geometry, built on first visit and cached ------------------------
class Scene:
    def __init__(self, index):
        lvl = LEVELS[index]
        pal = palette(index)
        self.level = lvl
        self.pal = pal
        self.grid = None
        if SHOW_FLOOR:
            pos, col, idx = build_grid(lvl, pal)
            self.grid = pico3d.mesh(positions=pos, indices=idx, colors=col)
        # walls/rings keep their bounds so only what's near the ball is drawn
        self.walls = []
        for wall in lvl.wall_pieces:
            pos, col, idx, bbox = build_wall(lvl, wall, pal)
            self.walls.append((bbox, pico3d.mesh(positions=pos, indices=idx, colors=col)))
        self.rings = []
        for (hx, hz) in lvl.holes:
            pos, col, idx = build_ring(lvl, hx, hz, HOLE_RADIUS)
            self.rings.append(((hx, hz, hx, hz), pico3d.mesh(positions=pos, indices=idx, colors=col)))
        gx, gz = lvl.goal
        pos, col, idx = build_ring(lvl, gx, gz, 0.42, width=0.1, color=GOAL_COL)
        self.rings.append(((gx, gz, gx, gz), pico3d.mesh(positions=pos, indices=idx, colors=col)))
        self.gems = [(x, z, lvl.height(x, z)) for (x, z) in lvl.gems]
        self.goal = (gx, lvl.height(gx, gz), gz)
        # how far back the camera sits to frame its patch of board
        vw, vh = view_patch(lvl)
        self.dist = fit_distance(vw, vh, FOV, ASPECT)
        self.draws = self._order(lvl)
        # sky gradient bands, precomputed as pens
        top, bot = pal[3], pal[4]
        self.sky = []
        n = 6
        for i in range(n):
            t = i / (n - 1)
            self.sky.append(color.rgb(int(top[0] + (bot[0] - top[0]) * t),
                                      int(top[1] + (bot[1] - top[1]) * t),
                                      int(top[2] + (bot[2] - top[2]) * t)))


    def _order(self, lvl):
        """Every static thing to draw, sorted back to front, once per level.

        There is no depth buffer, so draw order IS the depth test. The camera
        never yaws and its elevation never changes, so depth_key is affine in
        y and z and the order of anything that does not move never changes - it
        is worth exactly one sort per level and nothing per frame. Only the ball
        moves through this order; update() splices it in by its own key.

        Entries are (key, kind, payload): kind 0 draws payload's mesh with the
        plain board tilt (rings and walls), 1 is a gem (which needs its index,
        to skip collected ones, and its own spin), 2 is the goal beacon.
        """
        draws = []
        if self.grid is not None:
            # The ground grid underlies everything and spans the whole board, so
            # no single key describes it - and it is always furthest anyway.
            draws.append((-1e30, 0, ((-1e30, -1e30, 1e30, 1e30), self.grid)))
        for (bbox, mesh) in self.rings:
            cx, cz = (bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5
            draws.append((depth_key(cx, lvl.height(cx, cz), cz), 0, (bbox, mesh)))
        for (bbox, mesh) in self.walls:
            cx, cz = (bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5
            # keyed at mid-height, so a wall sorts against its neighbours by its
            # body rather than by whichever of its faces happens to be sampled
            draws.append((depth_key(cx, lvl.height(cx, cz) + WALL_H * 0.5, cz), 0, (bbox, mesh)))
        for i, (x, z, y) in enumerate(self.gems):
            draws.append((depth_key(x, y + GEM_Y, z), 1, (i, x, z, y)))
        gx, gy, gz = self.goal
        draws.append((depth_key(gx, gy + GEM_Y + 0.1, gz), 2, None))
        draws.sort(key=lambda e: e[0])
        return draws


scenes = {}


def scene_for(index):
    s = scenes.get(index)
    if s is None:
        s = Scene(index)
        scenes[index] = s
    return s


# --- per-frame state --------------------------------------------------------------
prev_ticks = None
roll_x = 0.0        # accumulated ball rotation about world X (from vz)
roll_z = 0.0        # ... and about world Z (from vx)
b_held_since = None
cam = None          # smoothed camera target [x, y, z]
cam_level = -1      # which level `cam` belongs to, so a level change snaps it
shake = 0.0
gem_flash = 0.0
fps_ms = 0.0
fps_n = 0
fps_text = ""
fps_t0 = 0


def centred(text, y):
    w, _ = screen.measure_text(text)
    screen.text(text, (screen.width - w) // 2, y)


def draw_sky(sc):
    n = len(sc.sky)
    band = screen.height // n + 1
    for i in range(n):
        screen.pen = sc.sky[i]
        screen.rectangle(rect(0, i * band, screen.width, band))


def draw_hud(g):
    pad = int(3 * S)
    line = int(10 * S)
    # the matcap preview owns the top-left corner, so start the text right of it
    left = pad + (MC * int(2 * S) + pad if (SHOW_MATCAP and REFLECT) else 0)
    screen.pen = color.rgb(200, 230, 255)
    screen.text("L%d %s" % (g.level + 1, g.cur.name), left, pad)
    lives = "x%d" % g.lives
    lw, _ = screen.measure_text(lives)
    screen.pen = color.rgb(255, 120, 100)
    screen.text(lives, screen.width - lw - pad, pad)
    screen.pen = color.rgb(230, 235, 255)
    centred("%.1f" % g.live_total(), pad)
    gems = "GEMS %d/%d" % (len(g.collected), len(g.cur.gems))
    screen.pen = color.rgb(255, 255, 255) if gem_flash > 0.0 else color.rgb(255, 230, 120)
    screen.text(gems, left, pad + line)
    if g.best > 0.0:
        screen.pen = color.rgb(150, 200, 255)
        best = "BEST %.1f" % g.best
        bw, bh = screen.measure_text(best)
        screen.text(best, screen.width - bw - pad, screen.height - bh - pad)

    msg = g.message()
    if msg:
        w, h = screen.measure_text(msg)
        y = screen.height // 2 - h
        screen.pen = color.rgb(10, 10, 20)
        screen.rectangle(rect((screen.width - w) // 2 - 3 * pad, y - pad, w + 6 * pad, h + 2 * pad))
        screen.pen = color.rgb(255, 90, 80) if g.state == "fell" else color.rgb(120, 255, 200)
        centred(msg, y)
        if g.state == "complete":
            screen.pen = color.rgb(230, 235, 255)
            centred("TOTAL %.1f  GEMS %d" % (g.total_time, g.gems_total), y + h + pad)
    elif b_held_since is not None:
        screen.pen = color.rgb(255, 230, 120)
        centred("RESTARTING...", screen.height // 2)

    screen.pen = color.rgb(90, 100, 130)
    _, hh = screen.measure_text("B")
    screen.text("hold B: restart", pad, screen.height - hh - pad)

    if SHOW_FPS and fps_text:
        screen.pen = color.rgb(120, 255, 120)
        fw, fh = screen.measure_text(fps_text)
        screen.text(fps_text, (screen.width - fw) // 2, screen.height - fh - pad)


def tilt_matrix(g, px, py, pz):
    # rock the whole board gently about its centre with the physics tilt
    return (pico3d.mat4().translate(px, py, pz)
            .rotate_x_radians(g.tilt_x * TILT_VISUAL).rotate_z_radians(g.tilt_z * TILT_VISUAL)
            .translate(-px, -py, -pz))


shot_done = False


def _dump_screen():
    """One frame of the framebuffer, base64, between markers - TEMPORARY."""
    import binascii
    mv = memoryview(display)
    w, h = screen.width, screen.height
    print("SHOT %d %d" % (w, h))
    step = 3 * 256                      # a multiple of 3, so base64 has no padding mid-stream
    total = w * h * 4
    for off in range(0, total, step):
        print(binascii.b2a_base64(mv[off:min(off + step, total)]).decode().strip())
    print("SHOTEND")


def update():
    global prev_ticks, roll_x, roll_z, b_held_since, cam, cam_level, shake, gem_flash
    global fps_ms, fps_n, fps_text, fps_t0
    t0 = time.ticks_us()
    t = loop.ticks
    if prev_ticks is None:
        prev_ticks = t
    dt = (t - prev_ticks) / 1000.0
    prev_ticks = t
    if dt > 0.05:
        dt = 0.05   # a stall must not tunnel the ball through a wall

    # B is a deliberate hold so a stray press doesn't wipe a good run
    if badge.held(BUTTON_B):
        if b_held_since is None:
            b_held_since = t
        elif t - b_held_since >= 1000:
            game.restart_level()
            b_held_since = None
    else:
        b_held_since = None

    game.step(dt, badge.held(BUTTON_A), badge.held(BUTTON_C),
              badge.held(BUTTON_UP), badge.held(BUTTON_DOWN))
    if game.save_pending:
        game.save_pending = False
        try:
            State.save("marble", {"best": game.best})
        except Exception:  # noqa: BLE001
            pass
    if game.event == "hit":
        shake = min(0.25, game.hit * 0.04)
    elif game.event == "gem":
        gem_flash = 0.4
    elif game.event == "fall":
        shake = 0.18
    shake -= shake * SHAKE_DECAY * dt
    gem_flash -= dt

    sc = scene_for(game.level)
    lvl = sc.level

    # roll: a ball moving +z turns about +X, moving +x turns about -Z
    roll_x += game.vz * dt / BALL_RADIUS
    roll_z -= game.vx * dt / BALL_RADIUS

    # follow camera: ease toward the ball, clamped so the frame stays on the board
    tx, tz = camera_target(lvl, game.x, game.z)
    ty = game.y
    if cam is None or cam_level != game.level:
        cam = [tx, ty, tz]
        cam_level = game.level
    else:
        k = CAM_FOLLOW * dt
        if k > 1.0:
            k = 1.0
        cam[0] += (tx - cam[0]) * k
        cam[1] += (ty - cam[1]) * k
        cam[2] += (tz - cam[2]) * k
    ax, ay, az = cam[0], cam[1], cam[2]
    ex, ey, ez = camera_eye(ax, ay, az, sc.dist)
    if shake > 0.002:
        ex += math.sin(t * 0.11) * shake
        ez += math.cos(t * 0.17) * shake * 0.6
    view = pico3d.mat4.look_at(pico3d.vec3(ex, ey, ez), pico3d.vec3(ax, ay, az), UP)
    view_proj = projection * view

    draw_sky(sc)

    # Painter's order: the surface has no depth buffer, so everything is drawn
    # back to front. sc.draws is sorted ONCE per level (see Scene._order) - the
    # only thing that moves through the order is the ball, so it is spliced in
    # at the first entry that is nearer than it.
    tilt = tilt_matrix(game, ax, ay, az)
    n = 0
    if scene is not None:
        scene.reset()
    bob = math.sin(t * 0.004) * 0.06
    spin = t * 0.25
    ball_key = None
    if game.state != "fell" or game.timer < 0.4:
        ball_key = depth_key(game.x, game.ball_y(), game.z)

    def draw_ball():
        if REFLECT:
            update_reflection(lvl, game.x, game.ball_y(), game.z, sc.pal)
        k = game.fall_scale()
        # the disc must face the camera, so it takes the ball's tilted POSITION
        # but not the board's rotation. A mirrored sphere shows no spin anyway.
        p = tilt.project(pico3d.vec3(game.x, game.ball_y(), game.z))
        ball = pico3d.mat4().translate(p.x, p.y, p.z).rotate_x(-CAM_ELEV)
        if k < 1.0:
            ball.scale(k)
        return draw_one(ball_mesh, ball, view_proj, ball_mat)

    for (key, kind, payload) in sc.draws:
        if ball_key is not None and key > ball_key:
            n += draw_ball()
            ball_key = None
        if kind == 0:                       # a ring or a wall: the plain tilt
            bbox, mesh = payload
            if visible(bbox, lvl, ax, az):
                n += draw_one(mesh, tilt, view_proj, unlit)
        elif kind == 1:                     # a gem, spun and bobbed
            i, x, z, y = payload
            if i in game.collected or not visible((x, z, x, z), lvl, ax, az):
                continue
            m = (tilt_matrix(game, ax, ay, az)
                 .translate(x, y + GEM_Y + bob, z).rotate_y(spin + i * 40.0))
            n += draw_one(gem_mesh, m, view_proj, unlit)
        else:                               # the goal beacon, slowly spinning
            gx, gy, gz = sc.goal
            beacon = (tilt_matrix(game, ax, ay, az)
                      .translate(gx, gy + GEM_Y + 0.1 + bob, gz).rotate_y(t * 0.12))
            n += draw_one(beacon_mesh, beacon, view_proj, unlit)
    if ball_key is not None:                # nearer than anything else in the scene
        n += draw_ball()

    # Banded Z-buffering rasterises the whole gathered scene in one go, once all
    # the geometry is in. Every 2D draw in this frame - the sky before, the
    # reflection and HUD after - is outside this call, which matters: the depth
    # strip and picovector's 2D rasteriser share the working buffer, and only
    # one of them is ever working at a time.
    if scene is not None:
        n = surface.draw(scene)

    if SHOW_MATCAP and REFLECT:
        # scaled up so the streaks are legible; sits under the HUD text
        z = int(2 * S)
        screen.blit(matcap, rect(0, 0, MC * z, MC * z))

    draw_hud(game)

    if SHOW_FPS:
        fps_ms += time.ticks_diff(time.ticks_us(), t0) / 1000.0
        fps_n += 1
        if t - fps_t0 >= 500:
            ms = fps_ms / fps_n
            fps_text = "%.1fms %dfps %dtri" % (ms, int(1000.0 / ms) if ms > 0 else 0, n)
            if PRINT_FPS:
                print("FPS", fps_text)
            fps_ms = 0.0
            fps_n = 0
            fps_t0 = t

    global shot_done
    if SHOT_AFTER and not shot_done and t > SHOT_AFTER:
        shot_done = True
        _dump_screen()


run(update)
