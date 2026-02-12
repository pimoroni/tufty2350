import sys
import gc

# Grab a list of modules from before launching menu
standard_modules = list(sys.modules.keys())

# We expect a launcher menu to be at /system/apps/menu
app_to_launch = run("/system/apps/menu")

# Make sure any module names imported by menu are freed for apps
for key in sys.modules.keys():
    if key not in standard_modules:
        del sys.modules[key]

gc.collect()

# Stopping in Thonny can cause run("/system/apps/menu") to return None
if app_to_launch is not None:

    # Don't pass menu button presses into the newly launched app
    while badge.held():
        badge.poll()

    run(app_to_launch)
