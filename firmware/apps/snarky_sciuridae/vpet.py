import random
import math

# this class defines our little friend, modify it to change their behaviour!
#
# - move pet to a random location
# - change pet's mood
# - alter pet's stats (happiness, hunger, cleanliness)
# - change pet's appearance
#
# the ui will automatically update to reflect pet's state

class Pet:
  _moods = []
  _animations = {}

  def __init__(self, y):
    self._happy = 100
    self._hunger = 100
    self._clean = 100
    self._animation = None
    self._mood = None
    self._mood_changed_at = (badge.ticks / 1000)
    self._action = None
    self._action_changed_at = None
    self._position_changed_at = (badge.ticks / 1000)
    self._position = (80, y + 2)
    self._direction = 1
    self._target = 80
    self._speed = 0.5
    self.set_mood("default")

  def load(self, state):
    self._happy = state.get("happy", 0)
    self._hunger = state.get("hunger", 0)
    self._clean = state.get("clean", 0)

  def save(self):
    return {
      "happy": self._happy,
      "hunger": self._hunger,
      "clean": self._clean,
    }

  def draw(self):
    # break out x and y into a shorter hand variables
    x, y = self._position

    # select sprite for current animation frame
    if self._action:
      action_time = (badge.ticks / 1000) - self._action_changed_at
      image = Pet._animations[self._action].frame(round(action_time * 10))
    else:
      image = Pet._animations[self._mood].frame(round(badge.ticks / 100))

    width, height = image.width * 4, image.height * 4

    # draw pets shadow
    screen.pen = color.rgb(0, 0, 0, 20)
    screen.shape(shape.rectangle(x - (width / 2) + 5, y , width - 10, 2))
    screen.shape(shape.rectangle(x - (width / 2) + 5 + 2, y - 2, width - 10 - 4, 4))

    # invert pet if they are walking left
    width *= self._direction

    # is pet floating?
    floating = math.sin(badge.ticks / 250) * 5 + 5 if self._mood == "dead" else 0

    # offset sprite
    x -= abs(width / 2)
    y -= height + floating

    y = int(y / 4) * 4
    x = int(x / 4) * 4

    # draw pet
    alpha = 150 if self._mood == "dead" else 255
    image.alpha = alpha
    screen.blit(image, rect(x, y, width, height))

    # draw pets reflection
    #image.alpha = int(alpha * 0.2)
    screen.blit(image, rect(x, self._position[1] + (floating / 2) + 1, width, -10))
    image.alpha = 255

  # set a new target position for pet to move to
  def move_to(self, target):
    self._target = target
    self._position_changed_at = (badge.ticks / 1000)

  # move pet back into centre frame
  def move_to_center(self):
    self._target = 80
    self._position_changed_at = (badge.ticks / 1000)

  # select a random position for pet to move to
  def move_to_random(self):
    self.move_to(random.randint(90, 130))

  # return the number of seconds since pet moved
  def time_since_last_position_change(self):
    return (badge.ticks / 1000) - self._position_changed_at

  # return pets current position
  def position(self):
    return self._position

  # change pets mood
  def set_mood(self, mood):
    self._mood = mood
    self._mood_changed_at = (badge.ticks / 1000)

  def do_action(self, action):
    self._action = action
    self._action_changed_at = (badge.ticks / 1000)

  def current_action(self):
    return self._action

  def is_dead(self):
    return self._happy == 0 or self._clean == 0 or self._hunger == 0

  # increase or decrease pets statistics
  def happy(self, amount=0):
    self._happy = clamp(self._happy + amount, 0, 100)
    return self._happy

  def clean(self, amount=0):
    self._clean = clamp(self._clean + amount, 0, 100)
    return self._clean

  def hunger(self, amount=0):
    self._hunger = clamp(self._hunger + amount, 0, 100)
    return self._hunger

  # update pets position
  def update(self):
    # break out x and y into a shorter hand variables
    x, y = self._position

    # if pet isn't at their target position then move towards it
    if x != self._target and not self._action:
      self._direction = 1 if x > self._target else -1
      self._position = (x - (self._speed * self._direction), y)

    # if pet is performing an action then let it run for 2 seconds and end it
    if self._action:
      if (badge.ticks / 1000) - self._action_changed_at > 2:
        self._action = None

  # select a random mood for pet
  def random_idle(self):
    idles = ["dig", "default"]
    self.set_mood(random.choice(idles))

  # return the number of seconds since pets mood changed
  def time_since_last_mood_change(self):
    return (badge.ticks / 1000) - self._mood_changed_at

# define pets animations and the number of frames
animations = {
  # actions
  "dance":    4, # play
  "clean":    4, # clean
  "eating":   2, # eat
  "running":  7,
  "sleep":    4,
  "dig":      4,
  "default":  6,
  "notify":   6,
  "dead":     6

}


# load the spritesheets for pets animations
for name, frame_count in animations.items():
  sprites = SpriteSheet(f"/system/assets/squirrel-sprites/{name}.png", frame_count, 1)
  Pet._animations[name] = sprites.animation()  # noqa: SLF001
print("done")

Pet._moods = list(Pet._animations.keys())  # noqa: SLF001
