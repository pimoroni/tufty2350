import asyncio

import aioble
import bluetooth

# Nordic UART Service: a de-facto standard GATT service for byte-stream
# chat over BLE. Notify (TX) carries badge -> laptop, write (RX) carries
# laptop -> badge. Any generic BLE terminal (nRF Connect, LightBlue, the
# ble_client.py tool in this repo) already knows how to talk to it.
_UART_SERVICE_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_TX_UUID = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_RX_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")

_ADV_INTERVAL_US = const(250_000)
_RX_MAX_LEN = const(200)

_service = aioble.Service(_UART_SERVICE_UUID)
_tx_characteristic = aioble.Characteristic(_service, _UART_TX_UUID, notify=True)
# A plain Characteristic's write buffer defaults to the size of its initial
# value (none, here), so anything longer than that is silently dropped by
# writes that don't expect a response. BufferedCharacteristic lets us size
# it for real messages instead.
_rx_characteristic = aioble.BufferedCharacteristic(
    _service,
    _UART_RX_UUID,
    write=True,
    write_no_response=True,
    capture=True,
    max_len=_RX_MAX_LEN,
)
aioble.register_services(_service)

_loop = asyncio.get_event_loop()

_name = "Tufty2350"
_connection = None
_messages = []
_advertise_task = None
_rx_task = None


async def _advertise_loop():
    global _connection

    while True:
        _connection = None
        _connection = await aioble.advertise(
            _ADV_INTERVAL_US,
            name=_name,
            services=[_UART_SERVICE_UUID],
        )
        await _connection.disconnected()


async def _rx_loop():
    while True:
        _conn, data = await _rx_characteristic.written()
        _messages.append(data.decode("utf-8", "ignore"))


def start(name="Tufty2350"):
    """Start advertising as `name` and begin accepting connections."""
    global _name, _advertise_task, _rx_task

    _name = name
    _messages.clear()

    if _advertise_task is None:
        _advertise_task = asyncio.create_task(_advertise_loop())
    if _rx_task is None:
        _rx_task = asyncio.create_task(_rx_loop())


def stop():
    """Disconnect, stop advertising, and tear down the background tasks."""
    global _advertise_task, _rx_task, _connection

    if _advertise_task is not None:
        _advertise_task.cancel()
        _advertise_task = None

    if _rx_task is not None:
        _rx_task.cancel()
        _rx_task = None

    if _connection is not None:
        try:
            _connection.disconnect()
        except OSError:
            pass
        _connection = None

    _messages.clear()


async def _yield():
    pass


def poll():
    """Pump the asyncio loop by one step. Call this every frame."""
    # run_until_complete() drains every currently-due task in the queue, not
    # just its argument, so a no-op coroutine is enough to advance
    # _advertise_loop/_rx_loop by one step. asyncio.sleep(0) can't be used
    # here: this build's sleep() returns a shared SingletonGenerator rather
    # than a real per-call coroutine, and create_task() rejects it.
    _loop.run_until_complete(_yield())


def is_connected():
    return _connection is not None


def send(text):
    """Notify the connected laptop/phone with `text` over the TX characteristic."""
    if _connection is None:
        return
    try:
        _tx_characteristic.notify(_connection, text.encode("utf-8"))
    except OSError:
        pass


def read():
    """Return and clear the messages received since the last call."""
    global _messages
    messages = _messages
    _messages = []
    return messages
