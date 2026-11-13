import pytest

from app.pipelines import congress_gov_bills
from app.pipelines.batch import BatchResult


def test_child_pagination_page_cap_is_an_incomplete_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(congress_gov_bills, "_PAGE", 1)
    monkeypatch.setattr(congress_gov_bills, "_SUBRESOURCE_MAX_PAGES", 2)
    def get_page(path: str, *, limit: int, offset: int) -> dict:
        assert path == "bill/119/hr/1/actions"
        assert limit == 1
        assert offset in (0, 1)
        return {
            "actions": [{"id": 1}],
            "pagination": {"next": "next-page"},
        }

    monkeypatch.setattr(congress_gov_bills, "_get", get_page)

    with pytest.raises(congress_gov_bills.IncompleteBillDetailError, match="exceeded 2 pages"):
        congress_gov_bills._paginate("bill/119/hr/1/actions", "actions")


def test_child_result_cap_cannot_truncate_a_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(congress_gov_bills, "_PAGE", 2)

    def get_page(path: str, *, limit: int, offset: int) -> dict:
        assert path == "bill/119/hr/1/actions"
        assert limit == 2
        assert offset == 0
        return {"actions": [{"id": 1}, {"id": 2}], "pagination": {"next": None}}

    monkeypatch.setattr(congress_gov_bills, "_get", get_page)

    with pytest.raises(congress_gov_bills.IncompleteBillDetailError, match="result cap"):
        congress_gov_bills._paginate("bill/119/hr/1/actions", "actions", cap=1)


def test_child_pagination_follows_next_after_a_partial_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(congress_gov_bills, "_PAGE", 2)
    monkeypatch.setattr(congress_gov_bills, "_SUBRESOURCE_MAX_PAGES", 3)
    calls: list[int] = []

    def get_page(path: str, *, limit: int, offset: int) -> dict:
        assert path == "bill/119/hr/1/actions"
        assert limit == 2
        calls.append(offset)
        if offset == 0:
            return {"actions": [{"id": 1}], "pagination": {"next": "next-page"}}
        return {"actions": [{"id": 2}], "pagination": {"next": None}}

    monkeypatch.setattr(congress_gov_bills, "_get", get_page)

    assert congress_gov_bills._paginate("bill/119/hr/1/actions", "actions") == [
        {"id": 1},
        {"id": 2},
    ]
    assert calls == [0, 2]


def test_invalid_child_row_rejects_the_whole_bill_bundle() -> None:
    with pytest.raises(congress_gov_bills.IncompleteBillDetailError, match="incomplete bill bundle"):
        congress_gov_bills._validate_each(
            [{"not_a_cosponsor": True}],
            congress_gov_bills.CosponsorRaw,
            "cosponsor for hr1",
        )


def test_incomplete_child_bundles_are_never_reported_as_complete() -> None:
    result = BatchResult(total=100, succeeded=99, failed=1, incomplete=True)

    assert result.degraded
    assert "incomplete detail bundles were withheld" in (result.describe("bills") or "")
