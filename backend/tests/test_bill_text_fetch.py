import asyncio
import contextlib
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
import requests
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.services import bill_enrich

TEXT_URL = "https://www.congress.gov/119/bills/hr1/BILLS-119hr1ih.htm"


class _Response:
    def __init__(
        self,
        status: int = 200,
        body: bytes = b"",
        location: str | None = None,
        encoding: str | None = "utf-8",
    ) -> None:
        self.status_code = status
        self.headers = {"location": location} if location else {}
        self.is_redirect = location is not None
        self.encoding = encoding
        self.closed = False
        self._body = body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.closed = True

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        for i in range(0, len(self._body), 4):
            yield self._body[i : i + 4]


@pytest.fixture(autouse=True)
def no_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bill_enrich, "request_slot", lambda _source: contextlib.nullcontext())


@pytest.mark.parametrize(
    "url",
    [
        TEXT_URL,
        "https://congress.gov/119/bills/hr1/BILLS-119hr1ih.htm",
        "https://www.govinfo.gov/content/pkg/BILLS-119hr1ih/html/BILLS-119hr1ih.htm",
        "https://WWW.CONGRESS.GOV:443/119/bills/hr1/BILLS-119hr1ih.htm",
    ],
)
def test_official_text_hosts_are_allowed(url: str) -> None:
    bill_enrich._check_text_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.congress.gov/119/bills/hr1/BILLS-119hr1ih.htm",
        "https://www.congress.gov.attacker.example/x.htm",
        "https://www.congress.gov@attacker.example/x.htm",
        "https://user@www.congress.gov/x.htm",
        "https://www.congress.gov:8443/x.htm",
        "https://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "https://www.congress.gov:bad/x.htm",
    ],
)
def test_other_text_urls_are_refused(url: str) -> None:
    with pytest.raises(ValueError):
        bill_enrich._check_text_url(url)


def test_redirect_off_the_allowlist_is_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    first = _Response(301, location="https://attacker.example/x.htm")
    get = Mock(side_effect=[first])
    monkeypatch.setattr(bill_enrich.requests, "get", get)
    with pytest.raises(ValueError, match="refusing"):
        bill_enrich._fetch_url(TEXT_URL)
    assert get.call_count == 1
    assert first.closed


def test_relative_redirect_on_an_allowed_host_is_followed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = _Response(body=b"<pre>SEC. 1.</pre>")
    get = Mock(
        side_effect=[_Response(302, location="/119/bills/hr1/BILLS-119hr1rh.htm"), final]
    )
    monkeypatch.setattr(bill_enrich.requests, "get", get)
    assert bill_enrich._fetch_url(TEXT_URL) == ("<pre>SEC. 1.</pre>", False)
    assert get.call_args.args[0] == "https://www.congress.gov/119/bills/hr1/BILLS-119hr1rh.htm"
    assert get.call_args.kwargs["allow_redirects"] is False
    assert get.call_args.kwargs["stream"] is True
    assert final.closed


def test_redirect_loops_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    get = Mock(side_effect=lambda *_a, **_k: _Response(301, location=TEXT_URL))
    monkeypatch.setattr(bill_enrich.requests, "get", get)
    with pytest.raises(ValueError, match="too many redirects"):
        bill_enrich._fetch_url(TEXT_URL)
    assert get.call_count == bill_enrich._TEXT_MAX_REDIRECTS + 1


def test_oversized_body_is_cut_at_the_byte_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bill_enrich, "_TEXT_MAX_BYTES", 10)
    response = _Response(body=b"0123456789abcdef", encoding="no-such-codec")
    monkeypatch.setattr(bill_enrich.requests, "get", Mock(return_value=response))
    assert bill_enrich._fetch_url(TEXT_URL) == ("0123456789", True)


def test_unclosed_final_pre_block_still_yields_text() -> None:
    doc = "<html><title>Header</title><pre>SEC. 1. Short title.\n  (a) In general"
    assert bill_enrich._html_to_text(doc) == "SEC. 1. Short title.\n  (a) In general"


def test_cut_short_text_is_stored_as_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    stored = SimpleNamespace(
        bill_id="hr1-119",
        text_version="Introduced in House",
        source_url=TEXT_URL,
        plain="SEC. 1.",
        truncated=True,
        fetched_at=None,
    )
    db = SimpleNamespace(
        get=AsyncMock(side_effect=[None, SimpleNamespace(bill_id="hr1-119"), stored]),
        commit=AsyncMock(side_effect=lambda: events.append("commit")),
        execute=AsyncMock(),
    )

    async def upstream(_source: str, fn: Any, *_args: Any, **_kwargs: Any) -> Any:
        events.append("fetch")
        if fn is bill_enrich._get:
            return {
                "textVersions": [
                    {
                        "type": "Introduced in House",
                        "date": "2025-01-03",
                        "formats": [{"type": "Formatted Text", "url": TEXT_URL}],
                    }
                ]
            }
        assert fn is bill_enrich._fetch_url
        return "<pre>SEC. 1.</pre>", True

    monkeypatch.setattr(settings, "congress_gov_api_key", "test-placeholder")
    monkeypatch.setattr(bill_enrich, "run_upstream", upstream)
    payload = asyncio.run(bill_enrich.get_bill_text(db, "hr1-119"))

    assert payload is not None and payload["truncated"] is True
    assert events[:2] == ["commit", "fetch"]
    params = db.execute.await_args.args[0].compile(dialect=postgresql.dialect()).params
    assert params["plain"] == "SEC. 1."
    assert params["truncated"] is True


def test_enriched_bill_is_expired_so_the_caller_rereads_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = SimpleNamespace(enriched_at=None)
    events: list[str] = []
    db = SimpleNamespace(
        get=AsyncMock(return_value=stub),
        commit=AsyncMock(side_effect=lambda: events.append("commit")),
        execute=AsyncMock(),
        expire=Mock(),
    )

    async def upstream(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        events.append("fetch")
        return {
            "bill": {"congress": 119, "type": "HR", "number": 1, "title": "Enriched"},
            "actions": [],
            "cosponsors": [],
            "summaries": [],
            "text_versions": [],
        }

    monkeypatch.setattr(settings, "congress_gov_api_key", "test-placeholder")
    monkeypatch.setattr(bill_enrich, "run_upstream", upstream)
    assert asyncio.run(bill_enrich.enrich_bill(db, "hr1-119")) is True

    assert events == ["commit", "fetch", "commit"]
    db.expire.assert_called_once_with(stub)
    upsert = str(db.execute.await_args_list[0].args[0].compile(dialect=postgresql.dialect()))
    assert "updated_at = now()" in upsert
