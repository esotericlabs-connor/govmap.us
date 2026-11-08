from collections import deque
from collections.abc import Iterator

import pytest
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
