import builtins


class AnimatedSprite:
    def __init__(self, sheet, x=0, y=0, count=1, horizontal=True):
        self.frames = []
        for _ in range(count):
            self.frames.append(sheet.sprite(x, y))
            if horizontal:
                x += 1
            else:
                y += 1

    def frame(self, frame_index=0):
        return self.frames[int(frame_index) % len(self.frames)]

    def count(self):
        return len(self.frames)


builtins.AnimatedSprite = AnimatedSprite
