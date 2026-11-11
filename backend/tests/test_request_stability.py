import asyncio
import logging
import os
from unittest.mock import AsyncMock, Mock

import pytest
import requests
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials
from sqlalchemy import literal, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models.contribution import DonationFetch
from app.pipelines import status
from app.routers import pipeline_status, search
from app.services import donations
from app.services.search import substring_pattern


@pytest.mark.parametrize(
    ("configured_user", "configured_password", "user", "password", "accepted"),
    [
        ("operator", "example-password", "operator", "example-password", True),
        ("operator", "example-password", "other", "example-password", False),
        ("operator", "example-password", "operator", "wrong", False),
        ("", "", "", "", False),
        ("operator", "", "operator", "", False),
        ("", "example-password", "", "example-password", False),
        ("operator", "example-password", "\u00e9", "example-password", False),
        ("operator", "example-password", "operator", "\u00e9", False),
        ("\u00e9", "example-password", "operator", "example-password", False),
        ("operator", "\u00e9", "operator", "example-password", False),
    ],
)
def test_internal_auth_rejects_bad_credentials_without_500(
    monkeypatch: pytest.MonkeyPatch,
    configured_user: str,
    configured_password: str,
    user: str,
    password: str,
    accepted: bool,
) -> None:
    monkeypatch.setattr(settings, "internal_user", configured_user)
    monkeypatch.setattr(settings, "internal_password", configured_password)
    credentials = HTTPBasicCredentials(username=user, password=password)
    if accepted:
        pipeline_status.require_internal_auth(credentials)
    else:
        with pytest.raises(HTTPException) as caught:
            pipeline_status.require_internal_auth(credentials)
        assert caught.value.status_code == 401
        assert caught.value.headers == {"WWW-Authenticate": "Basic"}


def test_unconfigured_webhook_does_not_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "alert_webhook_url", "")
    post = Mock()
    monkeypatch.setattr(status.requests, "post", post)
    asyncio.run(status.send_alert("example"))
    post.assert_not_called()


@pytest.mark.parametrize("http_status", [200, 202, 204, 301, 302, 307, 400, 401, 429, 500])
def test_webhook_http_outcome_is_checked_and_response_closed(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    http_status: int,
) -> None:
    url = "https://example.invalid/private-webhook-token"
    text = "private notification contents"
    monkeypatch.setattr(settings, "alert_webhook_url", url)
    response = Mock(status_code=http_status)
    post = Mock(return_value=response)
    monkeypatch.setattr(status.requests, "post", post)
    caplog.set_level(logging.WARNING, logger="app.pipelines.status")
    asyncio.run(status.send_alert(text))
    post.assert_called_once_with(
        url, json={"text": text}, timeout=10, allow_redirects=False, stream=True
    )
    response.close.assert_called_once_with()
    if 200 <= http_status < 300:
        assert not caplog.records
    else:
        assert f"HTTP {http_status}" in caplog.text
    assert url not in caplog.text
    assert text not in caplog.text


@pytest.mark.parametrize(
    "error", [requests.Timeout, requests.ConnectionError, requests.TooManyRedirects]
)
def test_webhook_transport_failure_is_logged_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: type[requests.RequestException],
) -> None:
    monkeypatch.setattr(settings, "alert_webhook_url", "https://example.invalid/token")
    monkeypatch.setattr(
        status.requests, "post", Mock(side_effect=error("private URL and payload"))
    )
    caplog.set_level(logging.WARNING, logger="app.pipelines.status")
    asyncio.run(status.send_alert("private notification"))
    assert error.__name__ in caplog.text
    assert "private" not in caplog.text
    assert "token" not in caplog.text


def test_webhook_programming_errors_are_not_silently_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "alert_webhook_url", "https://example.invalid/token")
    monkeypatch.setattr(status.requests, "post", Mock(side_effect=TypeError("bug")))
    with pytest.raises(TypeError, match="bug"):
        asyncio.run(status.send_alert("example"))


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("Ada", "%Ada%"),
        ("100%", "%100\\%%"),
        ("a_b", "%a\\_b%"),
        ("a\\b", "%a\\\\b%"),
        ("\\%_", "%\\\\\\%\\_%"),
    ],
)
def test_literal_substring_pattern_is_shared(term: str, expected: str) -> None:
    assert substring_pattern(term) == expected
    assert search.substring_pattern is donations.substring_pattern


def test_donation_search_binds_literal_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "fec_api_key", "")
    state = DonationFetch(
        bioguide_id="A000001", cycle=2026, resolved=True, fetched_count=0, complete=True
    )
    db = AsyncMock()
    db.get.return_value = state
    count = Mock()
    count.scalar_one.return_value = 0
    items = Mock()
    items.scalars.return_value.all.return_value = []
    db.execute.side_effect = [count, items]
    query = "100%_\\"
    result = asyncio.run(
        donations.get_donations(db, "A000001", 2026, 0, 50, q=query)
    )
    assert result["q"] == query
    for call in db.execute.call_args_list:
        compiled = call.args[0].compile(dialect=postgresql.dialect())
        assert substring_pattern(query) in compiled.params.values()
        assert "ESCAPE" in str(compiled)
        assert query not in str(compiled)


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
def test_literal_search_against_postgres() -> None:
    async def verify() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        try:
            async with engine.connect() as connection:
                for term, matching, nonmatching in [
                    ("100%", "gave 100% today", "gave 1000 today"),
                    ("a_b", "Ada a_b Smith", "Ada axb Smith"),
                    ("a\\b", "Ada a\\b Smith", "Ada ab Smith"),
                ]:
                    pattern = substring_pattern(term)
                    result = await connection.execute(
                        select(
                            literal(matching).ilike(pattern, escape="\\"),
                            literal(nonmatching).ilike(pattern, escape="\\"),
                        )
                    )
                    assert tuple(result.one()) == (True, False)
        finally:
            await engine.dispose()

    asyncio.run(verify())
