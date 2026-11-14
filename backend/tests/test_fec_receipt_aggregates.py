import asyncio
from contextlib import nullcontext
from decimal import Decimal
from typing import Any
from unittest.mock import Mock

import pytest

from app.pipelines import fec_finance
from app.services import fec_receipt_aggregates


class _Response:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, body: bytes) -> None:
        self.body = body

    def iter_content(self, chunk_size: int) -> list[bytes]:
        assert chunk_size > 0
        return [self.body]

    def close(self) -> None:
        pass


def _payload() -> dict[str, Any]:
    return {
        "results": [
            {
                "candidate_id": "H0CA00001",
                "cycle": 2026,
                "state": "CA",
                "state_full": "California",
                "count": 12,
                "total": 123.45,
            },
            {
                "candidate_id": "H0CA00001",
                "cycle": 2026,
                "state": "NY",
                "state_full": "New York",
                "count": 8,
                "total": 90.01,
            },
        ],
        "pagination": {
            "count": 2,
            "is_count_exact": True,
            "page": 1,
            "pages": 1,
        },
    }


def test_state_aggregate_preserves_exact_amounts_and_validates_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _Response(
        b'{"results":[{"candidate_id":"H0CA00001","cycle":2026,"state":"CA",'
        b'"state_full":"California","count":12,"total":123.45},'
        b'{"candidate_id":"H0CA00001","cycle":2026,"state":"NY",'
        b'"state_full":"New York","count":8,"total":90.01}],'
        b'"pagination":{"count":2,"is_count_exact":true,"page":1,"pages":1}}'
    )
    get = Mock(return_value=response)
    monkeypatch.setattr(fec_finance._session, "get", get)
    monkeypatch.setattr(fec_finance, "request_slot", lambda _source: nullcontext())

    async def upstream(
        _source: str, fn: Any, path: str, **params: Any
    ) -> dict[str, Any]:
        assert path == "schedules/schedule_a/by_state/by_candidate"
        assert params == {
            "candidate_id": "H0CA00001",
            "cycle": 2026,
            "page": 1,
            "per_page": 100,
            "decimal_json": True,
        }
        return fn(path, **params)

    monkeypatch.setattr(fec_receipt_aggregates, "run_upstream", upstream)
    result = asyncio.run(
        fec_receipt_aggregates.candidate_receipt_geography("H0CA00001", 2026)
    )

    assert [row.state for row in result.states] == ["CA", "NY"]
    assert [row.amount for row in result.states] == [Decimal("123.45"), Decimal("90.01")]
    assert result.state_group_count == 2
    assert get.call_count == 1


@pytest.mark.parametrize(
    "pagination",
    [
        {"count": 2, "is_count_exact": True, "page": 1, "pages": 2},
        {"count": 3, "is_count_exact": False, "page": 1},
    ],
)
def test_state_aggregate_rejects_unverified_completeness(
    monkeypatch: pytest.MonkeyPatch, pagination: dict[str, Any]
) -> None:
    payload = _payload()
    payload["pagination"] = pagination

    async def upstream(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return payload

    monkeypatch.setattr(fec_receipt_aggregates, "run_upstream", upstream)

    with pytest.raises(fec_receipt_aggregates.FecAggregateUnavailableError):
        asyncio.run(
            fec_receipt_aggregates.candidate_receipt_geography("H0CA00001", 2026)
        )


def test_state_aggregate_rejects_duplicate_and_foreign_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    payload["results"][1]["state"] = "CA"

    async def upstream(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return payload

    monkeypatch.setattr(fec_receipt_aggregates, "run_upstream", upstream)

    with pytest.raises(fec_receipt_aggregates.FecAggregateUnavailableError):
        asyncio.run(
            fec_receipt_aggregates.candidate_receipt_geography("H0CA00001", 2026)
        )

    payload["results"][1]["state"] = "NY"
    payload["results"][1]["candidate_id"] = "H0TX00001"
    with pytest.raises(fec_receipt_aggregates.FecAggregateUnavailableError):
        asyncio.run(
            fec_receipt_aggregates.candidate_receipt_geography("H0CA00001", 2026)
        )
