# We expect a launcher menu to be at /system/apps/menu
app_to_launch = launch("/system/apps/menu")

# Stopping in Thonny can cause launch("/system/apps/menu") to return None
if app_to_launch is not None:

    # Don't pass menu button presses into the newly launched app
    while badge.pressed() or badge.held() or badge.released():
        badge.poll()

    launch(app_to_launch)

# Catch any exit and reset back to the launcher
reset()
