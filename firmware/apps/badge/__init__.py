import sys
import os
import math

sys.path.insert(0, "/system/apps/badge")
os.chdir("/system/apps/badge")


CX = screen.width / 2
CY = screen.height / 2

screen.antialias = screen.X2


class Face:
    # details to be shown on the card
    id_photo = { "path": None, "data": None }
    id_name = None
    id_role = None

    lightness = None
    chroma = None
    hue = None

    id_socials = None


    def __init__ (self, id_photo_path = None, id_name = None, id_role = None,
                        lightness = None, chroma = None, hue = None,
                        id_socials = None):
        # Dict handling drove me CRAZY!
        # Originally, this code updated the path key only via
        # self.id_photo["path"] = id_photo_path, BUT this lead to a bug that
        # literally took me hours to debug: the id_photo dictionary in any Face
        # instance always referred to the same dictionary object, which meant
        # that it was shared among instances. Modifying any key hence modified
        # the content of all Face instances.
        # This is probably a peculiarity of MicroPython.
        # The workaround for this is to force the interpreter to create
        # distinct dictionaries by always creating new ones, always specifying
        # all keys.
        self.id_photo = { "path": id_photo_path,
                          "data": self.id_photo["data"] }
        self.id_name = id_name
        self.id_role = id_role

        self.lightness = lightness
        self.chroma = chroma
        self.hue = hue

        self.id_socials = id_socials


    def __str__ (self):
        return (f"Face(id_photo: {self.id_photo}, id_name: {self.id_name}, id_role: {self.id_role}, "
                     f"lightness: {self.lightness}, chroma: {self.chroma}, hue: {self.hue}, "
                     f"id_socials: {self.id_socials})")


    def copy (self, other):
        if not isinstance (other, Face):
            raise RuntimeError ("Face.copy () can only copy objects of its own class.")

        # N.B.: image data will not be a copy, we are lying in the function
        # name!
        self.id_photo = { "path": other.id_photo["path"],
                          "data": other.id_photo["data"] }
        self.id_name = other.id_name
        self.id_role = other.id_role

        self.lightness = other.lightness
        self.chroma = other.chroma
        self.hue = other.hue

        if other.id_socials is not None:
            self.id_socials = { }
            for key in other.id_socials:
                self.id_socials[key] = { "icon": other.id_socials[key]["icon"],
                                         "handle": other.id_socials[key]["handle"] }
        return (self)

# Disclaimer: all personas listed here are made up, including handles.
#             No endorsement was or is intended, and no such accounts existed
#             at the time of writing.
# Define your faces here and switch through them by long-pressing the B button.
# Within each face definition, if any value is None, it will use the value from
# the first face instead.
# Make sure that the first face is always fully defined (minus the icon key in
# the socials section, see below), or the application will crash!
faces = [Face ("avatar-squirrel.png", # Avatar image path.
               "Rusty A. Corn", # Description shown on front side of badge in a
                                # large font, typically your name.
               "Senior Nutwork Developer", # Description shown on front side of
                                           # badge in a smaller font, e.g.,
                                           # your job title.
               102, 64, 60, # Badge background color in lightness, chroma and
                            # hue values.
               # Lastly, a list of social accounts. This is a dictionary with
               # keys being social platform names - check the 'assets/social'
               # directory to see what is supported - and values being another
               # dictionary with two keys: an 'icon' key that will be used
               # internally to store the binary image data for the platform
               # logo, and a 'handle' key with your user name/mail
               # address/platform handle.
               # The 'icon' value is the only value that is allowed to be None
               # in the first face definition - and it SHOULD also be set to
               # None, since it will not be used, but always overwritten
               # internally.
               { "bluesky": { "icon": None, "handle": "rusty.acorn.tree" },
                 "github": { "icon": None, "handle": "treenutmachine" },
                 "discord": { "icon": None, "handle": "nutcache.dev" }
               }),
         Face (None, None, "Cert. Branch Routing Officer",
               None, None, None,
               None),
         Face ("avatar-bee.png", "Justin T. Hive",
               "Honeycomb Infra. Engineer",
               255, 255, 40,
               { "instagram": { "icon": None, "handle": "beenode.hun" },
                 "spotify": { "icon": None, "handle": "buzz_machine" },
               }),
         Face ("avatar-duck.png", "Dr. Drake Pointer",
               "Voting Mbr., Avian Arch. Cons.",
               255, 0, 0,
               { "steam": { "icon": None, "handle": "d1str1buted_quack" },
                 "deviantart": { "icon": None, "handle": "waddleworks" },
                 "twitch": { "icon": None, "handle": "pondstream33" },
                 "youtube": { "icon": None, "handle": "Mallard Runtime" }
               })]
face_id = 0
cur_face = Face ()

# id card variables
id_body = shape.rounded_rectangle(0, 0, 140, 100, 7)
id_outline = shape.rounded_rectangle(0, 0, 140, 100, 7).stroke(2)
flip = False
flip_start = 0
rear_view = False
card_pos = (10, 10)
# The color and background objects will be updated when applying the initial
# face.
lightness = None
chroma = None
hue = None
background = None

small_font = pixel_font.load("/system/assets/fonts/winds.ppf")
large_font = pixel_font.load("/system/assets/fonts/nope.ppf")


def draw_background():
    # ripple effect background
    cy = CY - 8
    cx = CX

    y = 0
    for _row in range(12):
        x = 0
        for _col in range(16):
            dist = math.sqrt((x + 5 - cx) ** 2 + (y + 5 - cy) ** 2)
            pulse = (math.sin(-badge.ticks / 400 + (dist / 6)) / 2) + 0.5
            pulse = 0.8 + (pulse / 2)
            screen.pen = color.rgb(0, 0, 0, 100 * pulse)
            screen.rectangle(x, y, 10, 10)
            x += 10
        y += 10


def shadow_text(text, x, y):
    screen.pen = color.rgb(20, 40, 60, 100)
    screen.text(text, x + 1, y + 1)
    screen.pen = color.rgb(0, 0, 0)
    screen.text(text, x, y)


def center_text(text, y):
    w, _ = screen.measure_text(text)
    shadow_text(text, (screen.width / 2) - (w / 2), y)


def apply_face(fid):
    global face_id, cur_face, lightness, chroma, hue, background

    face_id = fid % len (faces)
    cur_face = cur_face.copy (faces[face_id])

    # Fall back to first-face information if the current face does not provide
    # more specific ones. Unless we are already handling the first face...
    if (0 != face_id):
        if cur_face.id_photo["path"] is None:
            cur_face.id_photo = { "path": faces[0].id_photo["path"],
                                  "data": faces[0].id_photo["data"] }
        if cur_face.id_name is None:
            cur_face.id_name = faces[0].id_name
        if cur_face.id_role is None:
            cur_face.id_role = faces[0].id_role

        if cur_face.lightness is None:
            cur_face.lightness = faces[0].lightness
        if cur_face.chroma is None:
            cur_face.chroma = faces[0].chroma
        if cur_face.hue is None:
            cur_face.hue = faces[0].hue

        if cur_face.id_socials is None:
            cur_face.id_socials = { }
            for key in cur_face.id_socials.keys ():
                cur_face.id_socials[key] = { "icon": faces[0].id_socials[key]["icon"],
                                             "handle": faces[0].id_socials[key]["handle"] }

    # Load image data.
    # We are making a few design choices here that need some explanation:
    #   - We are not specially handling path values that are set to None. While
    #     image.load () will not handle None gracefully, we assume that users
    #     will define their faces array so that the path will never be None
    #     (especially with the fallback to the first face data we have in place
    #      above).
    #   - Instead of caching the actual binary image data for all faces once at
    #     initialization time, we will just load the data for each face when
    #     switching to it, dropping previously loaded data. This is a
    #     compromise between RAM usage and speed. Since faces are only switched
    #     rarely (at most every two seconds), loading the image data is not
    #     critical. On the other hand, RAM is tight on these boards, so try not
    #     to tax the hardware too much.
    cur_face.id_photo = { "path": cur_face.id_photo["path"],
                          "data": image.load (cur_face.id_photo["path"]) }

    if cur_face.id_socials is not None:
        for key in cur_face.id_socials.keys():
            cur_face.id_socials[key] = { "icon": image.load(f"assets/socials/{key}.png"),
                                         "handle": cur_face.id_socials[key]["handle"] }

    lightness = cur_face.lightness
    chroma = cur_face.chroma
    hue = cur_face.hue
    background = color.oklch(lightness, chroma, hue)


def init():
    apply_face (0)


def change_face():
    apply_face (face_id + 1)


def change_background(li = None, c = None, h = None):
    # a little helper to change the background color
    global background, lightness, chroma, hue

    changed = False

    if li:
        lightness += li
        lightness %= 256
        changed = True

    if c:
        chroma += c
        chroma = clamp(chroma, 0, 255)
        changed = True

    if h:
        hue += h
        hue %= 256
        changed = True

    if changed:
        background = color.oklch(lightness, chroma, hue)


def update():
    global flip, flip_start, rear_view, background, b_pressed

    # unpack the x and y for the card
    x, y = card_pos

    width = 1

    # clear the screen
    screen.pen = background
    screen.clear()

    # ripple effect
    draw_background()

    if badge.pressed (BUTTON_B):
        # If any other button is also pressed, the B button will be used as a
        # modifier.
        if not badge.held (BUTTON_UP) and not badge.held (BUTTON_DOWN) and \
           not badge.held (BUTTON_A)  and not badge.held (BUTTON_C):
            b_pressed = badge.ticks

    if badge.held (BUTTON_B):
        if b_pressed is not None:
            # If any other button is also pressed, we will use it as a
            # modifier.
            if badge.held (BUTTON_UP) or badge.held (BUTTON_DOWN) or \
               badge.held (BUTTON_A)  or badge.held (BUTTON_C):
                b_pressed = None
            else:
                # Make sure that we change faces immediately once the timeout
                # for long-pressing is reached.
                if 2000 <= (badge.ticks - b_pressed):
                    change_face()

                    b_pressed = None

    if badge.released (BUTTON_B):
        # Timeout might have already been reached by holding the button - do
        # nothing here if this is the case.
        # Once the B button is released, there are three possibilities:
        #   - B has been used as a modifier for a different button, in that
        #     case do nothing/forget the pressed state.
        #   - Flip the badge if the button was pressed for less than 2 seconds.
        #   - Change the face if the button was pressed for exactly 2 seconds.
        if b_pressed is not None:
            if 2000 > (badge.ticks - b_pressed):
                flip = True
                flip_start = badge.ticks
                rear_view = not rear_view
            else:
                # This should only happen if the button was pressed for exactly
                # 2 seconds. Unlikely to happen, but better safe than sorry.
                change_face()

            b_pressed = None

    if badge.held (BUTTON_UP):
        if badge.held (BUTTON_B):
            change_background (li = -5)
        else:
            change_background (h = -5)

    if badge.held (BUTTON_DOWN):
        if badge.held (BUTTON_B):
            change_background (li = 5)
        else:
            change_background (h = 5)

    if badge.held (BUTTON_C):
        if badge.held (BUTTON_B):
            # Do nothing, this would be a modifier, but we currently do not
            # use it.
            pass
        else:
            change_background (c = 5)

    if badge.held (BUTTON_A):
        if badge.held (BUTTON_B):
            # Do nothing, this would be a modifier, but we currently do not
            # use it.
            pass
        else:
            change_background (c =- 5)

    if flip:
        # create a spin animation that runs over 100ms
        speed = 95
        frame = badge.ticks - flip_start

        # calculate the width of the tile during this part of the animation
        width = round(math.cos(frame / speed) * 3) / 3

        # ensure the width never reduces to zero or the icon disappears
        width = max(0.1, width) if width > 0 else min(-0.1, width)

        # once the animation has completed unset the spin flag
        if frame > (speed * 3):
            flip = False

    # draw the card
    id_body.transform = mat3().translate(CX, y).scale(width, 1)
    id_outline.transform = mat3().translate(CX, y).scale(width, 1)
    id_body.transform = id_body.transform.translate(-70, 0)
    id_outline.transform = id_outline.transform.translate(-70, 0)

    screen.pen = color.rgb(50, 50, 50, 100)
    id_body.transform = id_body.transform.translate(4, 4)
    screen.shape(id_body)

    screen.pen = color.rgb(255, 255, 255, 90)
    id_body.transform = id_body.transform.translate(-4, -4)
    screen.shape(id_body)
    screen.pen = color.rgb(0, 0, 0, 100)
    screen.shape(id_outline)

    photo_y = y + 15 + cur_face.id_photo["data"].height
    socials_y = 22

    if not flip:
        # Draw the card information
        screen.pen = color.rgb(0, 0, 0)
        if not rear_view:
            screen.font = large_font
            screen.blit(cur_face.id_photo["data"], vec2(CX - cur_face.id_photo["data"].width / 2,
                                                        y + 10))
            center_text(cur_face.id_name, photo_y)
            screen.font = small_font
            center_text(cur_face.id_role, photo_y + 12)
        else:
            for account in cur_face.id_socials.items():
                screen.font = large_font
                y_offset = 1
                screen.pen = color.rgb(100, 100, 100)
                screen.shape(shape.rounded_rectangle(20, socials_y, 17, 17, 3))
                screen.blit(account[1]["icon"], vec2(20, socials_y))
                if 15 <= len (account[1]["handle"]):
                    screen.font = small_font
                    y_offset = 2
                shadow_text(account[1]["handle"], 40, socials_y + y_offset)
                socials_y += 21


def on_exit():
    pass


init ()
run(update)
