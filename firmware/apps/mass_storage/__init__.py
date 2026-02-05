import os
import sys


# Standalone bootstrap for finding app assets
os.chdir("/system/apps/mass_storage")

# Standalone bootstrap for module imports
sys.path.insert(0, "/system/apps/mass_storage")


# Called once to initialise your app.
def init():
    import _msc.py   # noqa F401


# Called every frame, update and render as you see fit!
def update():
    pass


# Handle saving your app state here
def on_exit():
    pass


# Standalone support for Thonny debugging
if __name__ == "__main__":
    run(update, init=init, on_exit=on_exit)
