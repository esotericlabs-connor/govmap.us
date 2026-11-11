"""Size- and time-bounded reads of upstream HTTP response bodies.

A ``requests`` timeout bounds the connect and each individual socket read, not
the whole body: an upstream that drips a byte just inside every read timeout,
or answers with a far larger payload than expected, could otherwise hold a
worker thread (and its upstream request slot) for hours or exhaust memory in
the API process that also hosts the scheduler. Every fetcher therefore sends
with ``stream=True`` and reads the body through this module, under an explicit
byte cap and a wall-clock deadline that starts once the headers arrive.

Bytes are counted after content decoding, so a compressed body is bounded by
its decoded size; the pinned urllib3 (2.8.0) also bounds per-read
decompression output and chunk-size lines in its streaming API.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import requests

_CHUNK = 64 * 1024


class ResponseTooLargeError(RuntimeError):
    """The upstream body exceeded the byte cap for this source."""


class BodyDeadlineError(requests.Timeout):
    """The body was not fully received before its deadline. A
    ``requests.Timeout`` so existing outage handling classifies it like any
    other upstream timeout."""


def _declared_length(resp: requests.Response) -> int | None:
    value = resp.headers.get("content-length")
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _read(
    resp: requests.Response, max_bytes: int, deadline_s: float, label: str, truncate: bool
) -> tuple[bytes, bool]:
    expired = threading.Event()

    def expire() -> None:
        expired.set()
        # Unblocks a read stuck waiting on the socket; urllib3 raises ValueError
        # or RuntimeError when the connection is already finished or released.
        shutdown = getattr(resp.raw, "shutdown", None)
        if shutdown is not None:
            try:
                shutdown()
            except (OSError, RuntimeError, ValueError):
                pass

    timer = threading.Timer(deadline_s, expire)
    timer.daemon = True
    body = bytearray()
    cut_short = False
    timer.start()
    try:
        for chunk in resp.iter_content(chunk_size=min(_CHUNK, max_bytes + 1)):
            body.extend(chunk)
            if len(body) > max_bytes:
                if not truncate:
                    raise ResponseTooLargeError(f"{label} is larger than {max_bytes} bytes")
                del body[max_bytes:]
                cut_short = True
                break
            if expired.is_set():
                break
    except ResponseTooLargeError:
        raise
    except Exception as exc:
        if expired.is_set():
            raise BodyDeadlineError(
                f"{label} body not received within {deadline_s:g}s ({type(exc).__name__})"
            ) from None
        raise
    finally:
        timer.cancel()
    # The socket shutdown can surface as a clean EOF on a close-delimited body,
    # so a short read after expiry is a timeout, never a complete payload.
    if expired.is_set():
        raise BodyDeadlineError(f"{label} body not received within {deadline_s:g}s")
    return bytes(body), cut_short


def read_body(
    resp: requests.Response, *, max_bytes: int, deadline_s: float, label: str
) -> bytes:
    """The whole body, or ``ResponseTooLargeError`` past ``max_bytes`` (checked
    against Content-Length first, then while streaming) and
    ``BodyDeadlineError`` past ``deadline_s``. ``label`` names the source in
    errors; it must not contain a URL with credentials or query parameters."""
    declared = _declared_length(resp)
    if declared is not None and declared > max_bytes:
        raise ResponseTooLargeError(
            f"{label} declares {declared} bytes, larger than {max_bytes} bytes"
        )
    return _read(resp, max_bytes, deadline_s, label, truncate=False)[0]


def read_prefix(
    resp: requests.Response, *, max_bytes: int, deadline_s: float, label: str
) -> tuple[bytes, bool]:
    """At most ``max_bytes`` of the body and whether more was available. For
    sources where a truncated body is still useful (or only a prefix is
    inspected); the deadline still applies."""
    return _read(resp, max_bytes, deadline_s, label, truncate=True)


def read_json(
    resp: requests.Response, *, max_bytes: int, deadline_s: float, label: str
) -> Any:
    """``read_body`` then JSON-decode; a malformed body raises ``ValueError``."""
    return json.loads(read_body(resp, max_bytes=max_bytes, deadline_s=deadline_s, label=label))


def text_excerpt(body: bytes, limit: int) -> str:
    """A whitespace-collapsed, length-limited excerpt of an error body."""
    return " ".join(body.decode("utf-8", errors="replace").split())[:limit]
