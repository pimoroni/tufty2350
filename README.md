# Tufty 2350<!-- omit in toc -->

Tufty — a glorious blend of everything you love about Badger, now with a vibrant full-colour display and silky-smooth animation.
Perfect for mini dashboards, fast-paced games, and eye-catching widgets.

Get your very own Tufty from [https://shop.pimoroni.com/products/tufty-2350](https://shop.pimoroni.com/products/tufty-2350)

![Tufty 2350 front](https://badgewa.re/static/images/tufty_web_front.png)

- [Specs](#specs)
- [Meet The Badgeware Family](#meet-the-badgeware-family)
- [Help](#help)
  - [Create Your First App](APPS.md)
  - [Installing Apps](#installing-apps)
  - [Configuring WiFi](#configuring-wifi)
  - [API Documentation](#api-documentation)
  - [Updating/Reflashing Firmware](#updatingreflashing-firmware)

## Specs

Tufty shares its core hardware and Badgeware software with the other badges in the family. These are the details relevant to our Tufty badges, based on the official [Shared hardware](https://badgewa.re/docs#shared-hardware) and [Meet the badges](https://badgewa.re/docs#meet-the-badges) documentation.

| Feature | Tufty 2350 |
| --- | --- |
| Display | 2.8" full-colour IPS LCD with full RGB colour. Supports 320×240 and 160×120 modes, with continuous redraws for games, animation, and graphical interfaces. |
| Processor | RP2350 with two Arm Cortex-M33 cores running at 200MHz and hardware floating-point support. |
| Memory | 16MB flash holds firmware, code, and assets; 8MB PSRAM provides runtime memory. |
| Connectivity | 2.4GHz Wi-Fi for online apps and data downloads, plus Bluetooth 5.2. |
| Power | 1,000mAh rechargeable battery, charged through USB-C. |
| Expansion | Qw/ST connector for breakout accessories and an SWD debugging port. |
| Buttons | Five buttons on the front, with RESET and BOOTSEL on the back. |
| Software | Badgeware's MicroPython API is shared across the badge family; apps may need adjustments for each display. |
| USB disk mode | Double-tap RESET to access the badge as a USB drive, copy app files, then safely eject it to run them. See [Installing Apps](#installing-apps). |
| Lighting | Four-zone rear lighting. |
| Included | "Sciuridae Consultant" lanyard. |

Our badges arrive with firmware and demo apps installed. You can add and edit apps using USB disk mode without reflashing the firmware.

## Meet The Badgeware Family

* [Badger](https://github.com/pimoroni/badger2350) - 2.7" 264×176 greyscale e-paper
* [Blinky](https://github.com/pimoroni/blinky2350) - 872 pixel LED display
* [Tufty](https://github.com/pimoroni/tufty2350) - 2.8" 320×240 full-colour IPS LCD

More details at [https://badgewa.re](https://badgewa.re)

## Help

### Create Your First App

Start with [Creating and Installing Tufty Apps](APPS.md) for a complete walkthrough: write a small interactive app, copy it to your badge, launch it, and make your first changes. You only need a text editor and a USB data cable; the example works offline and does not require reflashing firmware.

### Installing Apps

Follow [Install and launch](APPS.md#4-install-and-launch) for the USB installation steps, or start at the beginning of [the first-app guide](APPS.md) to create an app first.

### Configuring WiFi

* Connect your badge to your computer with a USB Type-C to USB A cable.
* Turn your badge around so the back is facing you.
* Double-tap the RESET button, located toward the right on the left-hand side of the badge.
* A disk named "Tufty2350" should appear on your computer.
* Edit the file "secrets.py" and fill in your WiFi credentials.
* *Safely Unmount* the disk from your computer. This may take a second.
* Your badge should reboot into the menu!

### API Documentation

For comprehensive documentation of the Badgeware API, see: [https://badgewa.re/docs](https://badgewa.re/docs)

### Updating/Reflashing Firmware

:warning: Our firmware comes in two flavours:

1. `tufty-vX.X.X-micropython-with-filesystem` which will replace all the apps and software on your device with the defaults, and

2. `tufty-vX.X.X-micropython.uf2` which will replace only the firmware.

Pick your desired firmware image from the latest release at [https://github.com/pimoroni/tufty2350/releases/latest](https://github.com/pimoroni/tufty2350/releases/latest)

Then:

* Connect your badge to your computer with a USB Type-C to USB A cable.
* Turn your badge around so the back is facing you.
* Press and hold the BOOT button towards the far left.
* Briefly tap the RESET button to the right of BOOT.
* A disk named "RP2350" should appear on your computer.
* Drag and drop the firmware .uf2 onto this disk.
* Your badge should update and reboot into the menu!
