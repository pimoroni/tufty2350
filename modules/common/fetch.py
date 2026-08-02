import io
import tls
import time
import errno
import socket
import json


class HTTPException(Exception):
    def __init__(self, fetch):
        self.fetch = fetch
        super().__init__(f"HTTP error {fetch.http_status}")


class AsyncFetch:
    FETCH_BLOCK_SIZE = 1024
    buffer = bytearray(FETCH_BLOCK_SIZE)

    # Bytes moved per update() call. One block per call would cap throughput at the
    # frame rate, a larger budget spends longer in a single step.
    STEP_BYTES = 4 * FETCH_BLOCK_SIZE

    # Initial size of the in-memory response buffer, doubled as needed
    BUFFER_START_SIZE = 2048

    # Ceiling on an in-memory response. A chunked response declares no length, so
    # without this the buffer grows to whatever the server decides to send.
    BUFFER_MAX_SIZE = 256 * 1024

    # Give up on a response header block longer than this
    MAX_HEADER_BYTES = 4096

    # Seconds to wait for data before abandoning a fetch, 0 to wait forever
    TIMEOUT = 10

    # Statuses that carry no body, whatever their headers say
    BODYLESS_STATUS = (204, 304)

    STATUS_TEXT = ["Idle", "Fetching", "Done", "Error"]
    IDLE = 0
    FETCHING = 1
    DONE = 2
    ERROR = 3

    def __init__(self, host, port=None, use_tls=True, debug=False, buffer_size=None, max_bytes=None, timeout=None, step_bytes=None):
        self._debug = debug

        self._fetch = None  # hold the pending fetch
        self._sock = None  # hold the open socket

        self._last_update = None  # keep track of the last updated time

        self._buffer = None  # bytearray holding an in-memory response
        self._buffer_len = 0  # amount of data actually in our buffer
        self._buffer_size = buffer_size or AsyncFetch.BUFFER_START_SIZE
        self._max_bytes = max_bytes or AsyncFetch.BUFFER_MAX_SIZE

        self._timeout = AsyncFetch.TIMEOUT if timeout is None else timeout
        self._deadline = None

        self._step_bytes = step_bytes or AsyncFetch.STEP_BYTES
        self._step_remaining = self._step_bytes

        self._interval = 0  # fetch interval in seconds
        self._path = None
        self._file = None  # Target file, or none to fetch to a stream

        self._on_complete = None
        self._on_error = None

        self._data = None
        self._method = "GET"

        self._headers = {}
        self._response_headers = {}
        self._status_code = None
        self._content_length = 0
        self._keep_alive = False
        self._chunked = False
        self._read_to_close = False

        self._use_tls = use_tls

        self._host = host
        self._port = port or (443 if use_tls else 80)

        # HTTP/1.1 wants the port in Host unless it's the default for the scheme
        default_port = 443 if use_tls else 80
        self._host_header = host if self._port == default_port else f"{host}:{self._port}"

        self._status = AsyncFetch.IDLE

    def fetch(self, path, file=None, interval=None, headers=None, data=None, method=None, blocking=False):
        if self._fetch:
            raise RuntimeError("Cannot interrupt a running fetch...")

        if path.startswith(("http://", "https://")):
            raise ValueError("fetch requires a relative path, not a full URL.")

        self._buffer_len = 0

        if interval is not None:
            self._interval = interval

        # Make sure we re-trigger is the interval is 0 (no-repeat)
        if self._interval == 0:
            self._last_update = None

        if headers is not None:
            # Copy, since request headers are added to this
            self._headers = dict(headers)

        self._path = path[1:] if path.startswith("/") else path
        self._file = file
        self._data = data

        if method is not None:
            self._method = method

        if "User-Agent" not in self._headers:
            self._headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.4 Safari/605.1.15"

        if blocking:
            # Fetch now, not at the next interval
            self._last_update = None
            self.finish()
            return self.stream

        return None

    def reset(self):
        # Drop any pending fetch and cached socket, ready for a new fetch
        self._fetch = None
        self._close_socket()
        self._status = AsyncFetch.IDLE

    def _close_socket(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _extend_deadline(self):
        # The timeout covers inactivity, so a slow but progressing transfer is fine
        if self._timeout:
            self._deadline = time.ticks_add(time.ticks_ms(), int(self._timeout * 1000))

    def _check_deadline(self):
        if self._deadline is None:
            return

        if time.ticks_diff(time.ticks_ms(), self._deadline) > 0:
            raise OSError(errno.ETIMEDOUT, f"No data for {self._timeout}s")

    def _budget_reset(self):
        self._step_remaining = self._step_bytes

    def _budget_spend(self, count):
        # True once this step has moved as much data as it is allowed to
        self._step_remaining -= count
        return self._step_remaining <= 0

    def _reserve(self, length):
        # Grow the in-memory buffer to hold length bytes, doubling from _buffer_size and
        # never shrinking. io.BytesIO reallocates to fit each individual write, which
        # copies the whole buffer once per block.
        if length > self._max_bytes:
            raise ValueError(f"Response of {length} bytes exceeds max_bytes of {self._max_bytes}")

        size = len(self._buffer) if self._buffer is not None else 0

        if size >= length:
            return

        new_size = max(size, self._buffer_size)
        while new_size < length:
            new_size *= 2

        new_size = min(new_size, self._max_bytes)

        buffer = bytearray(new_size)
        if self._buffer_len:
            buffer[: self._buffer_len] = memoryview(self._buffer)[: self._buffer_len]
        self._buffer = buffer

        if self._debug:
            print(f"Buffer {size} -> {new_size} bytes")

    def _response_header(self, name, default=None):
        # Header names are case-insensitive, servers pick their own capitalisation
        name = name.lower()
        for k in self._response_headers:
            if k.lower() == name:
                return self._response_headers[k]
        return default

    def _connect(self):
        # getaddrinfo blocks, so a hostname costs a DNS round trip inside this step,
        # where an address costs nothing
        sock_family, sock_type, sock_proto, _, sock_addr = socket.getaddrinfo(self._host, self._port, 0, socket.SOCK_STREAM)[0]

        sock = socket.socket(sock_family, sock_type, sock_proto)
        sock.setblocking(False)

        try:
            try:
                sock.connect(sock_addr)

            except OSError as e:
                # A non-blocking connect reports that it has started, not that it is done
                if e.errno != errno.EINPROGRESS:
                    raise

            if self._use_tls:
                context = tls.SSLContext(tls.PROTOCOL_TLS_CLIENT)
                context.verify_mode = tls.CERT_NONE

                # The handshake runs on the first write instead of blocking here for a
                # whole round trip, and _send_all spreads it over as many steps as it needs
                sock = context.wrap_socket(sock, server_hostname=self._host, do_handshake_on_connect=False)

        except OSError:
            sock.close()
            raise

        self._sock = sock
        yield

    def _send_all(self, data):
        # A non-blocking write returns the number of bytes it took, or None if it could
        # take none. That is also how a pending connection and an unfinished TLS
        # handshake report themselves, so this loop waits for both.
        view = memoryview(data)
        sent = 0

        while True:
            written = self._sock.write(view[sent:])

            if written:
                sent += written
                self._extend_deadline()

                if sent >= len(view):
                    return

            else:
                self._check_deadline()

            yield

    def _read_line(self):
        # readline() on a non-blocking socket returns a partial line when it runs out of
        # data mid-line, and None only when nothing at all was available, so accumulate
        # until the terminator arrives.
        line = b""

        while True:
            part = self._sock.readline()

            if part is None:
                self._check_deadline()

            elif part == b"":
                raise OSError("Connection closed mid-line")

            else:
                self._extend_deadline()
                self._budget_spend(len(part))
                line += part

                if line.endswith(b"\n"):
                    return line

            yield

    def _request(self):
        # Send the request and read the response status and headers
        self._status_code = None
        self._response_headers = {}

        if self._sock is None:
            yield from self._connect()

        try:
            request = [f"{self._method} /{self._path} HTTP/1.1", f"Host: {self._host_header}"]

            for k in self._headers:
                request.append(f"{k}: {self._headers[k]}")

            if self._data:
                request.append(f"Content-Length: {len(self._data)}")

            request = ("\r\n".join(request) + "\r\n\r\n").encode("utf-8")

            # One write, so Nagle can't hold the body back waiting for a delayed ACK
            yield from self._send_all((request + self._data) if self._data else request)

            header_bytes = 0

            while True:
                line = yield from self._read_line()

                if line in (b"\r\n", b"\n"):
                    break

                header_bytes += len(line)
                if header_bytes > AsyncFetch.MAX_HEADER_BYTES:
                    raise ValueError(f"Response headers longer than {AsyncFetch.MAX_HEADER_BYTES} bytes")

                if line.startswith(b"HTTP/"):
                    self._status_code = int(line.decode("utf-8").strip().split(" ")[1])

                elif b": " in line:
                    k, v = line.decode("utf-8").strip().split(": ", 1)
                    self._response_headers[k] = v

                if self._step_remaining <= 0:
                    yield
                    self._budget_reset()

        except Exception:
            # Nothing can be resynchronised from a half-read response
            self._close_socket()
            raise

    def _http_fetch(self):
        self._headers["Connection"] = "keep-alive"

        if self._data is not None and self._method == "GET":
            self._method = "POST"

        reused_socket = self._sock is not None

        try:
            yield from self._request()

        except OSError:
            # A cached keep-alive socket may have been dropped by the peer, so one retry
            # on a fresh connection. A failure on a fresh connection is real.
            if not reused_socket:
                raise
            if self._debug:
                print("Cached socket failed, retrying on a new one")
            yield from self._request()

        content_length = self._response_header("Content-Length")

        self._chunked = "chunked" in self._response_header("Transfer-Encoding", "").lower()
        self._content_length = int(content_length) if content_length is not None else 0

        # Honour the server's choice, don't cache a socket it intends to close
        self._keep_alive = "close" not in self._response_header("Connection", "").lower()

        if self._method == "HEAD" or self._status_code in AsyncFetch.BODYLESS_STATUS:
            # No body follows, whatever the headers say
            self._chunked = False
            self._content_length = 0
            self._read_to_close = False

        else:
            # Unframed, so the body ends when the peer closes and the socket can't be
            # handed to another request
            self._read_to_close = content_length is None and not self._chunked

            if self._read_to_close:
                self._keep_alive = False

        if self._debug:
            if self._chunked:
                print("Got a chunked response")
            elif self._read_to_close:
                print("Got a response terminated by close")
            else:
                print(f"Got {self._content_length} bytes")

    def _recv(self, stream, want):
        # Read up to want bytes into the destination. Returns the count, None if nothing
        # was available yet, or 0 at end of stream.
        if stream is None:
            # Clamp to the allowance, so a body of exactly max_bytes still fits
            want = min(want, self._max_bytes - self._buffer_len)

            if want == 0:
                raise ValueError(f"Response exceeds max_bytes of {self._max_bytes}")

            self._reserve(self._buffer_len + want)
            length = self._sock.readinto(memoryview(self._buffer)[self._buffer_len:], want)

        else:
            length = self._sock.readinto(AsyncFetch.buffer, want)
            if length:
                stream.write(memoryview(AsyncFetch.buffer)[:length])

        if length:
            self._buffer_len += length

        return length

    def _read_body(self, stream, remaining):
        # remaining is a byte count, or None to read until the peer closes
        while remaining is None or remaining > 0:
            want = AsyncFetch.FETCH_BLOCK_SIZE if remaining is None else min(remaining, AsyncFetch.FETCH_BLOCK_SIZE)

            length = self._recv(stream, want)

            if length is None:
                self._check_deadline()
                yield
                self._budget_reset()
                continue

            if length == 0:
                if remaining is None:
                    return  # A clean close is how this body ends
                raise OSError(f"Connection closed with {remaining} bytes outstanding")

            self._extend_deadline()

            if remaining is not None:
                remaining -= length

            if self._debug:
                print(f"Fetched {self._buffer_len} bytes")

            if self._budget_spend(length):
                yield
                self._budget_reset()

    def _read_chunked(self, stream):
        while True:
            # Each chunk opens with its length in hex, plus extensions we don't use
            header = yield from self._read_line()
            size = int(header.decode("utf-8").split(";")[0].strip(), 16)

            if self._debug:
                print(f"Chunk of {size} bytes")

            if size == 0:
                break

            yield from self._read_body(stream, size)

            yield from self._read_line()  # The CRLF that follows the chunk data

            if self._step_remaining <= 0:
                yield
                self._budget_reset()

        # Trailers, up to the blank line that ends the response. A peer that closes here
        # has still delivered the whole body, so keep it and drop the socket.
        try:
            while (yield from self._read_line()) not in (b"\r\n", b"\n"):
                pass

        except OSError:
            self._keep_alive = False

    def _fetch_to_stream(self):
        self._extend_deadline()
        self._budget_reset()

        # Grab the data
        yield from self._http_fetch()

        self._buffer_len = 0
        stream = None

        try:
            if self._file:
                stream = open(self._file, "wb")
                if self._debug:
                    print(f"Streaming to {self._file}")

            else:
                # One allocation covers a response that declares its length
                if self._content_length:
                    self._reserve(self._content_length)
                if self._debug:
                    print("Streaming to buffer")

            if self._chunked:
                yield from self._read_chunked(stream)

            elif self._read_to_close:
                yield from self._read_body(stream, None)

            elif self._content_length:
                yield from self._read_body(stream, self._content_length)

        except Exception:
            # A part-read body leaves the socket out of step with the next request
            self._close_socket()
            raise

        finally:
            # Leave the in-memory buffer alone, it is handed out by the stream property
            if stream is not None:
                stream.close()

        if not self._keep_alive:
            self._close_socket()

    def update(self):
        self._status = AsyncFetch.IDLE

        if self._path is not None:
            if self._last_update is None or (self._interval > 0 and self.duration > int(self._interval * 1000)):
                # Don't overwrite an existing fetch operation if the interval comes up...
                if self._fetch is None and self._debug:
                    print("Fetch started")
                self._fetch = self._fetch or self._fetch_to_stream()

            if self._fetch:
                try:
                    next(self._fetch)
                    self._status = AsyncFetch.FETCHING

                except StopIteration as e:
                    if self._debug:
                        print("Fetch done")
                    self._last_update = time.ticks_ms()
                    self._fetch = None

                    if self._status_code == 200:
                        self._status = AsyncFetch.DONE
                        if callable(self._on_complete):
                            self._on_complete(self)

                    else:
                        self._status = AsyncFetch.ERROR
                        if not callable(self._on_error) or not self._on_error(self):
                            raise HTTPException(self) from e

                except Exception:
                    # Clear the pending fetch, or a single failure blocks every later fetch
                    self._fetch = None
                    self._status = AsyncFetch.ERROR
                    raise

        return self._status

    @property
    def duration(self):
        if self._last_update is None:
            return 0
        return time.ticks_diff(time.ticks_ms(), self._last_update)

    @property
    def status(self):
        return self._status

    @property
    def source(self):
        return self._path

    @property
    def destination(self):
        return self._file

    @property
    def http_status(self):
        return self._status_code

    @property
    def http_response_headers(self):
        return self._response_headers

    @property
    def body(self):
        # The response bytes, without copying them out of the buffer
        if self._file:
            raise ValueError("Response was saved to a file")

        if self._buffer is None:
            return memoryview(b"")

        return memoryview(self._buffer)[: self._buffer_len]

    @property
    def stream(self):
        # Return a FileIO for a saved file or a StringIO containing the buffer value
        if self._file:
            return open(self._file, "r")

        if self._buffer is None:
            return io.StringIO("")

        # StringIO copies anything that isn't str or bytes, so prefer body or to_json
        return io.StringIO(memoryview(self._buffer)[: self._buffer_len])

    def to_json(self):
        if self._file:
            return json.load(self.stream)

        if self._buffer is None:
            raise ValueError("No response body to parse")

        # json.loads reads any buffer in place, so the body is parsed without a copy
        return json.loads(self.body)

    def finish(self):
        # Force a blocking finish of the fetch command
        while True:
            status = self.update()

            # DONE, or an error the caller has chosen not to raise on
            if status != AsyncFetch.FETCHING:
                return status

    def on_complete(self, handler):
        self._on_complete = handler

    def on_error(self, handler):
        self._on_error = handler
