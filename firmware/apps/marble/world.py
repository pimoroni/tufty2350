# Marble maze world: generated neon mazes, mesh builders, camera helpers and
# the tilt-the-board rolling physics.
#
# Presentation is 2.5D neon: there is no floor, just a dim grid drawn over the
# black void that follows the terrain height (so bumps and dips show as the
# grid warping), walls are low glowing extrusions, and pits, gems and the goal
# are glowing rings and diamonds. The terrain is still an analytic height
# function the physics reads directly.
#
# Free of any badge/pico3d/display dependency (math + array only) so it can be
# unit-tested on the host. __init__.py wires these into the engine.

import math
from array import array

GRID = 0.5           # ground-grid sample spacing along a line (world units)
BALL_RADIUS = 0.224   # 20% smaller than the 0.28 it started at
# The engine bakes a matcap's uv PER VERTEX and interpolates it as a plain
# texture coordinate, but the true mapping is curved, so the error grows with
# how much angle a face spans. At 8 segments a face spanned 45 degrees, which
# smeared the reflection and made silhouette faces sample across the middle of
# the map. These are the knob for that, and for how round the outline looks.
BALL_SEGS = 32       # segments around the ball disc's rim
BALL_RINGS = 14      # (only used by the unused full-sphere builder)
WALL_H = 0.22        # neon wall height: low, so the overhead view stays 2.5D
WALL_R = 0.05        # tiny plan-view corner radius, so the ball deflects off corners smoothly
WALL_SEGS = 1        # (collision only)
GRID_W = 0.05        # ground grid line width
HOLE_RADIUS = 0.42   # pit dimple radius (physics + ring size)
HOLE_DEPTH = 0.3
HOLE_CATCH = 0.24    # distance from a hole centre that swallows the ball
RING_W = 0.08        # width of a glowing ring
GEM_Y = 0.35         # hover height of gems and the goal beacon above the terrain
GEM_SIZE = 0.13

# --- physics --------------------------------------------------------------
GRAVITY = 12.0       # units/s^2 along the slope (board tilt AND terrain slope)
MAX_TILT = 0.42      # radians, either axis
TILT_RATE = 10.0     # how fast the board eases toward the buttons (per second)
FRICTION = 0.4       # velocity damping per second (rolling resistance)
BOUNCE = 0.5         # velocity kept after a wall hit
MAX_SPEED = 7.0
GOAL_CATCH = 0.4
GEM_CATCH = 0.4
HIT_MIN = 1.2        # wall impacts slower than this don't register as a hit
FALL_TIME = 0.7      # seconds the ball drops/shrinks before respawning
GOAL_TIME = 1.2      # pause on "GOAL!" before the next level
INTRO_TIME = 1.4     # "READY" ... "GO!" card
GO_TIME = 0.5        # how long "GO!" shows once play has started
COMPLETE_TIME = 4.0  # "COMPLETE" card before looping back to level 1
GEM_BONUS = 1.5      # seconds taken off the level time per gem
LIVES = 3


# --- levels ---------------------------------------------------------------
# A level is a generated maze on a grid of 1-unit cells, framed by a rim of
# floor RIM wide (the maze occupies world coords [RIM, RIM + cols] x [RIM, RIM + rows]).
#   seed    : maze generator seed (a small LCG, identical on host and device)
#   rooms   : (i0, j0, i1, j1) inclusive cell rects whose internal walls are
#             removed - the open spaces where the dangers live
#   braid   : fraction of dead ends opened into loops (0 = a perfect maze)
#   voids   : (i0, j0, i1, j1) inclusive cell rects cut out of the board; the
#             maze routes around them and the walls facing them are removed,
#             so their edges are cliffs
#   start/goal : cells
#   holes / gems : cell coords (may be fractional), converted to world coords
#   features  : height primitives in WORLD coords (see Level.height):
#     ("bump", cx, cz, rx, rz, h) elliptical cosine bump (negative h = dip)
#     ("ramp", axis, a0, a1, h0, h1) linear slope along "x" or "z"
RIM = 0.5
WALL_T = 0.16        # wall thickness (the reference prints are ~1/6 of a corridor)
WALL_PIECE = 1.0     # merged runs are chopped into pieces at most this long for
                     # DRAWING only: a 60:1 sliver's bounding box is ~48% larger
                     # than the ink in it, and each piece also culls on its own.
                     # Collision keeps the merged rects (fewer tests, no seams).
LEVEL_DATA = [
    {
        "name": "DOCK", "cols": 8, "rows": 6, "seed": 11, "braid": 0.15,
        "rooms": [(1, 1, 2, 2), (5, 3, 6, 4)],
        "start": (0, 0), "goal": (7, 5),
        "holes": [(6.0, 4.0)],
        "features": [],   # bumps off for now
        "gems": [(2.0, 2.0), (7, 0), (0, 5)],
        "voids": [],
    },
    {
        "name": "CONDUIT", "cols": 10, "rows": 7, "seed": 23, "braid": 0.1,
        "rooms": [(4, 2, 5, 4), (0, 5, 1, 6)],
        "start": (0, 0), "goal": (9, 6),
        "holes": [(5.0, 3.0), (0.5, 6.0)],
        "features": [],   # bumps off for now
        "gems": [(5.0, 3.0), (9, 0), (0, 6)],
        "voids": [],
    },
    {
        "name": "REACTOR", "cols": 9, "rows": 9, "seed": 37, "braid": 0.12,
        "rooms": [(3, 3, 5, 5)],
        "start": (0, 0), "goal": (8, 8),
        "holes": [(3.5, 5.5), (5.5, 3.5)],
        "features": [],   # bumps off for now
        "gems": [(4.5, 4.5), (8, 0), (0, 8)],
        "voids": [],
    },
    {
        "name": "SPINE", "cols": 12, "rows": 6, "seed": 41, "braid": 0.1,
        "rooms": [(2, 2, 3, 3), (6, 2, 7, 3), (9, 1, 10, 4)],
        "start": (0, 2), "goal": (11, 3),
        "holes": [(2.5, 3.5), (7.5, 2.5), (10.5, 1.5), (9.5, 4.5)],
        "features": [],   # bumps off for now
        "gems": [(3.5, 2.5), (6.5, 3.5), (10.0, 3.0)],
        "voids": [],
    },
    {
        "name": "VOID", "cols": 12, "rows": 8, "seed": 53, "braid": 0.15,
        "rooms": [(1, 3, 2, 4), (9, 3, 10, 4)],
        "start": (0, 3), "goal": (11, 4),
        "holes": [(2.0, 4.0), (10.0, 3.0), (6.0, 1.0)],
        "features": [],   # bumps off for now
        "gems": [(6.0, 7.0), (1.0, 0.0), (10.0, 7.0)],
        "voids": [(4, 0, 4, 2), (4, 5, 4, 7), (8, 0, 8, 0), (8, 2, 8, 7)],
    },
]


class _LCG:
    """Tiny deterministic RNG so host and device generate the same maze."""

    def __init__(self, seed):
        self.s = (seed * 747796405 + 2891336453) & 0xffffffff

    def next(self):
        self.s = (self.s * 1664525 + 1013904223) & 0xffffffff
        return self.s >> 8

    def randint(self, n):
        return self.next() % n

    def random(self):
        return self.next() / 16777216.0


def generate_maze(cols, rows, seed, blocked=(), rooms=(), braid=0.0):
    """Recursive-backtracker maze over a cols x rows cell grid.
    Returns (hwalls, vwalls): hwalls[j][i] is the wall on the -z side of cell
    (i, j) for j in 0..rows (row `rows` is the far edge); vwalls[j][i] is the
    wall on the -x side of cell (i, j) for i in 0..cols. Blocked cells are
    void: never entered, and every wall facing one is removed. Rooms lose
    their internal walls. braid opens that fraction of dead ends."""
    rng = _LCG(seed)
    blocked = set(blocked)
    hw = [[True] * cols for _ in range(rows + 1)]
    vw = [[True] * (cols + 1) for _ in range(rows)]
    visited = set(blocked)
    # rooms count as pre-joined so the carver treats each as one big cell
    room_of = {}
    for r_i, (i0, j0, i1, j1) in enumerate(rooms):
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                room_of[(i, j)] = r_i
        for j in range(j0, j1 + 1):
            for i in range(i0, i1):
                vw[j][i + 1] = False
        for j in range(j0, j1):
            for i in range(i0, i1 + 1):
                hw[j + 1][i] = False

    def open_between(a, b):
        (ia, ja), (ib, jb) = a, b
        if ia == ib:
            hw[max(ja, jb)][ia] = False
        else:
            vw[ja][max(ia, ib)] = False

    def mark(c):
        visited.add(c)
        r = room_of.get(c)
        if r is not None:
            i0, j0, i1, j1 = rooms[r]
            for j in range(j0, j1 + 1):
                for i in range(i0, i1 + 1):
                    visited.add((i, j))

    start = None
    for j in range(rows):
        for i in range(cols):
            if (i, j) not in blocked:
                start = (i, j)
                break
        if start:
            break
    stack = [start]
    mark(start)
    while stack:
        i, j = stack[-1]
        # a room cell may exit from any of its cells
        cells = [(i, j)]
        r = room_of.get((i, j))
        if r is not None:
            i0, j0, i1, j1 = rooms[r]
            cells = [(a, b) for b in range(j0, j1 + 1) for a in range(i0, i1 + 1)]
        options = []
        for (ci, cj) in cells:
            for (di, dj) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = ci + di, cj + dj
                if 0 <= ni < cols and 0 <= nj < rows and (ni, nj) not in visited:
                    options.append(((ci, cj), (ni, nj)))
        if not options:
            stack.pop()
            continue
        here, nxt = options[rng.randint(len(options))]
        open_between(here, nxt)
        mark(nxt)
        stack.append(nxt)

    # cliffs: no wall between a floor cell and a void cell (or off-board voids)
    for (i, j) in blocked:
        hw[j][i] = False
        hw[j + 1][i] = False
        vw[j][i] = False
        vw[j][i + 1] = False

    # braid: open some dead ends into loops so corridors flow
    if braid > 0.0:
        for j in range(rows):
            for i in range(cols):
                if (i, j) in blocked or (i, j) in room_of:
                    continue
                walls = []
                if hw[j][i] and j > 0 and (i, j - 1) not in blocked:
                    walls.append(("h", j, i))
                if hw[j + 1][i] and j + 1 < rows and (i, j + 1) not in blocked:
                    walls.append(("h", j + 1, i))
                if vw[j][i] and i > 0 and (i - 1, j) not in blocked:
                    walls.append(("v", j, i))
                if vw[j][i + 1] and i + 1 < cols and (i + 1, j) not in blocked:
                    walls.append(("v", j, i + 1))
                closed = (hw[j][i] + hw[j + 1][i] + vw[j][i] + vw[j][i + 1])
                if closed >= 3 and walls and rng.random() < braid:
                    kind, a, b = walls[rng.randint(len(walls))]
                    if kind == "h":
                        hw[a][b] = False
                    else:
                        vw[a][b] = False
    return hw, vw


def chop_walls(rects, piece=WALL_PIECE, level=None):
    """Split each slab along its long axis into pieces at most `piece` long.

    Each piece carries two things it cannot work out on its own, and without
    which the joints show:

    * `top` - the height of the WHOLE parent slab. Left to itself a piece takes
      the highest ground under its own four corners, so a wall crossing a bump
      would step at every joint.
    * `skip` - a bitmask of side faces that are buried inside another wall (the
      end caps at a joint, and the caps where two runs meet at a junction).
      Drawn, they appear as thin lines standing inside a continuous wall.

    Returns [(x0, z0, x1, z1, top, skip), ...]; bit k of skip is the face from
    corner k to corner k+1 of ((x0,z0), (x1,z0), (x1,z1), (x0,z1)).
    """
    out = []
    for (x0, z0, x1, z1) in rects:
        top = None
        if level is not None:
            top = max(level.height(x, z) for (x, z) in
                      ((x0, z0), (x1, z0), (x1, z1), (x0, z1))) + WALL_H
        if (x1 - x0) >= (z1 - z0):
            a = x0
            while a < x1 - 1e-6:
                b = min(a + piece, x1)
                out.append([a, z0, b, z1, top, 0])
                a = b
        else:
            a = z0
            while a < z1 - 1e-6:
                b = min(a + piece, z1)
                out.append([x0, a, x1, b, top, 0])
                a = b
    if level is None:
        return [tuple(p) for p in out]
    # bury any side face whose outward side is inside another wall
    eps = 0.02
    for p in out:
        x0, z0, x1, z1 = p[0], p[1], p[2], p[3]
        mids = (((x0 + x1) * 0.5, z0 - eps), (x1 + eps, (z0 + z1) * 0.5),
                ((x0 + x1) * 0.5, z1 + eps), (x0 - eps, (z0 + z1) * 0.5))
        mask = 0
        for k, (mx, mz) in enumerate(mids):
            for (wx0, wz0, wx1, wz1) in rects:
                if wx0 - 1e-9 <= mx <= wx1 + 1e-9 and wz0 - 1e-9 <= mz <= wz1 + 1e-9:
                    mask |= 1 << k
                    break
        p[5] = mask
    return [tuple(p) for p in out]


def walls_from_maze(hw, vw, cols, rows, origin=RIM, t=WALL_T):
    """Merge maze wall segments into slab rectangles (world coords)."""
    slabs = []
    h = t * 0.5
    for j in range(rows + 1):
        i = 0
        while i < cols:
            if hw[j][i]:
                k = i
                while k + 1 < cols and hw[j][k + 1]:
                    k += 1
                slabs.append((origin + i - h, origin + j - h, origin + k + 1 + h, origin + j + h))
                i = k + 1
            else:
                i += 1
    for i in range(cols + 1):
        j = 0
        while j < rows:
            if vw[j][i]:
                k = j
                while k + 1 < rows and vw[k + 1][i]:
                    k += 1
                slabs.append((origin + i - h, origin + j - h, origin + i + h, origin + k + 1 + h))
                j = k + 1
            else:
                j += 1
    return slabs


class Level:
    def __init__(self, d):
        self.name = d["name"]
        cols = d["cols"]
        rows = d["rows"]
        self.cols = cols
        self.rows = rows
        self.w = float(cols + 2 * RIM)
        self.h = float(rows + 2 * RIM)
        blocked = set()
        self.voids = []
        for (i0, j0, i1, j1) in d.get("voids", ()):
            for j in range(j0, j1 + 1):
                for i in range(i0, i1 + 1):
                    blocked.add((i, j))
            self.voids.append((RIM + i0, RIM + j0, RIM + i1 + 1, RIM + j1 + 1))
        self.seed = d["seed"]
        self.rooms = tuple(d.get("rooms", ()))
        self.braid = d.get("braid", 0.0)
        self.blocked = blocked
        self.start = self.cell_centre(*d["start"])
        self.goal = self.cell_centre(*d["goal"])
        self.features = d.get("features", [])
        self.holes = [self.cell_centre(i, j) for (i, j) in d.get("holes", ())]
        self.gems = [self.cell_centre(i, j) for (i, j) in d.get("gems", ())]
        hw, vw = generate_maze(cols, rows, self.seed, blocked, self.rooms, self.braid)
        # walls: merged runs for collision, chopped pieces for drawing. Chopping
        # reads height(), so it has to come after features and holes are set.
        self.walls = walls_from_maze(hw, vw, cols, rows) + list(d.get("walls", ()))
        self.wall_pieces = chop_walls(self.walls, WALL_PIECE, self)
        for p in [self.start, self.goal] + list(self.gems) + list(self.holes):
            if not self.on_board(p[0], p[1]):
                raise ValueError("%s: %r is off the board" % (self.name, p))

    @staticmethod
    def cell_centre(i, j):
        return (RIM + i + 0.5, RIM + j + 0.5)

    # --- terrain ---------------------------------------------------------------
    def height(self, x, z):
        y = 0.0
        for f in self.features:
            if f[0] == "bump":
                _, cx, cz, rx, rz, hgt = f
                dx = (x - cx) / rx
                dz = (z - cz) / rz
                d = math.sqrt(dx * dx + dz * dz)
                if d < 1.0:
                    y += hgt * (0.5 + 0.5 * math.cos(math.pi * d))
            else:
                _, axis, a0, a1, h0, h1 = f
                a = x if axis == "x" else z
                if a <= a0:
                    y += h0
                elif a >= a1:
                    y += h1
                else:
                    y += h0 + (h1 - h0) * (a - a0) / (a1 - a0)
        for (cx, cz) in self.holes:
            dx = x - cx
            dz = z - cz
            d = math.sqrt(dx * dx + dz * dz) / HOLE_RADIUS
            if d < 1.0:
                y -= HOLE_DEPTH * (0.5 + 0.5 * math.cos(math.pi * d))
        return y

    def gradient(self, x, z, eps=0.05):
        gx = (self.height(x + eps, z) - self.height(x - eps, z)) / (2.0 * eps)
        gz = (self.height(x, z + eps) - self.height(x, z - eps)) / (2.0 * eps)
        return gx, gz

    def in_void(self, x, z):
        for (x0, z0, x1, z1) in self.voids:
            if x0 <= x < x1 and z0 <= z < z1:
                return True
        return False

    def on_board(self, x, z):
        return 0.0 <= x < self.w and 0.0 <= z < self.h and not self.in_void(x, z)

    def under_wall(self, x0, z0, x1, z1):
        """Is the whole quad hidden inside a wall slab's footprint?"""
        for (wx0, wz0, wx1, wz1) in self.walls:
            if x0 >= wx0 and x1 <= wx1 and z0 >= wz0 and z1 <= wz1:
                return True
        return False

    def hole_dist(self, x, z):
        """Distance from the nearest hole centre (large if none)."""
        best = 1e9
        for (cx, cz) in self.holes:
            d = math.sqrt((x - cx) ** 2 + (z - cz) ** 2)
            if d < best:
                best = d
        return best


LEVELS = [Level(d) for d in LEVEL_DATA]


def rgb(r, g, b):
    """Pack to the engine's 0x00BBGGRR vertex-colour word."""
    return (r & 0xff) | ((g & 0xff) << 8) | ((b & 0xff) << 16)


def scale_rgb(c, k):
    r = int((c & 0xff) * k)
    g = int(((c >> 8) & 0xff) * k)
    b = int(((c >> 16) & 0xff) * k)
    return rgb(min(r, 255), min(g, 255), min(b, 255))


# One neon hue per level: (wall_top, wall_side, grid, sky_top(rgb tuple), sky_bottom)
PALETTES = [
    (rgb(255, 70, 230), rgb(150, 30, 140), rgb(28, 22, 60), (0, 0, 0), (16, 8, 40)),
    (rgb(255, 150, 40), rgb(150, 80, 20), rgb(40, 26, 24), (0, 0, 0), (30, 14, 8)),
    (rgb(120, 255, 80), rgb(60, 140, 40), rgb(20, 40, 28), (0, 0, 0), (6, 26, 14)),
    (rgb(170, 90, 255), rgb(90, 40, 150), rgb(26, 20, 56), (0, 0, 0), (14, 8, 36)),
    (rgb(255, 60, 90), rgb(150, 30, 50), rgb(44, 18, 28), (0, 0, 0), (28, 6, 14)),
]
BLACK = rgb(0, 0, 0)
HOLE_RING = rgb(255, 40, 30)        # danger red
GOAL_COL = rgb(60, 255, 120)
BALL_A = rgb(255, 255, 255)     # matcap tints, so white = the map's own colour
BALL_B = rgb(200, 226, 232)
GEM_COL = rgb(255, 240, 90)
BEACON_COL = rgb(60, 255, 120)


def palette(level_index):
    return PALETTES[level_index % len(PALETTES)]


class _MeshBuf:
    def __init__(self):
        self.pos = array("f")
        self.col = array("I")
        self.idx = array("H")

    def vert(self, x, y, z, c):
        self.pos.append(x)
        self.pos.append(y)
        self.pos.append(z)
        self.col.append(c)
        return len(self.col) - 1

    def tri(self, a, b, c):
        self.idx.append(a)
        self.idx.append(b)
        self.idx.append(c)

    def quad_facing(self, p0, p1, p2, p3, n, colors):
        """Quad p0-p1-p2-p3 (a loop) wound so its front faces along n.
        colors is one packed colour per corner."""
        b = self.vert(p0[0], p0[1], p0[2], colors[0])
        self.vert(p1[0], p1[1], p1[2], colors[1])
        self.vert(p2[0], p2[1], p2[2], colors[2])
        self.vert(p3[0], p3[1], p3[2], colors[3])
        ax, ay, az = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
        bx, by, bz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
        cx, cy, cz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
        if cx * n[0] + cy * n[1] + cz * n[2] >= 0.0:
            self.tri(b, b + 1, b + 2)
            self.tri(b, b + 2, b + 3)
        else:
            self.tri(b, b + 2, b + 1)
            self.tri(b, b + 3, b + 2)


UP = (0.0, 1.0, 0.0)


def _line(m, level, xa, za, xb, zb, width, c, lift, step=GRID):
    """A flat strip along the ground from (xa,za) to (xb,zb), sampled every
    `step` so it follows the terrain. Skips pieces whose middle is in a void."""
    length = math.sqrt((xb - xa) ** 2 + (zb - za) ** 2)
    n = max(1, int(round(length / step)))
    ux, uz = (xb - xa) / length, (zb - za) / length
    hx, hz = -uz * width * 0.5, ux * width * 0.5
    for k in range(n):
        t0 = k / n
        t1 = (k + 1) / n
        x0, z0 = xa + (xb - xa) * t0, za + (zb - za) * t0
        x1, z1 = xa + (xb - xa) * t1, za + (zb - za) * t1
        if level.in_void((x0 + x1) * 0.5, (z0 + z1) * 0.5):
            continue
        y0 = level.height(x0, z0) + lift
        y1 = level.height(x1, z1) + lift
        m.quad_facing((x0 + hx, y0, z0 + hz), (x1 + hx, y1, z1 + hz),
                      (x1 - hx, y1, z1 - hz), (x0 - hx, y0, z0 - hz), UP, (c, c, c, c))


def build_grid(level, pal=None, lift=0.0):
    """The ground: a dim grid of lines on the 1-unit cell boundaries across the
    whole board, following the terrain, so slopes read as grid distortion.
    Returns (positions, colors, indices)."""
    pal = pal or PALETTES[0]
    c = pal[2]
    m = _MeshBuf()
    x = 0.0
    while x <= level.w + 1e-6:
        _line(m, level, x, 0.0, x, level.h, GRID_W, c, lift)
        x += 1.0
    z = 0.0
    while z <= level.h + 1e-6:
        _line(m, level, 0.0, z, level.w, z, GRID_W, c, lift)
        z += 1.0
    return m.pos, m.col, m.idx


def build_wall(level, rect, pal=None):
    """One neon wall: a low box, top in the bright hue and sides in a darker
    one. `rect` is (x0, z0, x1, z1), optionally with a `top` height and a
    `skip` face mask from chop_walls; without them the piece stands on the
    highest ground under its own corners and draws all four sides.
    Returns (pos, col, idx, bbox)."""
    pal = pal or PALETTES[0]
    top_c, side_c = pal[0], pal[1]
    x0, z0, x1, z1 = rect[0], rect[1], rect[2], rect[3]
    top = rect[4] if len(rect) > 4 and rect[4] is not None else None
    skip = rect[5] if len(rect) > 5 else 0
    corners = ((x0, z0), (x1, z0), (x1, z1), (x0, z1))
    if top is None:
        top = max(level.height(x, z) for (x, z) in corners) + WALL_H
    m = _MeshBuf()
    m.quad_facing((x0, top, z0), (x0, top, z1), (x1, top, z1), (x1, top, z0), UP, (top_c,) * 4)
    for k in range(4):
        if skip & (1 << k):
            continue
        xa, za = corners[k]
        xb, zb = corners[(k + 1) % 4]
        nx, nz = (zb - za), -(xb - xa)          # outward normal of this edge
        ya = level.height(xa, za) - 0.05
        yb = level.height(xb, zb) - 0.05
        m.quad_facing((xa, ya, za), (xb, yb, zb), (xb, top, zb), (xa, top, za), (nx, 0.0, nz), (side_c,) * 4)
    return m.pos, m.col, m.idx, (x0, z0, x1, z1)


def build_ring(level, cx, cz, radius, width=RING_W, color=HOLE_RING, segments=12, lift=0.012):
    """A flat glowing annulus hugging the ground around (cx, cz).
    Returns (pos, col, idx)."""
    m = _MeshBuf()
    outer = []
    inner = []
    for s_ in range(segments):
        a = 2.0 * math.pi * s_ / segments
        ca = math.cos(a)
        sa = math.sin(a)
        xo, zo = cx + ca * radius, cz + sa * radius
        xi, zi = cx + ca * (radius - width), cz + sa * (radius - width)
        outer.append(m.vert(xo, level.height(xo, zo) + lift, zo, color))
        inner.append(m.vert(xi, level.height(xi, zi) + lift, zi, color))
    for s_ in range(segments):
        t = (s_ + 1) % segments
        # angle increases clockwise seen from +Y, so (o, i, i_next) is CCW from above
        m.tri(outer[s_], inner[s_], inner[t])
        m.tri(outer[s_], inner[t], outer[t])
    return m.pos, m.col, m.idx


def build_ball_disc(segments=BALL_SEGS, radius=BALL_RADIUS):
    """The ball as a camera-facing disc textured with the environment map.

    This is not an approximation of the sphere - it is the sphere, exactly. A
    matcap is indexed by the view-space normal, and on a sphere that normal at
    a given screen point IS that point on the unit disc, so the mapping is the
    identity and a lit sphere renders as the map painted on a disc. Drawing
    real sphere geometry only ADDS error: a polygonal silhouette, texture
    coordinates baked per vertex and interpolated flat, and rim triangles whose
    two ends sit on opposite sides of the map so they smear through its middle.

    Radially a triangle fan is exact (a point at disc radius r maps to map
    radius r/2, which is what linear interpolation from the centre gives), so
    the only error left is the polygonal rim, and that is 32 segments cheap.

    Built in the XY plane facing +Z; the wiring turns it to face the camera.
    Returns (positions, uvs, indices).
    """
    pos = array("f")
    uv = array("f")
    idx = array("H")
    pos.append(0.0); pos.append(0.0); pos.append(0.0)
    uv.append(0.5); uv.append(0.5)
    for k in range(segments):
        a = 2.0 * math.pi * k / segments
        ca = math.cos(a)
        sa = math.sin(a)
        pos.append(ca * radius); pos.append(sa * radius); pos.append(0.0)
        uv.append(0.5 + 0.5 * ca); uv.append(0.5 - 0.5 * sa)
    for k in range(segments):
        # CCW seen from +Z, so the disc faces the camera and survives culling
        idx.append(0); idx.append(1 + k); idx.append(1 + (k + 1) % segments)
    return pos, uv, idx


def build_ball(segments=BALL_SEGS, rings=BALL_RINGS, radius=BALL_RADIUS):
    """UV sphere with normals and two-tone stripes so the roll is visible.
    Returns (positions, normals, colors, indices)."""
    pos = array("f")
    nrm = array("f")
    col = array("I")
    idx = array("H")

    def vert(nx, ny, nz, c):
        for v in (nx, ny, nz):
            nrm.append(v)
            pos.append(v * radius)
        col.append(c)
        return len(col) - 1

    top = vert(0.0, 1.0, 0.0, BALL_A)
    for k in range(1, rings):
        th = math.pi * k / rings
        for s_ in range(segments):
            ph = 2.0 * math.pi * s_ / segments
            vert(math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph),
                 BALL_B if s_ & 1 else BALL_A)
    bot = vert(0.0, -1.0, 0.0, BALL_A)

    def ring(k, s_):
        return 1 + (k - 1) * segments + (s_ % segments)

    for s_ in range(segments):
        idx.append(top)
        idx.append(ring(1, s_ + 1))
        idx.append(ring(1, s_))
    for k in range(1, rings - 1):
        for s_ in range(segments):
            a = ring(k, s_)
            b = ring(k, s_ + 1)
            c = ring(k + 1, s_)
            d = ring(k + 1, s_ + 1)
            idx.append(a); idx.append(d); idx.append(c)
            idx.append(a); idx.append(b); idx.append(d)
    for s_ in range(segments):
        idx.append(bot)
        idx.append(ring(rings - 1, s_))
        idx.append(ring(rings - 1, s_ + 1))
    return pos, nrm, col, idx


def build_gem(size=GEM_SIZE, color=GEM_COL, tall=1.6):
    """Octahedron (8 tris) centred on the origin, stretched along Y. Used for
    both the gems and the goal beacon. Returns (positions, colors, indices)."""
    m = _MeshBuf()
    dim = scale_rgb(color, 0.6)
    top = m.vert(0.0, size * tall, 0.0, color)
    ring = [m.vert(size, 0.0, 0.0, dim), m.vert(0.0, 0.0, size, dim),
            m.vert(-size, 0.0, 0.0, dim), m.vert(0.0, 0.0, -size, dim)]
    bot = m.vert(0.0, -size * tall, 0.0, color)
    for s_ in range(4):
        a = ring[s_]
        b = ring[(s_ + 1) % 4]
        m.tri(top, b, a)
        m.tri(bot, a, b)
    return m.pos, m.col, m.idx


# --- reflection ---------------------------------------------------------------
# The ball's matcap is regenerated each frame from the walls around it, which is
# what makes it look mirrored. A matcap texel is indexed by the VIEW-SPACE
# NORMAL, and for a mirror sphere the normal that reflects a direction R into
# the eye is the bisector of R and the view axis. So a world direction maps to
# a matcap point with one normalise and an add - no trigonometry:
#
#     d_view = to_view(d) ; n = normalise(d_view + (0, 0, 1))
#     u = 0.5 + 0.5 * n.x ; v = 0.5 - 0.5 * n.y      (v flipped for image rows)
#
# The camera never yaws (fixed elevation, looking down -z), so the view basis is
# a constant: right = +x, up = (0, cos e, -sin e), forward = (0, -sin e, -cos e).
ENV_RANGE = 2.6      # only wall pieces within this many units are reflected
ENV_MAX = 10         # ... and at most this many, nearest first (bounds the cost)
ENV_MIN_W = 0.02     # floor on a streak's width in matcap units, so far walls still register


def _to_matcap(dx, dy, dz, sin_e, cos_e):
    """World direction -> (u, v) in the matcap's 0..1 square, or None if degenerate."""
    L = math.sqrt(dx * dx + dy * dy + dz * dz)
    if L < 1e-6:
        return None
    dx /= L; dy /= L; dz /= L
    # into view space: x right, y up, z toward the eye
    vx = dx
    vy = dy * cos_e - dz * sin_e
    vz = dy * sin_e + dz * cos_e
    # bisector of the reflected direction and the view axis
    nx, ny, nz = vx, vy, vz + 1.0
    n = math.sqrt(nx * nx + ny * ny + nz * nz)
    if n < 1e-6:
        return None
    return (0.5 + 0.5 * nx / n, 0.5 - 0.5 * ny / n)


def env_horizon(elev_deg=None, samples=24):
    """Where the ground plane's horizon lands in the matcap, as (cu, cv, rx, ry).

    Every horizontal direction maps to a closed loop inside the matcap disc.
    The camera's downward tilt squashes that loop vertically and pushes it up,
    so it is an ellipse, not a circle - fitting a circle to it was out by ~10%
    of the disc, which showed as the floor eating into the sky. Inside the
    ellipse is sky, outside is floor.
    """
    if elev_deg is None:
        elev_deg = CAM_ELEV
    e = math.radians(elev_deg)
    sin_e = math.sin(e)
    cos_e = math.cos(e)
    us = []
    vs = []
    for k in range(samples):
        a = 2.0 * math.pi * k / samples
        p = _to_matcap(math.cos(a), 0.0, math.sin(a), sin_e, cos_e)
        if p is not None:
            us.append(p[0])
            vs.append(p[1])
    cu = (min(us) + max(us)) * 0.5
    cv = (min(vs) + max(vs)) * 0.5
    return cu, cv, (max(us) - min(us)) * 0.5, (max(vs) - min(vs)) * 0.5


def env_streaks(level, bx, by, bz, elev_deg=None, rng=ENV_RANGE, limit=ENV_MAX):
    """Where the nearby walls appear in the ball's reflection.

    Returns [(u0, v0, u1, v1, width), ...] in matcap 0..1 coords.

    Two things matter for this to read as a reflection rather than as bars
    painted on a disc:

    * It walks the SHORT chopped wall pieces, not the merged runs. A long wall
      curves through the map, and a straight line between its two distant ends
      cuts across the disc through geometry that is not there.
    * A piece's width comes from mapping its base and its top and measuring the
      gap, not from a height-over-distance formula. The old formula was clamped
      at half the map, and since a ball in a maze is nearly always close to a
      wall, that clamp fired constantly and produced huge slabs of colour.
    """
    if elev_deg is None:
        elev_deg = CAM_ELEV
    e = math.radians(elev_deg)
    sin_e = math.sin(e)
    cos_e = math.cos(e)
    near = []
    for piece in level.wall_pieces:
        x0, z0, x1, z1 = piece[0], piece[1], piece[2], piece[3]
        px = min(max(bx, x0), x1)
        pz = min(max(bz, z0), z1)
        d2 = (px - bx) ** 2 + (pz - bz) ** 2
        if d2 <= rng * rng:
            near.append((d2, x0, z0, x1, z1, piece[4]))
    near.sort(key=lambda t: t[0])
    del near[limit:]
    out = []
    y_base = -by
    for (d2, x0, z0, x1, z1, top) in reversed(near):        # far ones painted first
        y_top = (top if top is not None else WALL_H) - by
        if (x1 - x0) >= (z1 - z0):
            ends = ((x0, (z0 + z1) * 0.5), (x1, (z0 + z1) * 0.5))
        else:
            ends = (((x0 + x1) * 0.5, z0), ((x0 + x1) * 0.5, z1))
        mids = []
        gaps = []
        ok = True
        for (ex, ez) in ends:
            dx = ex - bx
            dz = ez - bz
            lo = _to_matcap(dx, y_base, dz, sin_e, cos_e)
            hi = _to_matcap(dx, y_top, dz, sin_e, cos_e)
            if lo is None or hi is None:
                ok = False
                break
            mids.append(((lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5))
            gaps.append(math.sqrt((hi[0] - lo[0]) ** 2 + (hi[1] - lo[1]) ** 2))
        if not ok:
            continue
        wdt = (gaps[0] + gaps[1]) * 0.5
        if wdt < ENV_MIN_W:
            wdt = ENV_MIN_W
        out.append((mids[0][0], mids[0][1], mids[1][0], mids[1][1], wdt))
    return out


# --- camera -----------------------------------------------------------------
CAM_ELEV = 66.0      # degrees above the board: mostly overhead, with enough lean to see wall sides
VIEW_W = 3.0         # units of board the follow camera keeps in frame...
VIEW_H = 2.25        # ...horizontally and vertically (smaller boards fit whole)
CULL_MARGIN = 2.0    # extra board drawn around the framed patch (tilt/perspective slack)


def fit_distance(w, h, fov_deg, aspect, elev_deg=CAM_ELEV, margin=0.86):
    """Camera distance (along its own forward axis) from which a w x h patch
    of board, centred on the target and rocking by MAX_TILT, fits inside
    +-margin of NDC. Bisected against the patch's bounding-box corners."""
    cx = w * 0.5
    cz = h * 0.5
    lift = math.sin(MAX_TILT) * 0.4 * max(cx, cz) + WALL_H + 0.5
    corners = [(x, y, z) for x in (-cx, cx) for y in (-HOLE_DEPTH - lift, lift) for z in (-cz, cz)]
    el = math.radians(elev_deg)
    dy = math.sin(el)
    dz = math.cos(el)
    fx, fy, fz = 0.0, -dy, -dz
    ux, uy, uz = 0.0, dz, -dy
    tan_v = math.tan(math.radians(fov_deg) * 0.5) * margin
    tan_h = tan_v * aspect

    def fits(d):
        ex, ey, ez = 0.0, dy * d, dz * d
        for (px, py, pz) in corners:
            vx, vy, vz = px - ex, py - ey, pz - ez
            depth = vx * fx + vy * fy + vz * fz
            if depth <= 0.1:
                return False
            if abs(vx) > tan_h * depth:
                return False
            if abs(vx * ux + vy * uy + vz * uz) > tan_v * depth:
                return False
        return True

    lo, hi = 1.0, 200.0
    for _ in range(24):
        mid = (lo + hi) * 0.5
        if fits(mid):
            hi = mid
        else:
            lo = mid
    return hi


def view_patch(level):
    """How much board the follow camera frames: the whole board if small,
    else a VIEW_W x VIEW_H window that tracks the ball."""
    return min(level.w, VIEW_W), min(level.h, VIEW_H)


def camera_target(level, x, z):
    """Where the follow camera should look: the ball, clamped so the framed
    patch never slides off the board (a board smaller than the patch is
    simply centred)."""
    vw, vh = view_patch(level)
    tx = min(max(x, vw * 0.5), level.w - vw * 0.5) if level.w > vw else level.w * 0.5
    tz = min(max(z, vh * 0.5), level.h - vh * 0.5) if level.h > vh else level.h * 0.5
    return tx, tz


def camera_eye(tx, ty, tz, dist, elev_deg=CAM_ELEV):
    el = math.radians(elev_deg)
    return tx, ty + math.sin(el) * dist, tz + math.cos(el) * dist


_CAM_SIN = math.sin(math.radians(CAM_ELEV))
_CAM_COS = math.cos(math.radians(CAM_ELEV))


def depth_key(x, y, z):
    """Painter's-order key for a point: SMALLER is further from the camera.

    With no depth buffer, draw order is the depth test, so everything is drawn
    back to front by this. The eye sits at target + (0, sin e, cos e) * dist and
    looks straight back down that line (camera_eye; the camera never yaws), so
    view depth is -(sin e * y + cos e * z) plus a constant - x does not enter it
    at all. At CAM_ELEV that weights y by %.3f and z by %.3f: a wall half a cell
    nearer in z beats one a whole wall-height taller, which is the ordering the
    2.5D view actually needs.

    The constant and the sign flip are dropped, so this is ASCENDING = back to
    front, and it is affine in y and z - which is why a level's static geometry
    can be sorted once and never resorted.
    """ % (_CAM_SIN, _CAM_COS)
    return _CAM_SIN * y + _CAM_COS * z


def visible(bbox, level, tx, tz):
    """Does a chunk/wall bounding box (x0, z0, x1, z1) overlap the framed patch?"""
    vw, vh = view_patch(level)
    hx = vw * 0.5 + CULL_MARGIN
    hz = vh * 0.5 + CULL_MARGIN
    return bbox[2] >= tx - hx and bbox[0] <= tx + hx and bbox[3] >= tz - hz and bbox[1] <= tz + hz


def fit_camera(level, fov_deg, aspect, elev_deg=CAM_ELEV, margin=0.86):
    """Whole-board framing (kept for tests and as a fallback): eye and target."""
    d = fit_distance(level.w, level.h, fov_deg, aspect, elev_deg, margin)
    cx = level.w * 0.5
    cz = level.h * 0.5
    return camera_eye(cx, 0.0, cz, d, elev_deg), (cx, 0.0, cz)


class Game:
    def __init__(self, levels=LEVELS, best=0.0):
        self.levels = levels
        self.best = best          # best total time over all levels, 0 = none yet
        self.save_pending = False
        self.new_game()

    # --- flow ---------------------------------------------------------------
    def new_game(self):
        self.level = 0
        self.lives = LIVES
        self.total_time = 0.0     # completed levels only; add level_time for live total
        self.gems_total = 0
        self.load_level()

    def load_level(self):
        self.cur = self.levels[self.level]
        self.level_time = 0.0
        self.tilt_x = 0.0
        self.tilt_z = 0.0
        self.collected = set()    # indices into cur.gems
        self.spawn()
        self.state = "intro"
        self.timer = 0.0

    def spawn(self):
        self.x, self.z = self.cur.start
        self.y = self.cur.height(self.x, self.z)   # terrain height under the ball
        self.drop = 0.0           # extra fall below the terrain while falling
        self.vx = 0.0
        self.vz = 0.0
        self.hit = 0.0            # impact speed of the latest wall hit (wiring reads + clears)
        self.event = None         # "gem" | "hit" | "fall" | "goal", latest one-shot event

    def restart_level(self):
        # B held: keeps lives, resets the clock for this level
        self.load_level()

    def live_total(self):
        return self.total_time + self.level_time

    def gems_left(self):
        return len(self.cur.gems) - len(self.collected)

    def message(self):
        if self.state == "intro":
            return self.cur.name if self.timer < INTRO_TIME * 0.65 else "GO!"
        if self.state == "play" and self.timer < GO_TIME:
            return "GO!"
        if self.state == "fell":
            return "FELL!" if self.lives > 1 else "OUT OF LIVES"
        if self.state == "goal":
            return "GOAL!"
        if self.state == "complete":
            return "COMPLETE"
        return None

    def fall_scale(self):
        """Ball scale while sinking (1 when not falling)."""
        if self.state != "fell":
            return 1.0
        k = 1.0 - self.timer / FALL_TIME
        return k if k > 0.05 else 0.05

    def ball_y(self):
        return self.y + BALL_RADIUS * self.fall_scale() - self.drop

    # --- per-frame ------------------------------------------------------------
    def step(self, dt, left, right, up, down):
        self.timer += dt
        self.event = None
        st = self.state
        if st == "intro":
            if self.timer >= INTRO_TIME:
                self.state = "play"
                self.timer = 0.0
            return
        if st == "fell":
            self.drop = 1.2 * (self.timer / FALL_TIME) ** 2
            self._ease_tilt(0.0, 0.0, dt)
            if self.timer >= FALL_TIME:
                self.lives -= 1
                if self.lives <= 0:
                    self.new_game()
                else:
                    self.spawn()
                    self.state = "play"
                    self.timer = GO_TIME
            return
        if st == "goal":
            self._ease_tilt(0.0, 0.0, dt)
            if self.timer >= GOAL_TIME:
                self.total_time += self.level_time
                if self.level + 1 < len(self.levels):
                    self.level += 1
                    self.load_level()
                else:
                    if self.best <= 0.0 or self.total_time < self.best:
                        self.best = self.total_time
                        self.save_pending = True
                    self.state = "complete"
                    self.timer = 0.0
            return
        if st == "complete":
            if self.timer >= COMPLETE_TIME:
                self.new_game()
            return

        # --- play ---
        self.level_time += dt
        tx = (MAX_TILT if down else 0.0) - (MAX_TILT if up else 0.0)
        tz = (MAX_TILT if left else 0.0) - (MAX_TILT if right else 0.0)
        self._ease_tilt(tx, tz, dt)

        # rotate_z(+) raises the +X side, rotate_x(+) lowers the +Z side; the
        # terrain slope adds its own downhill pull, so bumps cost momentum
        gx, gz = self.cur.gradient(self.x, self.z)
        self.vx += (-GRAVITY * math.sin(self.tilt_z) - GRAVITY * gx) * dt
        self.vz += (GRAVITY * math.sin(self.tilt_x) - GRAVITY * gz) * dt
        k = 1.0 - FRICTION * dt
        if k < 0.0:
            k = 0.0
        self.vx *= k
        self.vz *= k
        sp = math.sqrt(self.vx * self.vx + self.vz * self.vz)
        if sp > MAX_SPEED:
            self.vx *= MAX_SPEED / sp
            self.vz *= MAX_SPEED / sp

        self.x += self.vx * dt
        self.z += self.vz * dt
        self._collide_walls()

        if not self.cur.on_board(self.x, self.z):
            self._fall()
            return
        for (hx, hz) in self.cur.holes:
            dx = self.x - hx
            dz = self.z - hz
            if dx * dx + dz * dz < HOLE_CATCH * HOLE_CATCH:
                # snap to the centre so the sink animation lands in the dimple
                self.x = hx
                self.z = hz
                self.y = self.cur.height(hx, hz)
                self._fall()
                return
        self.y = self.cur.height(self.x, self.z)

        for n, (gx_, gz_) in enumerate(self.cur.gems):
            if n in self.collected:
                continue
            dx = self.x - gx_
            dz = self.z - gz_
            if dx * dx + dz * dz < GEM_CATCH * GEM_CATCH:
                self.collected.add(n)
                self.gems_total += 1
                self.level_time -= GEM_BONUS
                if self.level_time < 0.0:
                    self.level_time = 0.0
                self.event = "gem"
        gx_, gz_ = self.cur.goal
        dx = self.x - gx_
        dz = self.z - gz_
        if dx * dx + dz * dz < GOAL_CATCH * GOAL_CATCH:
            self.state = "goal"
            self.timer = 0.0
            self.vx = 0.0
            self.vz = 0.0
            self.event = "goal"

    def _ease_tilt(self, tx, tz, dt):
        a = TILT_RATE * dt
        if a > 1.0:
            a = 1.0
        self.tilt_x += (tx - self.tilt_x) * a
        self.tilt_z += (tz - self.tilt_z) * a

    def _fall(self):
        self.state = "fell"
        self.timer = 0.0
        self.vx = 0.0
        self.vz = 0.0
        self.event = "fall"

    def _collide_walls(self):
        """Circle-vs-rounded-rectangle against every wall slab: push the ball
        out along the footprint's distance-field gradient and reflect the
        normal velocity component."""
        r = BALL_RADIUS
        for (x0, z0, x1, z1) in self.cur.walls:
            # quick reject on the padded box
            if self.x < x0 - r or self.x > x1 + r or self.z < z0 - r or self.z > z1 + r:
                continue
            hx = (x1 - x0) * 0.5
            hz = (z1 - z0) * 0.5
            cr = min(WALL_R, hx, hz)
            px = self.x - (x0 + x1) * 0.5
            pz = self.z - (z0 + z1) * 0.5
            # signed distance to the rounded rectangle (inner box + radius)
            qx = abs(px) - (hx - cr)
            qz = abs(pz) - (hz - cr)
            ox = qx if qx > 0.0 else 0.0
            oz = qz if qz > 0.0 else 0.0
            outside = math.sqrt(ox * ox + oz * oz)
            inside = min(max(qx, qz), 0.0)
            d = outside + inside - cr
            if d >= r:
                continue
            # normal: from the nearest inner-box point outward, or the dominant
            # axis when the centre is inside the box
            if outside > 0.0:
                nx = ox / outside * (1.0 if px > 0.0 else -1.0)
                nz = oz / outside * (1.0 if pz > 0.0 else -1.0)
            elif qx > qz:
                nx = 1.0 if px > 0.0 else -1.0
                nz = 0.0
            else:
                nx = 0.0
                nz = 1.0 if pz > 0.0 else -1.0
            push = r - d
            self.x += nx * push
            self.z += nz * push
            vn = self.vx * nx + self.vz * nz
            if vn < 0.0:
                if -vn >= HIT_MIN:
                    self.hit = -vn
                    self.event = "hit"
                self.vx -= (1.0 + BOUNCE) * vn * nx
                self.vz -= (1.0 + BOUNCE) * vn * nz
