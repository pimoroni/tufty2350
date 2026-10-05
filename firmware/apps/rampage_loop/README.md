# Rampage Loop

A silent, four-second video that repeats continuously on Tufty. After a brief loading screen, playback fills the display with no controls or text over the video. Press the rear HOME/BOOTSEL button to return to the launcher.

## Install

Follow [Install and launch](../../../APPS.md#4-install-and-launch), copying this entire `rampage_loop` directory into the badge's `apps` folder. Select **Rampage Loop** in the menu and press **B**. The included 24×24 icon depicts the Rampage boat from the video.

The folder must include `__init__.py`, `icon.png`, the loading-screen font at `assets/sins.ppf`, and all 48 PNG files inside `frames/`. The shipped launcher hides apps without an icon; newer launchers can provide a default. No Wi-Fi, MP4 player, or firmware flashing is required.

## Playback format

- Source: `havoc-rampage-crossing-water-loop-4s.mp4`, 640×480, 24 fps, four seconds.
- Badge frames: 160×120 RGB PNGs, numbered `frame_000.png` through `frame_047.png`.
- Playback: 12 fps in Tufty's low-resolution mode, filling the 320×240 display.
- Decoded pixel memory: 3,686,400 bytes (about 3.5 MiB), plus runtime and decoder overhead.

The app loads every frame once at startup. It selects frames using elapsed time, so a delayed refresh skips ahead rather than slowing the video. Playback repeats the supplied clip as-is; conversion does not change its loop boundary.

## Regenerate the frames

On a laptop with FFmpeg installed, run this from the repository root, replacing `/path/to/video.mp4` with the source video path:

```sh
ffmpeg -hide_banner -i /path/to/video.mp4 -an \
  -vf 'fps=12,scale=160:120:flags=lanczos,setsar=1' \
  -frames:v 48 -pix_fmt rgb24 -start_number 0 \
  firmware/apps/rampage_loop/frames/frame_%03d.png
```

This command expects the same four-second, 4:3 source. The MP4 stays on the laptop; only the converted frames are installed on the badge. If you change the duration or playback frame rate, update the constants in `__init__.py` and regenerate the matching number of frames.

The frame assets and playback logic can be checked on a laptop, but available memory and playback performance still need verification on a physical badge with its shipped firmware.
