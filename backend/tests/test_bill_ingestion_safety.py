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


@pytest.mark.parametrize(
    "record",
    [
        {"not_a_cosponsor": True},
        {"bioguideId": None},
        {"bioguideId": ""},
        {"bioguideId": " "},
        {"bioguideId": "A00001"},
        {"bioguideId": "A0000001"},
        {"bioguideId": "a000001"},
        {"bioguideId": "A00000!"},
        {"bioguideId": "A00000\u0661"},
        {"bioguideId": "A000001\n"},
        {"bioguideId": 123},
    ],
)
def test_invalid_child_row_rejects_the_whole_bill_bundle(record: dict) -> None:
    with pytest.raises(congress_gov_bills.IncompleteBillDetailError, match="incomplete bill bundle"):
        congress_gov_bills._validate_each(
            [{"bioguideId": "C001078"}, record],
            congress_gov_bills.CosponsorRaw,
            "cosponsor for hr1",
        )


def test_valid_cosponsor_keeps_optional_metadata_and_ignores_extra_fields() -> None:
    rows = congress_gov_bills._validate_each(
        [
            {
                "bioguideId": "C001078",
                "sponsorshipDate": "2025-01-03",
                "isOriginalCosponsor": True,
                "fullName": "Example member",
            },
            {"bioguideId": "A000001"},
        ],
        congress_gov_bills.CosponsorRaw,
        "cosponsor for hr1",
    )

    assert rows == [
        {
            "bioguideId": "C001078",
            "sponsorshipDate": "2025-01-03",
            "isOriginalCosponsor": True,
        },
        {"bioguideId": "A000001", "sponsorshipDate": None, "isOriginalCosponsor": None},
    ]


def test_fetch_rejects_a_bill_with_an_unidentified_cosponsor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def get_page(path: str, **params: object) -> dict:
        if path == "bill/119/hr/1":
            assert not params
            return {"bill": {"congress": 119, "type": "HR", "number": 1}}
        assert params == {"limit": congress_gov_bills._PAGE, "offset": 0}
        if path == "bill/119/hr/1/actions":
            return {"actions": [], "pagination": {}}
        if path == "bill/119/hr/1/cosponsors":
            return {"cosponsors": [{"fullName": "Unidentified member"}], "pagination": {}}
        raise AssertionError(f"unexpected request: {path}")

    monkeypatch.setattr(congress_gov_bills, "_get", get_page)

    with pytest.raises(congress_gov_bills.IncompleteBillDetailError, match="cosponsor"):
        congress_gov_bills._fetch_one(119, "HR", 1)


def test_batch_withholds_incomplete_bill_and_stages_complete_bills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(congress_gov_bills.settings, "congress_gov_api_key", "test-key")
    monkeypatch.setattr(congress_gov_bills.settings, "congress_number", 119)
    monkeypatch.setattr(congress_gov_bills.settings, "congress_gov_bill_limit", 2)
    monkeypatch.setattr(congress_gov_bills.settings, "congress_gov_bills_max_seconds", 60)
    monkeypatch.setattr(congress_gov_bills.settings, "congress_max_consecutive_failures", 2)
    staged: list[dict] = []

    def bill_list(congress: int, cap: int) -> list:
        assert (congress, cap) == (119, 2)
        return [
            congress_gov_bills.BillListItemRaw(congress=119, type="HR", number=1),
            congress_gov_bills.BillListItemRaw(congress=119, type="HR", number=2),
        ]

    def fetch(congress: int, bill_type: str, number: int) -> dict:
        assert (congress, bill_type) == (119, "HR")
        if number == 1:
            raise congress_gov_bills.IncompleteBillDetailError("invalid cosponsor")
        return {"bill": {"congress": congress, "type": bill_type, "number": number}}

    def stage(path: object, data: list[dict]) -> None:
        assert path == congress_gov_bills.STAGING_BILLS
        staged.extend(data)

    monkeypatch.setattr(congress_gov_bills, "_bill_list", bill_list)
    monkeypatch.setattr(congress_gov_bills, "_fetch_one", fetch)
    monkeypatch.setattr(congress_gov_bills, "_stage", stage)

    result = congress_gov_bills.run()

    assert (result.total, result.succeeded, result.failed) == (2, 1, 1)
    assert result.incomplete and result.degraded
    assert [bundle["bill"]["number"] for bundle in staged] == [2]


def test_incomplete_child_bundles_are_never_reported_as_complete() -> None:
    result = BatchResult(total=100, succeeded=99, failed=1, incomplete=True)

    assert result.degraded
    assert "incomplete detail bundles were withheld" in (result.describe("bills") or "")
