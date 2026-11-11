import time

import pytest

from app.normalize.bills import _strip_html


def test_summary_html_becomes_plain_text_with_bullets() -> None:
    raw = (
        "<p>The bill <b>does</b> X &amp; Y.</p>"
        "<ul><li>One</li><li class='a'>Two</li></ul>"
    )
    assert _strip_html(raw) == "The bill does X & Y.\n\n• One\n\n• Two"


def test_empty_summary_is_none() -> None:
    assert _strip_html(None) is None
    assert _strip_html("<p> </p>") is None


@pytest.mark.parametrize(
    "raw",
    ["<" * 200_000, "<li" * 100_000, "<br" + " " * 200_000],
    ids=["unclosed-tags", "unclosed-list-items", "unclosed-break"],
)
def test_summary_reduction_stays_linear_on_malformed_input(raw: str) -> None:
    started = time.monotonic()
    _strip_html(raw)
    assert time.monotonic() - started < 2
