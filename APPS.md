# Creating and Installing Tufty Apps

Build a small app that greets the Cloud Org and responds to a button press. This walkthrough uses the Badgeware firmware already on your Tufty; no firmware build, flashing, or Wi-Fi setup is required.

The app packaging and installation steps are based on Badgeware's [Creating your first app](https://badgewa.re/docs/introduction/your-first-app.md) tutorial. The example below uses the same `run(update)` pattern as this repo's bundled apps.

- [What you need](#what-you-need)
- [1. Create an app folder](#1-create-an-app-folder)
- [2. Write your app](#2-write-your-app)
- [3. Add an icon](#3-add-an-icon)
- [4. Install and launch](#4-install-and-launch)
- [5. Make it yours](#5-make-it-yours)
- [Troubleshooting](#troubleshooting)
- [Explore further](#explore-further)

## What you need

- Your Tufty badge with its supplied firmware and demo apps.
- A laptop and a USB cable that carries data, with connectors that fit your laptop and the badge's USB-C port.
- A plain-text code editor. You will save Python files on your laptop and copy them to the badge; you do not need to install Python on your laptop for this workflow.

## 1. Create an app folder

On your laptop, create a folder called `cloud_hello`. Inside it, create a file named exactly `__init__.py` (two underscores on each side of `init`).

```text
cloud_hello/
└── __init__.py
```

The badge runs `__init__.py` when you launch the app. Its folder name becomes the menu label: `cloud_hello` appears as **Cloud Hello**.

Keep this laptop copy as your working copy. You can also share the whole folder with a teammate.

## 2. Write your app

Paste this complete program into `cloud_hello/__init__.py` and save it:

```python
badge.mode(LORES | VSYNC)
try:
    screen.font = rom_font.sins
except NameError:
    screen.font = font.sins

greetings = ["Hello, Cloud Org!", "Hello from Tufty!"]
greeting_index = 0


def update():
    global greeting_index

    if badge.pressed(BUTTON_A):
        greeting_index = (greeting_index + 1) % len(greetings)

    screen.pen = color.rgb(15, 30, 50)
    screen.clear()
    screen.pen = color.white
    screen.text(greetings[greeting_index], 10, 35)
    screen.text("A: change greeting", 10, 70)


run(update)
```

Badgeware supplies `badge`, `screen`, `color`, the button constants, and `run` automatically. The font library is available to apps as `rom_font` on shipped firmware and `font` on newer firmware; the example tries those names directly, without looking them up on the `builtins` module. Run this program on the badge; a laptop's normal Python interpreter does not provide those objects.

The example uses Tufty's 160×120 drawing mode. Coordinates start at the top-left corner: increasing `x` moves right and increasing `y` moves down. `screen.pen` selects the colour for subsequent drawing, including `screen.clear()`.

`run(update)` repeatedly calls your function, displays the frame, and polls the buttons. The function returns normally each time so the helper can finish that work. `badge.pressed(BUTTON_A)` detects a new press, so each tap advances the greeting once.

## 3. Add an icon

Save a **24×24 PNG** as `cloud_hello/icon.png`. The shipped launcher only lists apps that contain this file. Newer launchers offer a default icon, but include one so your app works with the supplied firmware.

For a quick start, copy the [Gallery app's icon](firmware/apps/gallery/icon.png) into your folder, keeping the name `icon.png`. To make your own, use a simple symbol or a couple of letters that read clearly at that size.

You can later add an optional `assets/` folder for images or fonts; this example does not need one.

## 4. Install and launch

1. Connect the badge to your laptop with the USB data cable.
2. Double-tap **RESET** on the back to enter USB disk mode. Open the badge's drive in your file manager; look for **TUFTY** or **Tufty2350**.
3. Open the drive's existing `apps` folder. Copy your entire `cloud_hello` folder into it, alongside the supplied apps. The result should be:

   ```text
   <badge drive>/
   └── apps/
       └── cloud_hello/
           ├── __init__.py
           └── icon.png
   ```

4. Wait for copying to finish, then safely eject/unmount the drive. If the badge stays in disk mode after ejection, tap **RESET** once.
5. In the launcher, use **A/C** to move left/right and **UP/DOWN** to move between rows. Highlight **Cloud Hello** and press **B** to launch it.
6. You should see “Hello, Cloud Org!” on a dark blue background. Press **A** to switch greetings. Press the rear **HOME/BOOTSEL** button to return to the launcher.

## 5. Make it yours

Change a greeting to your name or team, choose a different background with `color.rgb(red, green, blue)` (each value is 0–255), or move the text by changing its coordinates.

Save your edits on the laptop. Double-tap RESET again, copy the updated files into the same `apps/cloud_hello` folder, safely eject, and relaunch **Cloud Hello**. Keep the app in its own folder so you can experiment without replacing a supplied app.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| No badge drive appears | Confirm the cable supports data and double-tap RESET again. |
| The drive is named `RP2350` | This is firmware flashing mode. Tap RESET to leave it, then double-tap RESET for app installation. |
| The app is missing from the menu | Check for both `apps/cloud_hello/__init__.py` and `apps/cloud_hello/icon.png`, with no extra nested folder or hidden `.txt` extension. The shipped launcher requires an icon. Eject and reset after copying. |
| An error appears when launching | Note the error and line number, check the saved code and indentation, then correct your laptop copy and reinstall it. |
| Laptop Python reports that `badge` or `screen` is undefined | Launch the app from the badge's menu instead of running it with desktop Python. |
| Your latest edits do not appear | Confirm that you saved the laptop file and replaced the file inside the badge's app folder before ejecting and relaunching. |

## Explore further

Browse the [bundled apps](firmware/apps) for ideas. The [badge app](firmware/apps/badge/__init__.py) shows a customizable name card, and the [graphics demos](firmware/apps/demos/demos) cover drawing techniques.

For online projects, follow [Configuring WiFi](README.md#configuring-wifi). The [Badgeware documentation](https://badgewa.re/docs) covers more of the API.

[Back to the README](README.md)
