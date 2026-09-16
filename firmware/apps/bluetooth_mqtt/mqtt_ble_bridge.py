"""MQTT <-> BLE bridge for Tufty2350 badges.

Subscribes to `test/topic` on the MQTT broker running on this laptop
(port 2883) and rewrites every message it sees to the RX characteristic
of the badge's Nordic UART Service (see apps/bluetooth/ble.py), over BLE.
Any badge running the `bluetooth` app and connected over BLE will show the
message in its log.

Also runs the other direction: any notification the badge sends on its TX
characteristic (e.g. pressing A in the `bluetooth` app) gets published
back to `test/topic`.

Runs continuously: scans for badges, connects to any it finds, reconnects
on drop, and keeps forwarding MQTT traffic to whichever badges are
currently connected.

Requires:
    pip install "paho-mqtt>=2.0" bleak

Run under pm2:
    pm2 start mqtt_ble_bridge.py --name mqtt-ble-bridge --interpreter python3
"""

import asyncio
import logging
import signal

import paho.mqtt.client as mqtt
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

MQTT_HOST = "localhost"
MQTT_PORT = 2883
MQTT_TOPIC = "test/topic"

# Matches apps/bluetooth/ble.py's Nordic UART Service.
UART_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
UART_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # badge -> laptop (notify)
UART_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # laptop -> badge (write)

SCAN_INTERVAL_S = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mqtt-ble-bridge")

connected_clients = {}  # address -> BleakClient
mqtt_client = None


async def broadcast(payload):
    if not connected_clients:
        log.warning("No BLE devices connected, dropping message: %r", payload)
        return

    for address, client in list(connected_clients.items()):
        try:
            await client.write_gatt_char(UART_RX_UUID, payload, response=False)
        except BleakError as e:
            log.warning("Failed to write to %s: %s", address, e)


def _on_disconnect(client):
    address = client.address
    log.info("Disconnected from %s", address)
    connected_clients.pop(address, None)


def _on_badge_notify(address):
    def _handler(_characteristic, data):
        log.info("BLE -> MQTT (%s): %r", address, data)
        mqtt_client.publish(MQTT_TOPIC, data)

    return _handler


async def connect_device(device):
    if device.address in connected_clients:
        return

    client = BleakClient(device, disconnected_callback=_on_disconnect)
    try:
        await client.connect()
        await client.start_notify(UART_TX_UUID, _on_badge_notify(device.address))
        connected_clients[device.address] = client
        log.info("Connected to %s (%s)", device.name, device.address)
    except BleakError as e:
        log.warning("Could not connect to %s: %s", device.address, e)


async def scan_loop():
    while True:
        try:
            devices = await BleakScanner.discover(timeout=5, service_uuids=[UART_SERVICE_UUID])
            for device in devices:
                await connect_device(device)
        except BleakError as e:
            log.warning("Scan failed: %s", e)

        await asyncio.sleep(SCAN_INTERVAL_S)


async def main():
    global mqtt_client

    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def on_message(_client, _userdata, msg):
        loop.call_soon_threadsafe(queue.put_nowait, msg.payload)

    def on_connect(client, _userdata, _flags, reason_code, _properties=None):
        log.info("Connected to MQTT broker at %s:%s (rc=%s)", MQTT_HOST, MQTT_PORT, reason_code)
        client.subscribe(MQTT_TOPIC)

    mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_client.loop_start()

    scan_task = asyncio.create_task(scan_loop())

    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async def forward_loop():
        while True:
            payload = await queue.get()
            log.info("MQTT -> BLE: %r", payload)
            await broadcast(payload)

    forward_task = asyncio.create_task(forward_loop())

    await stop.wait()
    log.info("Shutting down...")

    scan_task.cancel()
    forward_task.cancel()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    for client in list(connected_clients.values()):
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
