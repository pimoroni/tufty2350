# This example grabs current weather details from Open Meteo and displays them on Tufty 2350.
# Find out more about the Open Meteo API at https://open-meteo.com

import time

import ezwifi
import urequests
from picovector import (ANTIALIAS_BEST, HALIGN_CENTER, PicoVector, Polygon,
                        Transform)

import tufty2350
from tufty2350 import HEIGHT, WIDTH

# Set your latitude/longitude here (find yours by right clicking in Google Maps!)
LAT = 53.38609085276884
LNG = -1.4239983439328177
weather_timeZONE = "auto"  # determines weather_time zone from lat/long

URL = "http://api.open-meteo.com/v1/forecast?latitude=" + str(LAT) + "&longitude=" + str(LNG) + "&current_weather=true&weather_timezone=" + weather_timeZONE

CENTRE_X = WIDTH // 2
CENTRE_Y = HEIGHT // 2

ICONS = {
    "cloud": "\ue2bd",
    "rainy": "\uf176",
    "weather_snowy": "\ue2cd",
    "thunderstorm": "\uebdb",
    "sunny": "\ue81a"
}

# Display Setup
display = tufty2350.Tufty2350()

BACKGROUND = display.create_pen(154, 203, 208)
FOREGROUND = display.create_pen(242, 239, 231)
HIGHLIGHT = display.create_pen(72, 166, 167)

# Pico Vector
vector = PicoVector(display.display)
vector.set_antialiasing(ANTIALIAS_BEST)
t = Transform()
vector.set_font("Roboto-Medium-With-Material-Symbols.af", 40)
vector.set_font_align(HALIGN_CENTER)
vector.set_transform(t)

TITLE_BAR = Polygon()
TITLE_BAR.rectangle(2, 2, WIDTH - 4, 16, (8, 8, 8, 8))
TITLE_BAR.circle(WIDTH - 10, 10, 4)

INFO_BOX = Polygon()
INFO_BOX.rectangle(2, 122, WIDTH - 4, 90, (8, 8, 8, 8))


def draw_header():

    # Clear the display
    display.set_pen(BACKGROUND)
    display.clear()
    display.set_pen(0)

    # Draw the page header
    display.set_pen(FOREGROUND)
    vector.draw(TITLE_BAR)
    display.set_pen(HIGHLIGHT)
    display.text("tuftyOS", 7, 6, WIDTH, 1)
    display.text("Weather", WIDTH - 60, 6, WIDTH, 1)
    display.set_pen(2)


# Display a loading screen while the wifi connects.
draw_header()
display.set_pen(HIGHLIGHT)
display.text("Loading...", 5, HEIGHT // 2, WIDTH, 2)
display.update()

# Connects to the wireless network. Ensure you have entered your details in WIFI_CONFIG.py :).
ezwifi.connect(verbose=True, retries=3)


def get_data():

    # display.led(128)

    try:
        global weathercode, temperature, windspeed, winddirection, date, weather_time
        print(f"Requesting URL: {URL}")
        r = urequests.get(URL)
        # open the json data
        j = r.json()
        print("Data obtained!")
        print(j)

        # parse relevant data from JSON
        current = j["current_weather"]
        temperature = current["temperature"]
        windspeed = current["windspeed"]
        winddirection = calculate_bearing(current["winddirection"])
        weathercode = current["weathercode"]
        date, weather_time = current["time"].split("T")

        r.close()
        # display.led(0)
    except OSError:
        temperature = None
        # display.led(0)


def calculate_bearing(d):
    # calculates a compass direction from the wind direction in degrees
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    ix = round(d / (360. / len(dirs)))
    return dirs[ix % len(dirs)]


def draw_page():

    draw_header()

    display.set_font("bitmap8")
    display.set_pen(FOREGROUND)
    vector.draw(INFO_BOX)

    display.set_pen(FOREGROUND)
    if temperature is not None:
        icon_y = 70
        # Choose an appropriate icon based on the weather code
        # Weather codes from https://open-meteo.com/en/docs
        # Weather icons from https://fontawesome.com/
        if weathercode in [71, 73, 75, 77, 85, 86]:  # codes for snow
            vector.text(ICONS["weather_snowy"], CENTRE_X, icon_y)
        elif weathercode in [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82]:  # codes for rain
            vector.text(ICONS["rainy"], CENTRE_X, icon_y)
        elif weathercode in [1, 2, 3, 45, 48]:  # codes for cloud
            vector.text(ICONS["cloud"], CENTRE_X, icon_y)
        elif weathercode in [0]:  # codes for sun
            vector.text(ICONS["sunny"], CENTRE_X, icon_y)
        elif weathercode in [95, 96, 99]:  # codes for storm
            vector.text(ICONS["thunderstorm"], CENTRE_X, icon_y)

        line_y = 131

        display.set_pen(HIGHLIGHT)
        display.text(f"Temperature: {temperature}°C", 8, line_y, WIDTH, 2)
        line_y += 22
        display.text(f"Wind Speed: {windspeed}kmph", 8, line_y, WIDTH, 2)
        line_y += 22
        display.text(f"Wind Direction: {winddirection}", 8, line_y, WIDTH, 2)
        line_y += 22
        display.text(f"Last update: {date}, {weather_time}", 8, line_y, WIDTH, 1)

    else:
        display.set_pen(3)
        display.text("Unable to display weather! Check your network settings in secrets.py", 5, 127, WIDTH - 10, 2)

    display.update()


# Keep a record of the last time we updated.
# We only want to be requesting new information every half an hour.
last_updated = time.time()

# Grab the data before we enter the loop.
get_data()

while True:

    # Update every 15 minutes
    if time.time() - last_updated > 900:
        get_data()
        last_updated = time.time()

    draw_page()
