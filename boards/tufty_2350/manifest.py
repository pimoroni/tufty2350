require("bundle-networking")
require("urllib.urequest")
require("umqtt.simple")

# Bluetooth
require("aioble")

freeze("$(BOARD_DIR)", "version.py")

include("../manifest-common.py")
