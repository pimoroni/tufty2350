import math

# colour stops are constant, so define them once. each stop is (position, color)
# with position 0..1, up to 16 stops.
SUNSET = [
  (0.0, color.rgb(255, 94, 91)),
  (0.5, color.rgb(255, 209, 102)),
  (1.0, color.rgb(67, 138, 255)),
]

ORB = [
  (0.0, color.rgb(255, 255, 255)),
  (0.35, color.rgb(120, 210, 255)),
  (1.0, color.rgb(18, 28, 84)),
]


def update():
  screen.antialias = image.X4

  w = screen.width
  h = screen.height

  # --- linear gradient filling a rounded rectangle -------------------------
  rx, ry = w * 0.06, h * 0.08
  rw, rh = w * 0.88, h * 0.40

  # the gradient axis lives in 0..1 space; rotate it about the centre over time
  ang = badge.ticks / 1200
  dx, dy = math.cos(ang) * 0.5, math.sin(ang) * 0.5

  # map the 0..1 unit square onto the rectangle
  m = mat3().translate(rx, ry).scale(rw, rh)
  screen.pen = brush.gradient(brush.LINEAR, 0.5 - dx, 0.5 - dy, 0.5 + dx, 0.5 + dy, SUNSET, m)
  screen.shape(shape.rounded_rectangle(rx, ry, rw, rh, h * 0.05))

  # --- radial gradient filling a circle ------------------------------------
  cx, cy = w * 0.5, h * 0.74
  rad = min(w, h) * 0.22

  # map the 0..1 square onto the circle's bounding box. centre the bright stop
  # toward the top-left (0.35, 0.35) and reach the last stop at the far corner
  # (1, 1) so it reads like a lit sphere.
  m2 = mat3().translate(cx - rad, cy - rad).scale(rad * 2, rad * 2)
  screen.pen = brush.gradient(brush.RADIAL, 0.35, 0.35, 1.0, 1.0, ORB, m2)
  screen.shape(shape.circle(cx, cy, rad))

  screen.pen = color.rgb(255, 255, 255)
  screen.text("linear", rx, ry + rh + 3)
  screen.text("radial", cx - 18, cy + rad + 4)
