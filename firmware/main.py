import sys
import os
from badgeware import fatal_error
import machine
import gc

running_app = None


def quit_to_launcher(pin):
    global running_app
    getattr(running_app, "on_exit", lambda: None)()
    # If we reset while boot is low, bad times
    while not pin.value():
        pass
    machine.reset()


standard_modules = list(sys.modules.keys())

try:
    menu = __import__("/system/apps/menu")
except Exception as e:  # noqa: BLE001
    fatal_error("Error!", e)

app = run(menu.update)

if sys.path[0].startswith("/system/apps"):
    sys.path.pop(0)

del menu

# make any module names imported by menu are freed for apps
for key, _module in sys.modules.items():
    if key not in standard_modules:
        del sys.modules[key]

gc.collect()

# Stopping in Thonny can cause run(menu.update) to return None
if app is not None:
    # Don't pass the b press into the app
    while badge.held():
        badge.poll()

    machine.Pin.board.BUTTON_HOME.irq(
        trigger=machine.Pin.IRQ_FALLING, handler=quit_to_launcher
    )

    sys.path.insert(0, app)
    try:
        os.chdir(app)
        running_app = __import__(app)
        getattr(running_app, "init", lambda: None)()
    except Exception as e:  # noqa: BLE001
        fatal_error("Error!", e)

    run(running_app.update)

    machine.reset()
