"""Laptop-side companion for the badge's `bluetooth` app.

Connects to a Tufty2350 badge over BLE (Nordic UART Service), prints
whatever it sends, and relays anything you type back to the badge.

Requires bleak:  pip install bleak

Usage:
    python3 ble_client.py [device-name]
"""

import asyncio
import sys

from bleak import BleakClient, BleakScanner

DEVICE_NAME = sys.argv[1] if len(sys.argv) > 1 else "Tufty2350"

UART_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # badge -> laptop (notify)
UART_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # laptop -> badge (write)


def on_notify(_characteristic, data):
    print(f"< {data.decode('utf-8', 'ignore')}")


async def send_loop(client):
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return
        line = line.rstrip("\n")
        if line:
            await client.write_gatt_char(UART_RX_UUID, line.encode(), response=False)


async def main():
    print(f"Scanning for '{DEVICE_NAME}'...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15)
    if device is None:
        print(f"Could not find a BLE device advertising as '{DEVICE_NAME}'.")
        return

    async with BleakClient(device) as client:
        print(f"Connected to {device.address}. Type a message and press enter to send it.")
        await client.start_notify(UART_TX_UUID, on_notify)
        await send_loop(client)


if __name__ == "__main__":
    asyncio.run(main())
