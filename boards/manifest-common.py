# from include("$(PORT_DIR)/boards/manifest.py")
freeze("$(PORT_DIR)/modules", "rp2.py")
include("$(MPY_DIR)/extmod/asyncio")
require("onewire")
require("ds18x20")
require("dht")
require("neopixel")

# Handy for dealing with APIs
require("datetime")

freeze("../modules/python/")
