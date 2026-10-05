# Tamagotchi - a virtual pet for the Badgeware Tufty.
#
# The pet ages and its needs decay in real time, using the battery-backed RTC,
# so it keeps living while the badge is asleep, in another app, or switched off.
#
# Controls:
#   A / C   move the selection along the action bar
#   B       do the selected action (or confirm)
#   UP      stat sheet
#   DOWN    back / cancel
#   HOME    leave the app (progress is saved as you go)

import builtins
import math
import time

# ---------------------------------------------------------------------------
# Firmware compatibility
#
# Badgeware's API has moved on since some badges shipped. Newer builds expose
# ROM fonts as font.<name>, scale pixel text with a size argument, and add
# colour helpers like .lighten(); older ones have pixel_font.load(), no text
# scaling and no colour maths. This app sticks to the calls that are present on
# both, and shims the handful it needs, so it runs either way.
# ---------------------------------------------------------------------------

FONT_DIR = "/system/assets/fonts/"


def load_font(name):
  """A pixel font by name, however this firmware happens to provide it.

  The ROM collection is `rom_font` on shipped firmware and `font` on newer
  builds; either way it needs no file. Failing that, load the .ppf from the
  system font folder. `rom_font` is reached through `builtins` because it is
  injected at runtime and so isn't a name the linter knows about.
  """
  for library_name in ("rom_font", "font"):
    library = getattr(builtins, library_name, None)
    if library is not None:
      rom = getattr(library, name, None)
      if rom is not None:
        return rom

  path = FONT_DIR + name + ".ppf"
  loader = getattr(builtins, "pixel_font", None)
  if loader is not None:
    try:
      return loader.load(path)
    except OSError:
      pass
  return font.load(path)


def _frnd(limit=1.0):
  """frnd() is not on every build; rnd() is."""
  return rnd(0, 100000) * limit / 100000.0


def _ellipse_native(x, y, rx, ry):
  return shape.ellipse(x, y, rx, ry)


def _ellipse_polygon(x, y, rx, ry):
  points = []
  for i in range(20):
    a = math.pi * i / 10.0
    points.append(vec2(x + math.cos(a) * rx, y + math.sin(a) * ry))
  return shape.custom(points)


try:
  shape.ellipse(0, 0, 1, 1)
  _ellipse = _ellipse_native
except (NameError, AttributeError, TypeError):
  _ellipse = _ellipse_polygon


def pixel(x, y):
  screen.rectangle(int(x), int(y), 1, 1)


# Colours are held as plain (r, g, b) tuples so the app can shade them itself,
# rather than leaning on colour methods only newer firmware has.
def rgba(t, a=255):
  return color.rgb(int(t[0]), int(t[1]), int(t[2]), a)


def lighter(t, amount):
  return (t[0] + (255 - t[0]) * amount,
          t[1] + (255 - t[1]) * amount,
          t[2] + (255 - t[2]) * amount)


def blend(a, b, k):
  return (a[0] + (b[0] - a[0]) * k,
          a[1] + (b[1] - a[1]) * k,
          a[2] + (b[2] - a[2]) * k)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

try:
  badge.mode(LORES | VSYNC)        # 160 x 120, tear free, where supported
except (NameError, AttributeError, TypeError):
  pass

screen.antialias = image.X2

W = screen.width
H = screen.height

SAVE_NAME = "tamagotchi"

# ---------------------------------------------------------------------------
# Tuning - everything you would want to fiddle with lives here
# ---------------------------------------------------------------------------

# Life stages, and the age in seconds at which the pet reaches each one.
EGG, BABY, CHILD, TEEN, ADULT, ELDER = 0, 1, 2, 3, 4, 5
STAGE_AGE = (0, 2 * 60, 60 * 60, 6 * 3600, 24 * 3600, 72 * 3600)
STAGE_NAME = ("EGG", "BABY", "CHILD", "TEEN", "ADULT", "ELDER")

# Need decay, in points per hour (needs run 0-100, 100 being fully satisfied).
# Tuned so a well-fed pet comfortably survives a night, while one ignored
# completely gets into trouble after about half a day and dies after roughly one.
HUNGER_RATE = 6.0
HAPPY_RATE = 4.5
ENERGY_RATE = 5.5
ENERGY_REGEN = 26.0        # while asleep
CLEAN_RATE = 1.0           # doubled, tripled... for each poop left lying about

# Health responds to how well the other needs are being met.
HEALTH_DRAIN = 6.0
HEALTH_SICK = 4.5
HEALTH_REGEN = 8.0

POOP_PER_HOUR = 0.6        # chance of a poop each hour while awake
MAX_POOPS = 4
SICK_PER_HOUR = 0.25       # chance of falling ill each hour, while neglected

MAX_AWAY = 3 * 24 * 3600   # never simulate more than three days of absence
SAVE_EVERY = 60_000        # autosave interval in ms

# One hundred names, eight characters at most so "IT'S A <NAME>!" still fits
# across the 160px screen when the egg hatches.
NAMES = (
    "PIP", "BLOB", "NOODLE", "MOCHI", "SPUD", "WOTSIT", "GIZMO", "BEAN",
    "TOFU", "PIXEL", "SPROUT", "DUMPLING", "BISCUIT", "CRUMPET", "WAFFLE",
    "PICKLE", "GHERKIN", "SCAMP", "NUGGET", "TATER", "GNOCCHI", "RAVIOLI",
    "BUBBLE", "SQUISH", "WOBBLE", "JELLY", "PUDDING", "CUSTARD", "TRIFLE",
    "SCONE", "MUFFIN", "CRUMB", "TWIG", "PEBBLE", "ACORN", "CONKER",
    "TURNIP", "PARSNIP", "RADISH", "SPRIG", "MOSS", "FERN", "ZIGGY",
    "BODGE", "FIDGET", "WIDGET", "SPROCKET", "COG", "BOLT", "RIVET",
    "SOCKET", "GASKET", "NIBBLE", "BYTE", "KERNEL", "PATCH", "STACK",
    "CACHE", "BUFFER", "PIXIE", "GLITCH", "FUZZ", "BOOP", "BLIP",
    "PING", "ZAP", "FIZZ", "POP", "SNAP", "WHIRR", "CLICK", "BUZZ",
    "MARBLE", "DOODLE", "SCRIBBLE", "SMUDGE", "BLOT", "SPLAT", "DASH",
    "MUNCH", "SLURP", "CHOMP", "GOBBLE", "GULP", "TOAST", "CRISP",
    "WAFER", "HONEY", "MAPLE", "COCOA", "NOOT", "HONK", "SQUEAK",
    "CHIRP", "PEEP", "WARBLE", "GLOOP", "SLIME", "BLOOP", "COMET",
)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

BG_TOP_T = (38, 46, 78)
BG_BOTTOM_T = (22, 28, 48)
SKIN_T = (110, 216, 200)
HEART_T = (228, 88, 108)
SICK_T = (150, 180, 110)
GHOST_T = (90, 96, 110)

BG_TOP = rgba(BG_TOP_T)
BG_BOTTOM = rgba(BG_BOTTOM_T)
FLOOR = color.rgb(58, 68, 104)
PANEL = color.rgb(16, 22, 38)
INK = color.rgb(222, 238, 214)
WHITE = color.rgb(255, 255, 255)
DIM = color.rgb(120, 134, 168)
SKIN = rgba(SKIN_T)
SKIN_DARK = color.rgb(64, 158, 152)
BELLY = color.rgb(214, 248, 240)
BLUSH = color.rgb(232, 130, 150)
EGGSHELL = color.rgb(238, 232, 214)
EGGSPOT = color.rgb(198, 178, 140)
POOP = color.rgb(122, 84, 52)
HEART = rgba(HEART_T)
CUTOUT = PANEL          # icons punch holes back to the bar colour

GAUGE_T = ((228, 132, 72),     # hunger
           (232, 196, 88),     # happiness
           (122, 176, 238),    # energy
           (122, 214, 156))    # hygiene
GAUGE_COLORS = tuple(rgba(t) for t in GAUGE_T)

# ---------------------------------------------------------------------------
# Saved state
# ---------------------------------------------------------------------------


def fresh_pet(generation=1):
  return {
      "name": NAMES[rnd(len(NAMES) - 1)],
      "generation": generation,
      "born": now(),
      "last": now(),
      "stage": EGG,
      "hunger": 80.0,
      "happy": 80.0,
      "energy": 90.0,
      "clean": 100.0,
      "health": 100.0,
      "weight": 8.0,
      "poops": [],
      "sick": False,
      "asleep": False,
      "lights_off": False,
      "dead": False,
      "died_at": 0,
      "neglect": 0,
      "meals": 0,
      "games": 0,
      "wins": 0,
  }


def now():
  """Wall clock seconds. Survives resets thanks to the battery backed RTC."""
  try:
    return int(time.time())
  except (AttributeError, OSError, OverflowError, ValueError):
    return 0


pet = fresh_pet()
State.load(SAVE_NAME, pet)

# A save written by an older version may be missing newer keys.
for key, value in fresh_pet().items():
  if key not in pet:
    pet[key] = value

dirty = False
last_save = 0


def save():
  global dirty, last_save
  pet["last"] = now()
  State.save(SAVE_NAME, pet)
  dirty = False
  last_save = badge.ticks


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


def age():
  return max(0, now() - pet["born"])


def stage_for_age(seconds):
  stage = EGG
  for i in range(len(STAGE_AGE)):
    if seconds >= STAGE_AGE[i]:
      stage = i
  return stage


def step(dt):
  """Advance the simulation by dt seconds. Kept short so odds stay sane."""
  if pet["dead"] or dt <= 0:
    return

  hours = dt / 3600.0

  if pet["stage"] == EGG:
    if age() >= STAGE_AGE[BABY]:
      hatch()
    return

  asleep = pet["asleep"]

  pet["hunger"] = clamp(pet["hunger"] - HUNGER_RATE * (0.35 if asleep else 1.0) * hours, 0, 100)
  pet["happy"] = clamp(pet["happy"] - HAPPY_RATE * (0.3 if asleep else 1.0) * hours, 0, 100)

  if asleep:
    pet["energy"] = clamp(pet["energy"] + ENERGY_REGEN * hours, 0, 100)
  else:
    pet["energy"] = clamp(pet["energy"] - ENERGY_RATE * hours, 0, 100)

  pet["clean"] = clamp(pet["clean"] - CLEAN_RATE * (1 + len(pet["poops"])) * hours, 0, 100)

  # Poops arrive at random while the pet is awake and has eaten something.
  if not asleep and len(pet["poops"]) < MAX_POOPS:
    if _frnd() < POOP_PER_HOUR * hours * (0.3 + pet["hunger"] / 150.0):
      pet["poops"].append(rnd(24, W - 24))

  # Neglect makes illness likely.
  neglected = pet["hunger"] < 20 or pet["clean"] < 30 or len(pet["poops"]) >= MAX_POOPS
  if not pet["sick"] and neglected:
    if _frnd() < SICK_PER_HOUR * hours:
      pet["sick"] = True

  # Health follows from everything else.
  drain = 0.0
  if pet["hunger"] <= 0:
    drain += HEALTH_DRAIN
  if pet["happy"] <= 0:
    drain += HEALTH_DRAIN * 0.5
  if pet["clean"] < 15:
    drain += HEALTH_DRAIN * 0.5
  if pet["sick"]:
    drain += HEALTH_SICK

  if drain > 0:
    pet["health"] = clamp(pet["health"] - drain * hours, 0, 100)
    pet["neglect"] = pet["neglect"] + 1 if _frnd() < hours else pet["neglect"]
  elif pet["hunger"] > 50 and pet["happy"] > 50:
    pet["health"] = clamp(pet["health"] + HEALTH_REGEN * hours, 0, 100)

  # Sleep looks after itself: exhaustion knocks the pet out, a full battery
  # wakes it, and lights out keeps it under until you turn them back on.
  if pet["lights_off"]:
    pet["asleep"] = True
  elif pet["asleep"] and pet["energy"] >= 95:
    pet["asleep"] = False
  elif not pet["asleep"] and pet["energy"] <= 4:
    pet["asleep"] = True

  if pet["health"] <= 0:
    die()

  new_stage = stage_for_age(age())
  if new_stage > pet["stage"]:
    pet["stage"] = new_stage
    say("{} GREW UP!".format(pet["name"]), 2200)


def advance(seconds):
  """Run the simulation forward, in chunks, so a long absence behaves."""
  global dirty
  seconds = min(seconds, MAX_AWAY)
  while seconds > 0:
    chunk = min(seconds, 300)
    step(chunk)
    seconds -= chunk
  dirty = True


def hatch():
  pet["stage"] = BABY
  pet["hunger"] = 70.0
  pet["happy"] = 90.0
  set_mode("hatch")
  save()


def die():
  pet["dead"] = True
  pet["died_at"] = now()
  pet["asleep"] = False
  set_mode("dead")
  save()


def start_over():
  global pet
  pet = fresh_pet(pet["generation"] + 1)
  save()
  set_mode("main")


# ---------------------------------------------------------------------------
# Screen mode + banner plumbing
# ---------------------------------------------------------------------------

mode = "main"
mode_since = 0
message = None
message_until = 0
selected = 0

# Feed sub menu, mini game and the "eating" animation all keep a little state.
feed_choice = 0
game_round = 0
game_score = 0
game_phase = "ask"
game_phase_at = 0
game_guess = 0
game_answer = 0
anim = None
anim_until = 0


def set_mode(new_mode):
  global mode, mode_since
  mode = new_mode
  mode_since = badge.ticks


def mode_ticks():
  return badge.ticks - mode_since


def say(text, ms=1400):
  global message, message_until
  message = text
  message_until = badge.ticks + ms


def play_anim(name, ms):
  global anim, anim_until
  anim = name
  anim_until = badge.ticks + ms


def animating():
  return anim is not None and badge.ticks < anim_until


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

HEADER_H = 11
GAUGE_Y = 13
PLAY_TOP = 21
FLOOR_Y = 86
BAR_TOP = 90
ICON_Y = 100
HINT_Y = 112

TINY = load_font("ark")          # 6px
SMALL = load_font("sins")        # 7px
BODY = load_font("nope")         # 8px
BIG = load_font("absolute")      # 10px, bold


def draw_sky():
  """A banded gradient. Older firmware has no gradient brush, and at this size
  a handful of bands is indistinguishable from one anyway."""
  band = 6
  y = PLAY_TOP
  span = float(FLOOR_Y - PLAY_TOP)
  while y < FLOOR_Y:
    screen.pen = rgba(blend(BG_TOP_T, BG_BOTTOM_T, (y - PLAY_TOP) / span))
    screen.rectangle(0, y, W, band)
    y += band


def text_at(msg, x, y):
  screen.text(msg, int(x), int(y))


def text_center(msg, cx, y):
  w, _ = screen.measure_text(msg)
  screen.text(msg, int(cx - w / 2), int(y))


def text_right(msg, right, y):
  w, _ = screen.measure_text(msg)
  screen.text(msg, int(right - w), int(y))


# ---------------------------------------------------------------------------
# Little glyphs
# ---------------------------------------------------------------------------


def glyph_heart(cx, cy, s):
  screen.shape(shape.circle(cx - s * 0.42, cy - s * 0.28, s * 0.48))
  screen.shape(shape.circle(cx + s * 0.42, cy - s * 0.28, s * 0.48))
  screen.shape(shape.custom([vec2(cx - s * 0.86, cy - s * 0.1),
                             vec2(cx + s * 0.86, cy - s * 0.1),
                             vec2(cx, cy + s)]))


def glyph_apple(cx, cy, s):
  screen.shape(shape.circle(cx, cy + s * 0.15, s * 0.72))
  screen.shape(shape.line(cx, cy - s * 0.4, cx + s * 0.4, cy - s, 1))


def glyph_bolt(cx, cy, s):
  screen.shape(shape.custom([vec2(cx + s * 0.3, cy - s),
                             vec2(cx - s * 0.6, cy + s * 0.15),
                             vec2(cx - s * 0.05, cy + s * 0.15),
                             vec2(cx - s * 0.3, cy + s),
                             vec2(cx + s * 0.6, cy - s * 0.2),
                             vec2(cx + s * 0.05, cy - s * 0.2)]))


def glyph_drop(cx, cy, s):
  screen.shape(shape.circle(cx, cy + s * 0.3, s * 0.66))
  screen.shape(shape.custom([vec2(cx - s * 0.6, cy + s * 0.35),
                             vec2(cx + s * 0.6, cy + s * 0.35),
                             vec2(cx, cy - s)]))


# ---------------------------------------------------------------------------
# Gauges
# ---------------------------------------------------------------------------


def draw_bar(x, y, w, h, value, col_t):
  screen.pen = color.rgb(12, 16, 30)
  screen.rectangle(int(x), int(y), int(w), int(h))
  filled = int(w * clamp(value, 0, 100) / 100.0)
  if filled > 0:
    # Anything running low pulses, so an empty gauge is hard to miss.
    if value < 25 and round(badge.ticks / 300) % 2 == 0:
      screen.pen = rgba(lighter(col_t, 0.35))
    else:
      screen.pen = rgba(col_t)
    screen.rectangle(int(x), int(y), filled, int(h))


GAUGES = (glyph_apple, glyph_heart, glyph_bolt, glyph_drop)


def draw_gauges():
  screen.pen = PANEL
  screen.rectangle(0, HEADER_H, W, PLAY_TOP - HEADER_H)

  values = (pet["hunger"], pet["happy"], pet["energy"], pet["clean"])
  cell = W / 4.0
  for i in range(4):
    x = i * cell
    screen.pen = GAUGE_COLORS[i]
    GAUGES[i](x + 6, GAUGE_Y + 3, 3)
    draw_bar(x + 12, GAUGE_Y + 1, cell - 16, 5, values[i], GAUGE_T[i])


def draw_header():
  screen.pen = PANEL
  screen.rectangle(0, 0, W, HEADER_H)

  screen.font = BODY
  screen.pen = INK
  text_at(pet["name"], 3, 2)

  # Health, as a heart that empties as the pet fails.
  hx = W - 8
  health = pet["health"]
  screen.pen = color.rgb(80, 40, 52)
  glyph_heart(hx, 5, 4)
  if health > 0:
    # A smaller heart inside the dark one, so it shrinks as health drains.
    # (Clipping a slice would be nicer, but screen.clip isn't on every build.)
    if health > 30 or round(badge.ticks / 250) % 2 == 0:
      screen.pen = HEART
    else:
      screen.pen = rgba(lighter(HEART_T, 0.4))
    glyph_heart(hx, 5, 4 * (0.4 + 0.6 * health / 100.0))

  screen.font = TINY
  screen.pen = DIM
  text_right(age_text(), W - 15, 3)


def age_text():
  seconds = age()
  if pet["dead"]:
    return "RIP"
  if seconds < 3600:
    return "{}m".format(seconds // 60)
  if seconds < 24 * 3600:
    return "{}h".format(seconds // 3600)
  return "{}d".format(seconds // 86400)


# ---------------------------------------------------------------------------
# The pet
# ---------------------------------------------------------------------------

# stage -> (body radius x, body radius y, eye spacing, eye radius)
BODY_SHAPE = {
    BABY: (13, 11, 5.0, 3.0),
    CHILD: (17, 15, 6.0, 3.4),
    TEEN: (19, 18, 7.0, 3.6),
    ADULT: (22, 21, 8.0, 4.0),
    ELDER: (22, 20, 8.0, 3.8),
}


def mood():
  if pet["dead"]:
    return "dead"
  if pet["asleep"]:
    return "asleep"
  if pet["sick"]:
    return "sick"
  if pet["hunger"] < 25 or pet["happy"] < 25 or pet["clean"] < 25 or pet["health"] < 40:
    return "sad"
  if pet["happy"] > 70 and pet["hunger"] > 50:
    return "happy"
  return "ok"


def pet_base_y():
  """Body centre that puts the pet's feet on the floor, whatever size it is."""
  if pet["stage"] == EGG:
    return FLOOR_Y - 21
  ry = BODY_SHAPE[pet["stage"]][1]
  return FLOOR_Y - ry * 1.12


def draw_shadow(cx, rx):
  screen.pen = color.rgb(0, 0, 0, 90)
  screen.shape(_ellipse(cx, FLOOR_Y + 1, rx * 0.85, 3))


def draw_egg(cx, cy):
  # The egg rocks a little, and rocks harder as hatching approaches.
  left = max(0, STAGE_AGE[BABY] - age())
  urgency = 1.0 - clamp(left / float(STAGE_AGE[BABY]), 0, 1)
  tilt = math.sin(badge.ticks / (260.0 - 140.0 * urgency)) * (3 + 9 * urgency)

  draw_shadow(cx, 16)

  egg = _ellipse(0, 0, 15, 19)
  egg.transform = mat3().translate(cx, cy + 2).rotate(tilt)
  screen.pen = EGGSHELL
  screen.shape(egg)

  screen.pen = EGGSPOT
  for i in range(3):
    spot = shape.circle(0, 0, 3 - i * 0.4)
    spot.transform = mat3().translate(cx, cy + 2).rotate(tilt).translate(-6 + i * 7, -4 + i * 8)
    screen.shape(spot)

  # A crack opens up over the last quarter of the wait.
  if urgency > 0.75:
    screen.pen = color.rgb(150, 140, 120)
    seam = ((-8, -4), (-3, 0), (-6, 3), (2, 6), (0, 1), (5, -2))
    m = mat3().translate(cx, cy + 2).rotate(tilt)
    for i in range(len(seam) - 1):
      segment = shape.line(seam[i][0], seam[i][1], seam[i + 1][0], seam[i + 1][1], 1)
      segment.transform = m
      screen.shape(segment)


def draw_eyes(cx, cy, edx, er, m, look):
  closed = m in ("asleep", "dead")
  blink = (badge.ticks % 3600) < 150

  for side in (-1, 1):
    ex = cx + side * edx
    if closed or blink:
      screen.pen = color.rgb(24, 28, 44)
      screen.shape(shape.line(ex - er, cy, ex + er, cy, 1.6))
    elif m == "dead":
      pass
    else:
      screen.pen = WHITE
      screen.shape(shape.circle(ex, cy, er))
      screen.pen = color.rgb(24, 28, 44)
      screen.shape(shape.circle(ex + look * er * 0.35, cy + er * 0.1, er * 0.55))
      screen.pen = WHITE
      screen.shape(shape.circle(ex + look * er * 0.35 - er * 0.22, cy - er * 0.2, er * 0.18))


def draw_mouth(cx, my, m):
  screen.pen = color.rgb(24, 28, 44)
  if m == "happy":
    screen.shape(shape.arc(cx, my - 1, 3.2, 4.6, 120, 240))
  elif m == "sad":
    screen.shape(shape.arc(cx, my + 5, 3.2, 4.6, 300, 420))
  elif m == "sick":
    screen.shape(shape.circle(cx, my + 1, 2.2))
  elif m == "asleep":
    screen.shape(shape.arc(cx, my - 1, 2.0, 3.2, 120, 240))
  elif m == "dead":
    screen.shape(shape.line(cx - 3, my, cx + 3, my, 1.4))
  else:
    screen.shape(shape.line(cx - 2.5, my, cx + 2.5, my, 1.4))


def draw_ears(cx, cy, rx, ry, stage, wobble):
  screen.pen = SKIN_DARK
  if stage == BABY:
    # A single springy antenna.
    tip = vec2(cx + wobble * 2, cy - ry - 8)
    screen.shape(shape.line(cx, cy - ry * 0.9, tip.x, tip.y, 1.6))
    screen.shape(shape.circle(tip.x, tip.y, 2.4))
  elif stage in (CHILD, ELDER):
    for side in (-1, 1):
      screen.shape(shape.circle(cx + side * rx * 0.72, cy - ry * 0.78, rx * 0.3))
  else:
    for side in (-1, 1):
      base = vec2(cx + side * rx * 0.55, cy - ry * 0.75)
      screen.shape(shape.custom([vec2(base.x - side * 4, base.y + 2),
                                 vec2(base.x + side * 5, base.y + 1),
                                 vec2(base.x + side * 2 + wobble, base.y - 11)]))


def draw_pet(cx, cy):
  stage = pet["stage"]
  if stage == EGG:
    draw_egg(cx, cy)
    return

  rx, ry, edx, er = BODY_SHAPE[stage]
  m = mood()
  t = badge.ticks

  if m == "asleep":
    bob = math.sin(t / 900.0) * 1.2
  elif m == "happy":
    bob = abs(math.sin(t / 320.0)) * -4.0
  elif m == "sad":
    bob = math.sin(t / 700.0) * 0.8 + 2
  else:
    bob = math.sin(t / 480.0) * 1.5

  cy = cy + bob
  wobble = math.sin(t / 300.0) * 1.5
  look = math.sin(t / 1100.0)

  draw_shadow(cx, rx * (1.15 if m == "happy" else 1.0))
  draw_ears(cx, cy, rx, ry, stage, wobble)

  skin_t = SKIN_T
  if m == "sick":
    skin_t = blend(SKIN_T, SICK_T, 0.55)
  elif m == "dead":
    skin_t = blend(SKIN_T, GHOST_T, 0.7)
  skin = rgba(skin_t)

  # Feet, tucked behind the body.
  screen.pen = SKIN_DARK
  for side in (-1, 1):
    screen.shape(_ellipse(cx + side * rx * 0.45, cy + ry * 0.94, rx * 0.3, ry * 0.2))

  # Arms appear once the pet has grown a bit, and wave when it is pleased.
  if stage >= TEEN:
    lift = -6 if m == "happy" else 0
    for side in (-1, 1):
      screen.shape(_ellipse(cx + side * rx * 0.95, cy + ry * 0.2 + lift,
                                 rx * 0.22, ry * 0.16))

  screen.pen = skin
  screen.shape(_ellipse(cx, cy, rx, ry))

  screen.pen = BELLY
  screen.shape(_ellipse(cx, cy + ry * 0.36, rx * 0.55, ry * 0.44))

  screen.pen = rgba(lighter(skin_t, 0.18))
  screen.shape(_ellipse(cx - rx * 0.3, cy - ry * 0.5, rx * 0.3, ry * 0.18))

  eye_y = cy - ry * 0.16
  draw_eyes(cx, eye_y, edx, er, m, look)
  draw_mouth(cx, eye_y + er + 4, m)

  if m == "happy":
    screen.pen = BLUSH
    for side in (-1, 1):
      screen.shape(_ellipse(cx + side * (edx + er + 2), eye_y + er, 2.6, 1.6))

  if stage == ELDER:
    screen.pen = color.rgb(230, 236, 244)
    for side in (-1, 1):
      screen.shape(shape.line(cx + side * (edx + er * 0.4), eye_y - er - 3,
                              cx + side * (edx - er * 0.6), eye_y - er - 2, 1.2))

  if m == "sick":
    # A little red cross bobbing over the pet's head.
    mx = cx + rx * 0.55
    my = cy - ry - 9 + math.sin(t / 400.0) * 1.5
    screen.pen = color.rgb(228, 88, 108)
    screen.shape(shape.rectangle(mx - 4, my - 1.5, 8, 3))
    screen.shape(shape.rectangle(mx - 1.5, my - 4, 3, 8))

  if m == "asleep" and not pet["lights_off"]:
    draw_zzz(cx + rx * 0.8, cy - ry)


def draw_zzz(x, y):
  for i in range(3):
    phase = ((badge.ticks / 12.0) + i * 40) % 120
    alpha = int(255 * (1.0 - phase / 120.0))
    # A bigger font for the last one, since pixel text can't always be scaled.
    screen.font = BIG if i == 2 else SMALL
    screen.pen = color.rgb(255, 255, 255, alpha)
    text_at("z", x + phase * 0.12, y - phase * 0.22)


def draw_poops():
  screen.pen = POOP
  for i in range(len(pet["poops"])):
    x = pet["poops"][i]
    screen.shape(_ellipse(x, FLOOR_Y - 1, 6, 2.6))
    screen.shape(_ellipse(x, FLOOR_Y - 4, 4.4, 2.4))
    screen.shape(_ellipse(x, FLOOR_Y - 7, 2.8, 2.2))
    # A fly, buzzing about, because of course there is.
    screen.pen = color.rgb(200, 210, 220)
    fx = x + math.sin((badge.ticks + i * 700) / 240.0) * 9
    fy = FLOOR_Y - 12 + math.sin((badge.ticks + i * 400) / 130.0) * 3
    pixel(fx, fy)
    screen.pen = POOP


# ---------------------------------------------------------------------------
# Action bar
# ---------------------------------------------------------------------------


def icon_feed(cx, cy, col):
  screen.pen = col
  screen.shape(shape.pie(cx, cy + 1, 7, 90, 270))
  screen.shape(shape.rectangle(cx - 8, cy - 1, 16, 2))
  screen.shape(shape.circle(cx, cy - 5, 2.4))


def icon_play(cx, cy, col):
  screen.pen = col
  screen.shape(shape.circle(cx, cy, 7).stroke(1.6))
  screen.shape(shape.arc(cx, cy, 6, 7.4, 200, 340))
  screen.shape(shape.circle(cx, cy, 1.8))


def icon_clean(cx, cy, col):
  screen.pen = col
  glyph_drop(cx - 1, cy, 5)
  screen.shape(shape.star(cx + 6, cy - 5, 4, 3.2, 1.0))


def icon_meds(cx, cy, col):
  screen.pen = col
  pill = shape.rounded_rectangle(-8, -3.5, 16, 7, 3.5)
  pill.transform = mat3().translate(cx, cy).rotate(-40)
  screen.shape(pill)
  screen.pen = CUTOUT
  line = shape.rectangle(-0.8, -3.5, 1.6, 7)
  line.transform = mat3().translate(cx, cy).rotate(-40)
  screen.shape(line)


def icon_light(cx, cy, col):
  screen.pen = col
  if pet["lights_off"]:
    screen.shape(shape.circle(cx + 1, cy, 7))
    screen.pen = CUTOUT
    screen.shape(shape.circle(cx + 4.5, cy - 2, 6))
  else:
    screen.shape(shape.circle(cx, cy, 4))
    for i in range(8):
      a = i * math.pi / 4
      screen.shape(shape.line(cx + math.sin(a) * 5.5, cy - math.cos(a) * 5.5,
                              cx + math.sin(a) * 7.5, cy - math.cos(a) * 7.5, 1.4))


def icon_info(cx, cy, col):
  screen.pen = col
  screen.shape(shape.rounded_rectangle(cx - 6, cy - 7, 12, 14, 2).stroke(1.4))
  for i in range(3):
    screen.shape(shape.rectangle(cx - 3, cy - 4 + i * 4, 6 - i * 2, 1.4))


ACTIONS = ("FEED", "PLAY", "CLEAN", "MEDS", "LIGHT", "INFO")
ICONS = (icon_feed, icon_play, icon_clean, icon_meds, icon_light, icon_info)
CELL = W / len(ACTIONS)


def draw_action_bar():
  screen.pen = PANEL
  screen.rectangle(0, BAR_TOP, W, H - BAR_TOP)
  screen.pen = color.rgb(40, 50, 78)
  screen.rectangle(0, BAR_TOP, W, 1)

  for i in range(len(ACTIONS)):
    cx = CELL * (i + 0.5)
    on = i == selected
    ICONS[i](cx, ICON_Y + (-1 if on else 0), INK if on else DIM)
    if on:
      screen.pen = color.rgb(118, 148, 210)
      screen.shape(shape.rounded_rectangle(cx - 12, ICON_Y - 11, 24, 21, 5).stroke(1))

  screen.font = TINY
  screen.pen = DIM
  text_at("<A", 2, HINT_Y + 1)
  text_right("C>", W - 2, HINT_Y + 1)
  screen.pen = INK
  text_center("B  " + ACTIONS[selected], W / 2, HINT_Y)


def draw_scene(pet_x=None, pet_y=None):
  draw_sky()

  screen.pen = FLOOR
  screen.rectangle(0, FLOOR_Y, W, 3)
  screen.pen = color.rgb(46, 56, 88)
  screen.rectangle(0, FLOOR_Y + 3, W, BAR_TOP - FLOOR_Y - 3)

  px = W / 2 if pet_x is None else pet_x
  py = pet_base_y() if pet_y is None else pet_y

  draw_poops()
  draw_pet(px, py)

  if pet["lights_off"]:
    screen.pen = color.rgb(0, 0, 0, 165)
    screen.rectangle(0, PLAY_TOP, W, BAR_TOP - PLAY_TOP)
    # Redraw the Zzz on top, so it stays readable through the darkness.
    if pet["asleep"] and pet["stage"] != EGG:
      rx, ry, _, _ = BODY_SHAPE[pet["stage"]]
      draw_zzz(px + rx * 0.8, py - ry)

  draw_effects()


def draw_effects():
  if not animating():
    return
  left = anim_until - badge.ticks
  cx = W / 2

  if anim in ("eat", "snack"):
    gone = 1.0 - clamp(left / 1400.0, 0, 1)
    if anim == "snack":
      screen.pen = color.rgb(238, 150, 180)
      remaining = 1.0 - gone
      screen.shape(shape.circle(cx + 26, FLOOR_Y - 8, 5 * remaining + 0.5))
      screen.pen = color.rgb(120, 84, 60)
      screen.shape(shape.rectangle(cx + 25, FLOOR_Y - 6, 2, 6))
    else:
      screen.pen = color.rgb(214, 224, 236)
      screen.shape(shape.pie(cx + 26, FLOOR_Y - 4, 8, 90, 270))
      full = max(0.0, 1.0 - gone)
      if full > 0.05:
        screen.pen = color.rgb(228, 132, 72)
        screen.shape(_ellipse(cx + 26, FLOOR_Y - 5, 6 * full, 3 * full))
  elif anim == "clean":
    for i in range(6):
      p = ((badge.ticks / 6.0) + i * 26) % 160
      screen.pen = color.rgb(140, 220, 255, 200)
      screen.shape(shape.circle(p, PLAY_TOP + 10 + (i % 3) * 18, 2.2))
  elif anim == "med":
    y = FLOOR_Y - 30 - left * 0.03
    screen.pen = color.rgb(240, 240, 250)
    pill = shape.rounded_rectangle(-6, -2.5, 12, 5, 2.5)
    pill.transform = mat3().translate(cx + 24, y).rotate(-30)
    screen.shape(pill)
  elif anim == "cheer":
    for i in range(7):
      a = (badge.ticks / 3.0 + i * 51) % 360
      r = 22 + (1.0 - clamp(left / 1200.0, 0, 1)) * 26
      screen.pen = GAUGE_COLORS[i % 4]
      screen.shape(shape.star(cx + math.sin(math.radians(a)) * r,
                              FLOOR_Y - 26 - math.cos(math.radians(a)) * r * 0.6,
                              5, 3.4, 1.4))


def draw_banner():
  if message is None or badge.ticks > message_until:
    return
  screen.font = SMALL
  w, h = screen.measure_text(message)
  bw, bh = w + 12, h + 7
  bx, by = (W - bw) / 2, PLAY_TOP + 3
  screen.pen = color.rgb(12, 16, 30, 225)
  screen.shape(shape.rounded_rectangle(bx, by, bw, bh, 4))
  screen.pen = color.rgb(90, 108, 150)
  screen.shape(shape.rounded_rectangle(bx, by, bw, bh, 4).stroke(1))
  screen.pen = INK
  text_center(message, W / 2, by + 4)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def do_action(index):
  global dirty
  action = ACTIONS[index]

  if action == "INFO":
    set_mode("stats")
    return

  if pet["dead"]:
    say("{} IS GONE...".format(pet["name"]))
    return

  if pet["stage"] == EGG:
    say("STILL AN EGG!")
    return

  if pet["asleep"] and action != "LIGHT":
    say("SHHH - ASLEEP")
    return

  if action == "FEED":
    set_mode("feed")
  elif action == "PLAY":
    if pet["energy"] < 15:
      say("TOO TIRED")
    else:
      start_game()
  elif action == "CLEAN":
    if pet["poops"]:
      pet["poops"] = []
      pet["clean"] = 100.0
      say("SPARKLING!")
    elif pet["clean"] < 98:
      pet["clean"] = clamp(pet["clean"] + 30, 0, 100)
      say("SCRUB SCRUB")
    else:
      say("ALREADY CLEAN")
    play_anim("clean", 1200)
    dirty = True
    save()
  elif action == "MEDS":
    if pet["sick"]:
      pet["sick"] = False
      pet["health"] = clamp(pet["health"] + 18, 0, 100)
      pet["happy"] = clamp(pet["happy"] - 4, 0, 100)
      say("ALL BETTER!")
      play_anim("med", 1300)
      save()
    else:
      say("NOT SICK")
  elif action == "LIGHT":
    pet["lights_off"] = not pet["lights_off"]
    if pet["lights_off"]:
      pet["asleep"] = True
      say("LIGHTS OUT")
    else:
      if pet["energy"] < 85:
        pet["happy"] = clamp(pet["happy"] - 8, 0, 100)
        say("...GRUMPY!")
      else:
        say("GOOD MORNING")
      pet["asleep"] = False
    save()


def feed(kind):
  if kind == 0:
    if pet["hunger"] > 92:
      say("NOT HUNGRY")
      set_mode("main")
      return
    pet["hunger"] = clamp(pet["hunger"] + 32, 0, 100)
    pet["weight"] += 2
    pet["meals"] += 1
    say("YUM!")
    play_anim("eat", 1400)
  else:
    pet["hunger"] = clamp(pet["hunger"] + 8, 0, 100)
    pet["happy"] = clamp(pet["happy"] + 14, 0, 100)
    pet["weight"] += 4
    say("TREAT!")
    play_anim("snack", 1200)
  set_mode("main")
  save()


# ---------------------------------------------------------------------------
# The guessing game
# ---------------------------------------------------------------------------


def start_game():
  global game_round, game_score, game_phase, game_phase_at
  game_round = 0
  game_score = 0
  game_phase = "ask"
  game_phase_at = badge.ticks
  set_mode("game")


def finish_game():
  pet["games"] += 1
  if game_score >= 2:
    pet["wins"] += 1
  pet["happy"] = clamp(pet["happy"] + 6 + game_score * 9, 0, 100)
  pet["energy"] = clamp(pet["energy"] - 7, 0, 100)
  pet["hunger"] = clamp(pet["hunger"] - 4, 0, 100)
  pet["weight"] = max(4.0, pet["weight"] - game_score * 0.6)
  if game_score >= 2:
    say("WON {}/3 - HOORAY!".format(game_score), 2000)
    play_anim("cheer", 1200)
  else:
    say("WON {}/3".format(game_score), 2000)
  set_mode("main")
  save()


def game_mode():
  global game_phase, game_phase_at, game_guess, game_answer, game_round, game_score

  t = badge.ticks - game_phase_at
  base = pet_base_y()
  px, py = W / 2, base

  if game_phase == "jump":
    p = clamp(t / 500.0, 0, 1)
    px = W / 2 + game_answer * 36 * math.sin(p * math.pi / 2)
    py = base - math.sin(p * math.pi) * 14
    if p >= 1:
      game_phase = "result"
      game_phase_at = badge.ticks
      if game_guess == game_answer:
        game_score += 1
  elif game_phase == "result":
    px = W / 2 + game_answer * 36
    if t > 900:
      game_round += 1
      if game_round >= 3:
        finish_game()
        return
      game_phase = "ask"
      game_phase_at = badge.ticks

  draw_header()
  draw_gauges()
  draw_scene(px, py)

  screen.pen = PANEL
  screen.rectangle(0, BAR_TOP, W, H - BAR_TOP)

  screen.font = SMALL
  if game_phase == "ask":
    screen.pen = INK
    text_center("WHICH WAY?", W / 2, BAR_TOP + 3)
    screen.font = TINY
    screen.pen = DIM
    text_at("<A LEFT", 3, HINT_Y + 1)
    text_right("RIGHT C>", W - 3, HINT_Y + 1)
  else:
    screen.font = BIG
    screen.pen = INK if game_guess == game_answer else DIM
    text_center("YES!" if game_guess == game_answer else "NOPE", W / 2, BAR_TOP + 3)
    screen.font = TINY
    screen.pen = DIM
    text_center("ROUND {}/3  SCORE {}".format(game_round + 1, game_score), W / 2, HINT_Y + 1)

  draw_banner()

  if game_phase == "ask":
    guess = 0
    if badge.pressed(BUTTON_A):
      guess = -1
    elif badge.pressed(BUTTON_C):
      guess = 1
    if guess:
      game_guess = guess
      game_answer = -1 if rnd(1) == 0 else 1
      game_phase = "jump"
      game_phase_at = badge.ticks
    elif badge.pressed(BUTTON_DOWN):
      set_mode("main")


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------


def main_mode():
  global selected

  draw_header()
  draw_gauges()
  draw_scene()
  draw_action_bar()
  draw_banner()

  if badge.pressed(BUTTON_A):
    selected = (selected - 1) % len(ACTIONS)
  if badge.pressed(BUTTON_C):
    selected = (selected + 1) % len(ACTIONS)
  if badge.pressed(BUTTON_UP):
    set_mode("stats")
  if badge.pressed(BUTTON_B):
    do_action(selected)


def feed_mode():
  global feed_choice

  draw_header()
  draw_gauges()
  draw_scene()

  screen.pen = color.rgb(0, 0, 0, 150)
  screen.rectangle(0, PLAY_TOP, W, BAR_TOP - PLAY_TOP)

  screen.pen = PANEL
  screen.rectangle(0, BAR_TOP, W, H - BAR_TOP)

  options = ("MEAL", "SNACK")
  for i in range(2):
    cx = W * (0.28 + i * 0.44)
    on = i == feed_choice
    if on:
      screen.pen = color.rgb(118, 148, 210)
      screen.shape(shape.rounded_rectangle(cx - 26, 42, 52, 34, 5).stroke(1))
    screen.pen = INK if on else DIM
    if i == 0:
      icon_feed(cx, 54, INK if on else DIM)
    else:
      screen.shape(shape.circle(cx, 52, 5))
      screen.shape(shape.rectangle(cx - 1, 54, 2, 7))
    screen.font = TINY
    screen.pen = INK if on else DIM
    text_center(options[i], cx, 66)

  screen.font = TINY
  screen.pen = DIM
  text_at("<A", 2, HINT_Y + 1)
  text_right("C>", W - 2, HINT_Y + 1)
  screen.pen = INK
  text_center("B FEED   DOWN BACK", W / 2, HINT_Y + 1)

  draw_banner()

  if badge.pressed(BUTTON_A) or badge.pressed(BUTTON_C):
    feed_choice = 1 - feed_choice
  if badge.pressed(BUTTON_B):
    feed(feed_choice)
  if badge.pressed(BUTTON_DOWN):
    set_mode("main")


STAT_ROWS = (("FOOD", "hunger"), ("FUN", "happy"), ("ENERGY", "energy"),
             ("HYGIENE", "clean"), ("HEALTH", "health"))


def stats_mode():
  screen.pen = BG_BOTTOM
  screen.clear()

  screen.pen = PANEL
  screen.rectangle(0, 0, W, HEADER_H)
  screen.font = BODY
  screen.pen = INK
  text_at(pet["name"], 3, 2)
  screen.font = TINY
  screen.pen = DIM
  text_right("GEN {}".format(pet["generation"]), W - 3, 3)

  screen.font = TINY
  y = 15
  for i in range(len(STAT_ROWS)):
    label, key = STAT_ROWS[i]
    screen.pen = DIM
    text_at(label, 4, y)
    col = GAUGE_T[i] if i < 4 else HEART_T
    draw_bar(52, y, 74, 5, pet[key], col)
    screen.pen = INK
    text_right("{}".format(int(pet[key])), W - 4, y)
    y += 10

  screen.pen = color.rgb(40, 50, 78)
  screen.rectangle(4, y + 1, W - 8, 1)
  y += 6

  facts = (
      ("STAGE", STAGE_NAME[pet["stage"]]),
      ("AGE", long_age_text()),
      ("WEIGHT", "{}g".format(int(pet["weight"]))),
      ("MEALS", "{}".format(pet["meals"])),
      ("GAMES", "{} WON / {}".format(pet["wins"], pet["games"])),
  )
  for label, value in facts:
    screen.pen = DIM
    text_at(label, 4, y)
    screen.pen = INK
    text_right(value, W - 4, y)
    y += 8

  screen.pen = PANEL
  screen.rectangle(0, HINT_Y - 2, W, H - HINT_Y + 2)
  screen.pen = DIM
  status = "SICK!" if pet["sick"] else ("ASLEEP" if pet["asleep"] else "AWAKE")
  text_at(status, 3, HINT_Y + 1)
  text_right("B / DOWN BACK", W - 3, HINT_Y + 1)

  if badge.pressed(BUTTON_B) or badge.pressed(BUTTON_DOWN) or badge.pressed(BUTTON_UP):
    set_mode("main")


def long_age_text():
  seconds = age()
  days = seconds // 86400
  hours = (seconds % 86400) // 3600
  minutes = (seconds % 3600) // 60
  if days:
    return "{}d {}h".format(days, hours)
  if hours:
    return "{}h {}m".format(hours, minutes)
  return "{}m".format(minutes)


def hatch_mode():
  draw_header()
  draw_gauges()
  draw_scene()

  screen.pen = PANEL
  screen.rectangle(0, BAR_TOP, W, H - BAR_TOP)
  screen.font = BIG
  screen.pen = INK
  text_center("IT'S A {}!".format(pet["name"]), W / 2, BAR_TOP + 5)

  # Confetti for the new arrival.
  for i in range(10):
    p = ((badge.ticks - mode_since) / 6.0 + i * 37) % 90
    screen.pen = GAUGE_COLORS[i % 4]
    screen.shape(shape.rectangle(12 + i * 14, PLAY_TOP + p * 0.7, 2, 3))

  if mode_ticks() > 2600 or badge.pressed(BUTTON_B):
    set_mode("main")


def dead_mode():
  screen.pen = BG_BOTTOM
  screen.clear()
  draw_header()

  screen.pen = color.rgb(96, 104, 128)
  screen.shape(shape.rounded_rectangle(W / 2 - 18, 34, 36, 46, 16))
  screen.pen = color.rgb(64, 72, 94)
  screen.shape(shape.rectangle(W / 2 - 2, 44, 4, 22))
  screen.shape(shape.rectangle(W / 2 - 9, 51, 18, 4))

  screen.font = TINY
  screen.pen = color.rgb(180, 190, 210)
  text_center("RIP", W / 2, 38)
  text_center(pet["name"], W / 2, 68)

  screen.pen = DIM
  text_center("LIVED {}".format(long_age_text()), W / 2, 84)
  text_center("GEN {}  -  {} MEALS".format(pet["generation"], pet["meals"]), W / 2, 92)

  screen.pen = PANEL
  screen.rectangle(0, HINT_Y - 3, W, H - HINT_Y + 3)
  screen.pen = INK
  text_center("HOLD B FOR A NEW EGG", W / 2, HINT_Y)

  progress = hold_progress()
  if progress > 0:
    screen.pen = color.rgb(122, 214, 156)
    screen.rectangle(0, HINT_Y - 3, int(W * clamp(progress, 0, 1)), 2)

  draw_banner()


hold_since = None


def hold_progress():
  global hold_since
  if badge.held(BUTTON_B):
    if hold_since is None:
      hold_since = badge.ticks
    progress = (badge.ticks - hold_since) / 1200.0
    if progress >= 1.0:
      hold_since = None
      start_over()
      return 0.0
    return progress
  hold_since = None
  return 0.0


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

MODES = {
    "main": main_mode,
    "feed": feed_mode,
    "game": game_mode,
    "stats": stats_mode,
    "hatch": hatch_mode,
    "dead": dead_mode,
}


def catch_up():
  """Bring the pet forward to the present, however long we have been away."""
  wall = now()
  gap = wall - pet["last"]
  if gap >= 1:
    advance(gap)
    pet["last"] = wall
  elif gap < 0:
    # The clock went backwards - an RTC that lost its battery, or a fresh badge
    # that has never had the time set. Re-anchor rather than freeze forever.
    pet["last"] = wall


def update():
  catch_up()

  # A pet that died while we weren't looking gets its own screen.
  if pet["dead"] and mode not in ("dead", "stats"):
    set_mode("dead")

  MODES.get(mode, main_mode)()

  if dirty and badge.ticks - last_save > SAVE_EVERY:
    save()


# On the very first run there is nothing saved and no clock history, so start
# the pet's life from this moment rather than from the epoch.
if pet["last"] <= 0 or pet["born"] <= 0:
  pet["born"] = now()
  pet["last"] = now()
  save()

if pet["dead"]:
  set_mode("dead")

run(update)
