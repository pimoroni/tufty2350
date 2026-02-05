import math

skull = image.load("/system/assets/skull.png")
screen.font = pixel_font.load("/system/assets/fonts/compass.ppf")


def pen_glyph_renderer(_image, parameters, _cursor, measure):
  if measure:
    return 0

  r = int(parameters[0])
  g = int(parameters[1])
  b = int(parameters[2])
  screen.pen = color.rgb(r, g, b)
  return None


def skull_glyph_renderer(image, _parameters, cursor, measure):
  if measure:
    return 24
  image.blit(skull, cursor)
  return None


def circle_glyph_renderer(image, _parameters, cursor, measure):
  if measure:
    return 12

  image.shape(shape.circle(cursor.x + 6, cursor.y + 7, 6))
  return None


nope = pixel_font.load("/system/assets/fonts/nope.ppf")


glyph_renderers = {
  "skull": skull_glyph_renderer,
  "pen": pen_glyph_renderer,
  "circle": circle_glyph_renderer
}


def update():
  i = round(badge.ticks / 200)
  i %= 10

  message = """[pen:180,150,120]Upon the mast I gleam and grin, A sentinel of bone and sin. Wind and thunder, night and hull- None fear the sea like a [pen:230,220,200]pirate skull[pen:180,150,120][skull].
"""

  screen.pen = color.rgb(100, 255, 100, 150)

  x = 5
  y = 5
  width = math.sin(badge.ticks / 500) * 40 + 110
  height = 200
  tokens = text_tokenise(screen, message, glyph_renderers)
  bounds = rect(x, y, width, height)
  text_draw(screen, tokens, bounds, line_spacing=1, word_spacing=1.05)

  screen.pen = color.rgb(60, 80, 100, 100)
  screen.line(bounds.x, bounds.y, bounds.x + bounds.w, bounds.y)
  screen.line(bounds.x, bounds.y, bounds.x, bounds.y + bounds.h)
  screen.line(bounds.x, bounds.y + bounds.h, bounds.x + bounds.w, bounds.y + bounds.h)
  screen.line(bounds.x + bounds.w, bounds.y, bounds.x + bounds.w, bounds.y + bounds.h)

