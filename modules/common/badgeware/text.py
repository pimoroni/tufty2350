import builtins


def pen_glyph_renderer(image, parameters, measure):
    if measure:
        return 0
    image.pen = color.rgb(*(int(c) for c in parameters))
    return None


# Sprites registered by name for the inline [sprite:name] renderer.
SPRITES = {}


def register_sprite(name, img):
    SPRITES[name] = img


def sprite_glyph_renderer(image, parameters, measure):
    img = SPRITES[parameters[0]]
    if measure:
        return img.width
    image.blit(img, image.cursor)
    return None


# Built-in inline glyph renderers, keyed by the [code] used in the text. A
# renderer is fn(image, params, measure): return the advance width when measure
# is True, else draw (reading image.cursor for position) and return None. Extend
# with register_glyph_renderer(name, fn) or the per-call glyph_renderers arg.
GLYPH_RENDERERS = {"pen": pen_glyph_renderer, "sprite": sprite_glyph_renderer}


def register_glyph_renderer(name, fn):
    GLYPH_RENDERERS[name] = fn

class _text:
    @staticmethod
    def tokenise(image, text, glyph_renderers=None, size=0):
        WORD = 1
        SPACE = 2
        LINE_BREAK = 3

        # avoid copying the registry when there are no per-call additions
        renderers = GLYPH_RENDERERS
        if glyph_renderers:
            renderers = dict(GLYPH_RENDERERS)
            renderers.update(glyph_renderers)

        tokens = []

        for line in text.splitlines():
            start = 0
            length = len(line)
            while start < length:
                # inline [code] / [code:a,b] markup at the cursor
                if line[start] == "[":
                    glyph_end = line.find("]", start)
                    if glyph_end != -1:
                        body = line[start + 1:glyph_end]
                        if ":" in body:
                            code, params = body.split(":", 1)
                            params = params.split(",")
                        else:
                            code, params = body, []
                        if code in renderers:
                            w = renderers[code](None, params, True)
                            tokens.append((renderers[code], w, tuple(params)))
                            start = glyph_end + 1
                            continue
                    # unterminated or unknown: fall through and treat as text

                # a run of text up to the next space or the next [ markup
                next_space = line.find(" ", start)
                next_glyph = line.find("[", start + 1)

                end = min(next_space, next_glyph)
                if end == -1:
                    end = max(next_space, next_glyph)
                if end == -1:
                    end = length

                # measure the word (size is a sentinel-0 optional: point size for
                # vector fonts, integer scale for pixel)
                if end > start:
                    width, _ = image.measure_text(line[start:end], size)
                    tokens.append((WORD, width, line[start:end]))

                start = end
                if start < length and line[start] == " ":
                    tokens.append((SPACE,))
                    start += 1

            tokens.append((LINE_BREAK,))

        return tokens

    @staticmethod
    def draw(image, text, bounds=None, line_spacing=1, word_spacing=1, size=0):
        WORD = 1
        SPACE = 2
        LINE_BREAK = 3

        if bounds is None:
            bounds = rect(0, 0, image.width, image.height)
        else:
            bounds = rect(int(bounds.x), int(bounds.y), int(bounds.w), int(bounds.h))

        if isinstance(text, str):
            tokens = _text.tokenise(image, text, size=size)
        else:
            tokens = text

        old_clip = image.clip
        image.clip = bounds

        # Line height: vector fonts use the point size (12 by default); pixel
        # fonts use their glyph height times the integer scale (1 by default).
        if isinstance(image.font, vector_font):
            font_height = size or 12
        else:
            font_height = image.font.height * (size or 1)

        c = vec2(bounds.x, bounds.y)
        b = rect(bounds.x, bounds.y, 0, 0)
        for token in tokens:
            if token[0] == WORD:
                if c.x + token[1] > bounds.x + bounds.w:
                    c.x = bounds.x
                    c.y += font_height * line_spacing
                image.text(token[2], c.x, c.y, size)
                c.x += token[1]
            elif token[0] == SPACE:
                c.x += (font_height / 3) * word_spacing
            elif token[0] == LINE_BREAK:
                c.x = bounds.x
                c.y += font_height * line_spacing
            else:
                if c.x + token[1] > bounds.x + bounds.w:
                    c.x = bounds.x
                    c.y += font_height * line_spacing

                image.cursor = c
                token[0](image, token[2], False)
                c.x += token[1]

            if token[0] != SPACE:
                b.w = max(b.w, c.x - b.x)

            b.h = max(b.h, c.y - b.y)

        # c.y is the top of the last line; include its height in the bounds.
        b.h += font_height

        image.clip = old_clip
        return b

    # Draw scrolling text into a given window
    @staticmethod
    def scroll(text, font_face=None, font_size=None, target=None, speed=25, gap=None, align="middle"):
        font_face = font_face or rom_font.sins

        is_vector_font = isinstance(font_face, vector_font)

        if is_vector_font and font_size is None:
            raise ValueError("scroll_text: vector fonts require a font_size")

        # Bitmap fonts take an integer scale (1, 2, 3, ...); default to 1x so we
        # pass a real scale through rather than None (the text API rejects None).
        if not is_vector_font and font_size is None:
            font_size = 1

        target = target or screen
        target.font = font_face

        tw, th = target.measure_text(text, font_size)

        if is_vector_font:
            th = font_size

        scroll_distance = tw + (gap if isinstance(gap, int) else target.width)

        t_start = badge.ticks

        offset_y = align if isinstance(align, int) else 0

        if align == "middle":
            offset_y = (target.height - th) // 2

        if align == "bottom":
            offset_y = target.height - th

        offset = vec2(0, offset_y)

        def update():
            timedelta = badge.ticks - t_start
            timedelta /= 1000 / speed
            progress = timedelta / scroll_distance
            timedelta %= scroll_distance
            timedelta /= scroll_distance

            if isinstance(gap, int):
                offset.x = -scroll_distance * timedelta
            else:
                offset.x = target.width - (scroll_distance * timedelta)

            target.font = font_face

            # font_size is the point size for vector fonts and the integer scale
            # for bitmap fonts (see picovector image.text).
            target.text(text, offset, font_size)

            if isinstance(gap, int):
                while offset.x + tw < target.width:
                    offset.x += tw + gap
                    target.text(text, offset, font_size)

            return progress

        return update


# Kept for back-compat: font.load is now the single loader (native), which
# sniffs the file's magic marker, resolves short names against the search paths
# and returns a vector_font or pixel_font.
def load_font(font_file):
    return font.load(font_file)


# rom_font is the font namespace itself: font.sins loads /rom/fonts/sins.ppf
# (cached), and dir(font) lists the ROM fonts. The alias keeps existing
# rom_font.<name> call sites working.
builtins.rom_font = font
builtins.load_font = load_font
builtins.text = _text
builtins.register_glyph_renderer = register_glyph_renderer
builtins.register_sprite = register_sprite
