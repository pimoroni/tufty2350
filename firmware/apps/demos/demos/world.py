import math
import json

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

def update():
  screen.antialias = image.OFF

  i =  0
  for coastline in coastlines:
    i = i + 1
    x = math.sin(badge.ticks / 1000) * 100
    y = math.cos(badge.ticks / 700) * 30
    s = 1 #math.sin(badge.ticks / 1000) * 1 + 2

    screen.pen = color.hsv(i * 2, 200, 160)

    coastline.transform = mat3().translate(80 + x, 60 + y).scale(s, s)
    screen.shape(coastline)

  screen.pen = color.rgb(255, 255, 255)

  screen.text(f"{path_count} paths", 100, 95)
  screen.text(f"{point_count} points", 90, 105)
