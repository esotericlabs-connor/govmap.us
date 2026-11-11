import json
from collections import deque
from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock

import pytest
import requests
from pydantic import ValidationError
from starlette.requests import Request

from app.config import Settings, settings
from app.routers import report


def _request(
    headers: dict[str, str] | None = None, peer: str = "198.51.100.10"
) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/report",
            "headers": [
                (key.encode("ascii"), value.encode("ascii"))
                for key, value in (headers or {}).items()
            ],
            "client": (peer, 12345),
        }
    )


@pytest.fixture(autouse=True)
def reset_report_limits() -> Iterator[None]:
    report._rate.clear()
    report._global_rate.clear()
    yield
    report._rate.clear()
    report._global_rate.clear()


@pytest.mark.parametrize(
    ("origin", "accepted"),
    [
        ("https://govmap.us", True),
        ("https://GOVMAP.US:443", True),
        ("https://govmap.us.attacker.example", False),
        ("https://govmap.us:444", False),
        ("http://govmap.us", False),
        ("https://govmap.us@attacker.example", False),
        ("https://attacker.example@govmap.us", False),
        ("https://govmap.us:invalid", False),
        ("null", False),
        ("", False),
    ],
)
def test_origin_matches_exact_authority(
    monkeypatch: pytest.MonkeyPatch, origin: str, accepted: bool
) -> None:
    monkeypatch.setattr(settings, "cors_origins", "https://govmap.us")
    assert report._origin_ok(_request({"origin": origin})) is accepted


def test_referer_fallback_and_origin_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cors_origins", "https://govmap.us")
    assert report._origin_ok(_request({"referer": "https://govmap.us/congress?q=test"}))
    assert not report._origin_ok(
        _request({"origin": "https://attacker.example", "referer": "https://govmap.us/"})
    )


def test_untrusted_peer_cannot_select_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")
    request = _request(
        {"cf-connecting-ip": "203.0.113.7", "x-forwarded-for": "203.0.113.8"}
    )
    assert report._client_ip(request) == "198.51.100.10"


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"cf-connecting-ip": "203.0.113.7"}, "203.0.113.7"),
        ({"cf-connecting-ip": "2001:db8::1"}, "2001:db8::1"),
        ({"cf-connecting-ip": "invalid"}, "198.51.100.10"),
        ({"cf-connecting-ip": "203.0.113.7,203.0.113.8"}, "198.51.100.10"),
        ({"x-forwarded-for": "203.0.113.8"}, "198.51.100.10"),
        ({}, "198.51.100.10"),
    ],
)
def test_only_trusted_peer_can_supply_verified_header(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str], expected: str
) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "198.51.100.10/32")
    assert report._client_ip(_request(headers)) == expected
    assert report._client_ip(_request(headers, peer="198.51.100.11")) == "198.51.100.11"


@pytest.mark.parametrize("cidrs", ["invalid", "0.0.0.0/0", "::/0"])
def test_invalid_or_universal_proxy_trust_is_rejected(cidrs: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, trusted_proxy_cidrs=cidrs)


def test_per_ip_limit_expires_without_clearing_other_buckets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(report.time, "monotonic", lambda: clock[0])
    for _ in range(20):
        assert report._rate_ok("198.51.100.10")
    assert not report._rate_ok("198.51.100.10")
    assert report._rate_ok("198.51.100.11")
    clock[0] = 3600.0
    assert report._rate_ok("198.51.100.10")


def test_rotating_addresses_cannot_bypass_global_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(report.time, "monotonic", lambda: 0.0)
    for i in range(200):
        assert report._rate_ok(f"203.0.113.{i}")
    assert not report._rate_ok("198.51.100.99")


def test_bucket_capacity_never_resets_active_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(report.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(report, "_MAX_RATE_IPS", 2)
    report._rate["198.51.100.1"] = deque([0.0] * 20)
    report._rate["198.51.100.2"] = deque([0.0] * 20)
    assert not report._rate_ok("198.51.100.3")
    assert not report._rate_ok("198.51.100.1")
    clock[0] = 3600.0
    assert report._rate_ok("198.51.100.3")
    assert len(report._rate) == 1


def test_scrub_strips_terminal_bidi_and_invisible_characters() -> None:
    raw = "a\x1b[31mb\x9b2Jc\u2028d\u202ee\u200bf\ufeffg\u2066h"
    assert report._scrub(raw, 200) == "a [31mb 2Jc d e f g h"
    assert report._scrub("Café — naïve ½", 200) == "Café — naïve ½"


class _VerifyResponse:
    def __init__(self, status: int = 200, body: Any = None, content: bytes | None = None):
        self.status_code = status
        self._content = content if content is not None else json.dumps(body).encode()
        self.headers: dict[str, str] = {}
        self.raw = None

    def __enter__(self) -> "_VerifyResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def iter_content(self, chunk_size: int = 1) -> Iterator[bytes]:
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]


def _turnstile(
    monkeypatch: pytest.MonkeyPatch,
    response: _VerifyResponse | Exception,
    secret: str = "real-secret-for-tests",
) -> Mock:
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", secret)
    monkeypatch.setattr(settings, "cors_origins", "https://govmap.us")
    post = Mock(side_effect=[response])
    monkeypatch.setattr(report.requests, "post", post)
    return post


@pytest.mark.parametrize(
    ("body", "accepted"),
    [
        ({"success": True, "hostname": "govmap.us"}, True),
        ({"success": True, "hostname": "GOVMAP.US"}, True),
        ({"success": True, "hostname": "attacker.example"}, False),
        ({"success": True}, False),
        ({"success": "true", "hostname": "govmap.us"}, False),
        ({"success": False, "hostname": "govmap.us"}, False),
        (["success"], False),
    ],
)
def test_turnstile_requires_a_well_formed_success_for_our_hostname(
    monkeypatch: pytest.MonkeyPatch, body: Any, accepted: bool
) -> None:
    post = _turnstile(monkeypatch, _VerifyResponse(body=body))
    assert report._verify_turnstile("token", "198.51.100.10") is accepted
    assert post.call_args.kwargs["allow_redirects"] is False
    assert post.call_args.kwargs["stream"] is True


def test_turnstile_dummy_secret_skips_the_hostname_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {"success": True, "hostname": "example.com"}
    _turnstile(
        monkeypatch, _VerifyResponse(body=body), secret="1x0000000000000000000000000000000AA"
    )
    assert report._verify_turnstile("XXXX.DUMMY.TOKEN.XXXX", "198.51.100.10") is True


@pytest.mark.parametrize(
    "response",
    [
        requests.ConnectionError("down"),
        _VerifyResponse(status=503, body={"success": False}),
        _VerifyResponse(content=b"not json"),
        _VerifyResponse(content=b" " * (64 * 1024 + 1)),
    ],
    ids=["unreachable", "server-error", "unparseable", "oversized"],
)
def test_turnstile_outage_fails_open_without_logging_secrets(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    response: _VerifyResponse | Exception,
) -> None:
    _turnstile(monkeypatch, response)
    assert report._verify_turnstile("token-value", "198.51.100.10") is True
    assert "real-secret-for-tests" not in caplog.text
    assert "token-value" not in caplog.text


def test_turnstile_missing_token_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    post = _turnstile(monkeypatch, _VerifyResponse(body={"success": True}))
    assert report._verify_turnstile(None, "198.51.100.10") is False
    post.assert_not_called()


@pytest.mark.parametrize("http_status", [301, 302, 307, 400, 401, 403, 429])
def test_turnstile_redirects_and_client_errors_never_fail_open(
    monkeypatch: pytest.MonkeyPatch, http_status: int
) -> None:
    _turnstile(
        monkeypatch, _VerifyResponse(status=http_status, content=b"not json")
    )
    assert report._verify_turnstile("token", "198.51.100.10") is False
