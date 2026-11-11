"""Pins the upstream body bounds (size, wall-clock deadline) and the refusal of
XML entity declarations and YAML aliases that every fetcher relies on."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from types import SimpleNamespace
from typing import cast
from xml.etree import ElementTree as ET

import pytest
import requests
import yaml

from app.services.bounded_http import (
    BodyDeadlineError,
    ResponseTooLargeError,
    read_body,
    read_json,
    read_prefix,
    text_excerpt,
)
from app.services.safe_parse import load_yaml, parse_xml


class _Body:
    def __init__(self, chunks: list[bytes], headers: dict[str, str] | None = None) -> None:
        self._chunks = chunks
        self.headers = headers or {}
        self.raw = None
        self.iterated = False

    def iter_content(self, chunk_size: int = 1) -> Iterator[bytes]:
        self.iterated = True
        yield from self._chunks


class _Stalled:
    """Sends one chunk, then blocks until the reader shuts the socket down —
    which then surfaces either as a broken connection or as a clean EOF."""

    def __init__(self, eof: bool, shutdown_error: Exception | None) -> None:
        self.headers: dict[str, str] = {}
        self._released = threading.Event()
        self._eof = eof
        self._shutdown_error = shutdown_error
        self.raw = SimpleNamespace(shutdown=self._shutdown)

    def _shutdown(self) -> None:
        self._released.set()
        if self._shutdown_error is not None:
            raise self._shutdown_error

    def iter_content(self, chunk_size: int = 1) -> Iterator[bytes]:
        yield b"partial"
        if not self._released.wait(timeout=5):
            raise AssertionError("the deadline never shut the socket down")
        if self._eof:
            return
        raise requests.exceptions.ChunkedEncodingError("connection shut down")


def _r(fake: object) -> requests.Response:
    """The fakes implement only the Response surface bounded_http uses."""
    return cast(requests.Response, fake)


def _read(resp: object, max_bytes: int = 8) -> bytes:
    return read_body(_r(resp), max_bytes=max_bytes, deadline_s=5, label="test source")


def test_body_up_to_the_cap_is_returned_whole() -> None:
    assert _read(_Body([b"0123", b"4567"])) == b"01234567"


def test_body_past_the_cap_is_refused_while_streaming() -> None:
    with pytest.raises(ResponseTooLargeError, match="test source is larger than 8 bytes"):
        _read(_Body([b"0123", b"4567", b"8"]))


def test_declared_oversize_is_refused_before_reading() -> None:
    resp = _Body([b"0"], headers={"content-length": "9"})
    with pytest.raises(ResponseTooLargeError, match="declares 9 bytes"):
        _read(resp)
    assert not resp.iterated


def test_unparseable_content_length_falls_back_to_counting() -> None:
    assert _read(_Body([b"ok"], headers={"content-length": "lots"})) == b"ok"


def test_oversize_is_a_runtime_error_for_existing_handlers() -> None:
    assert issubclass(ResponseTooLargeError, RuntimeError)
    assert issubclass(BodyDeadlineError, requests.Timeout)


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        ([b"0123", b"4567"], (b"01234567", False)),
        ([b"0123", b"4567", b"89"], (b"01234567", True)),
    ],
)
def test_prefix_truncates_at_the_cap(chunks: list[bytes], expected: tuple[bytes, bool]) -> None:
    resp = _Body(chunks)
    assert read_prefix(_r(resp), max_bytes=8, deadline_s=5, label="test source") == expected


@pytest.mark.parametrize(
    ("eof", "shutdown_error"),
    [(False, None), (True, None), (False, RuntimeError("connection already released"))],
    ids=["broken-connection", "silent-eof", "shutdown-raises"],
)
def test_deadline_interrupts_a_stalled_body(
    eof: bool, shutdown_error: Exception | None
) -> None:
    resp = _Stalled(eof, shutdown_error)
    with pytest.raises(BodyDeadlineError, match="test source body not received within"):
        read_body(_r(resp), max_bytes=1024, deadline_s=0.05, label="test source")


def test_deadline_also_bounds_a_prefix_read() -> None:
    resp = _Stalled(eof=True, shutdown_error=None)
    with pytest.raises(BodyDeadlineError):
        read_prefix(_r(resp), max_bytes=1024, deadline_s=0.05, label="test source")


def test_read_json_decodes_and_rejects_malformed_bodies() -> None:
    def decode(chunks: list[bytes]) -> object:
        return read_json(_r(_Body(chunks)), max_bytes=64, deadline_s=5, label="test source")

    assert decode([b'{"a": ', b"1}"]) == {"a": 1}
    with pytest.raises(ValueError):
        decode([b"<html>"])


def test_text_excerpt_collapses_whitespace_and_limits_length() -> None:
    assert text_excerpt(b"bad \n\t param\xff value", 14) == "bad param\ufffd val"


# --- XML / YAML ----------------------------------------------------------------

_ENTITY_BOMB = (
    b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
    b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">]><lolz>&lol2;</lolz>'
)
_EXTERNAL_ENTITY = (
    b'<?xml version="1.0"?><!DOCTYPE vote [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
    b"<vote>&xxe;</vote>"
)
_PARAMETER_ENTITY = (
    b'<?xml version="1.0"?><!DOCTYPE vote [<!ENTITY % p "x">]><vote/>'
)


def test_plain_xml_parses() -> None:
    root = parse_xml(b'<?xml version="1.0"?><vote><n>1</n></vote>', label="test source")
    assert root.tag == "vote" and root.findtext("n") == "1"


def test_doctype_without_entities_is_accepted() -> None:
    root = parse_xml(b'<!DOCTYPE vote SYSTEM "vote.dtd"><vote/>', label="test source")
    assert root.tag == "vote"


@pytest.mark.parametrize(
    "body", [_ENTITY_BOMB, _EXTERNAL_ENTITY, _PARAMETER_ENTITY],
    ids=["internal", "external", "parameter"],
)
def test_entity_declarations_are_refused(body: bytes) -> None:
    with pytest.raises(ValueError, match="test source: XML entity declarations are not accepted"):
        parse_xml(body, label="test source")


def test_malformed_xml_still_raises_parse_error() -> None:
    with pytest.raises(ET.ParseError):
        parse_xml(b"<<not xml", label="test source")


def test_plain_yaml_loads_including_unused_anchors() -> None:
    assert load_yaml(b"- id: {bioguide: A000001}\n  name: &n Ada\n") == [
        {"id": {"bioguide": "A000001"}, "name": "Ada"}
    ]


def test_yaml_aliases_are_refused() -> None:
    with pytest.raises(yaml.YAMLError, match="YAML aliases are not accepted"):
        load_yaml(b"a: &x [1, 2]\nb: *x\n")


def test_yaml_loader_stays_safe() -> None:
    with pytest.raises(yaml.YAMLError):
        load_yaml(b"!!python/object/apply:os.system ['true']\n")
