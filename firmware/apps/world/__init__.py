import json
import os
import sys
import time

# standalone app bootstrap
os.chdir("/system/apps/world")
sys.path.insert(0, "/system/apps/world")

badge.mode(HIRES)

coastlines = []
path_count, point_count = 0, 0


def load_coastlines():
  global path_count, point_count

  with open("/system/assets/world.geo.json", "r") as f:
    data = json.loads(f.read())
    for country in data:
      for polygon in country["polygons"]:
        path = [vec2(p[0], -p[1]) for p in polygon]
        point_count += len(path)
        path_count += 1
        coastlines.append(shape.custom(path))


load_coastlines()

# each coastline's colour is a pure function of its index, so compute it once
coastline_colors = [color.hsv(i * 2, 200, 160) for i in range(1, len(coastlines) + 1)]

# view state (screen-space pan offset + integer zoom)
pan_x = 0.0
pan_y = 0.0
zoom = 1

# app-level timing: split the frame into the (Python) shape loop vs everything
# else (clear + present), printed roughly once a second to match [pv].
_last_print = time.ticks_ms()


def update():
  global pan_x, pan_y, zoom, _last_print
  screen.antialias = image.X4

  # pan with UP/DOWN and A/C (left/right); B cycles zoom 1..5x
  step = 4.0
  if badge.held(BUTTON_UP):    pan_y += step * zoom
  if badge.held(BUTTON_DOWN):  pan_y -= step * zoom
  if badge.held(BUTTON_A):     pan_x += step * zoom
  if badge.held(BUTTON_C):     pan_x -= step * zoom
  if badge.pressed(BUTTON_B):  zoom = zoom % 10 + 1

  # one transform shared by every coastline this frame: scale (zoom) then pan
  xform = mat3().translate(160 + pan_x, 120 + pan_y).scale(zoom, zoom)

  t0 = time.ticks_us()
  for coastline, pen in zip(coastlines, coastline_colors):
    screen.pen = pen
    coastline.transform = xform
    screen.shape(coastline)
  t_shapes = time.ticks_diff(time.ticks_us(), t0)

  screen.pen = color.rgb(255, 255, 255)
  screen.text(f"zoom {zoom}x", 5, screen.height - 12)
  t_update = time.ticks_diff(time.ticks_us(), t0)

  now = time.ticks_ms()
  if time.ticks_diff(now, _last_print) >= 1000:
    _last_print = now
    # shapes = 273-shape loop (C rasteriser + Python marshalling); update adds text
    print(f"[app] shapes={t_shapes}us update={t_update}us")


run(update)
