"""On-demand FEC aggregates that avoid exposing receipt-level donor identities."""

import logging
from datetime import UTC, datetime
from decimal import Decimal

import requests
from pydantic import ValidationError

from app.pipelines.fec_finance import FecRateLimited, _fec_get
from app.schemas.campaign_money import (
    CandidateReceiptGeographyOut,
    CandidateReceiptStateOut,
    FecScheduleAStatePageRaw,
)
from app.services.upstream import UpstreamCapacityError, run_upstream

logger = logging.getLogger(__name__)
_PAGE_SIZE = 100


class FecAggregateUnavailableError(RuntimeError):
    """The FEC aggregate response failed validation or was incomplete."""


async def candidate_receipt_geography(
    candidate_id: str, cycle: int
) -> CandidateReceiptGeographyOut:
    try:
        payload = await run_upstream(
            "fec",
            _fec_get,
            "schedules/schedule_a/by_state/by_candidate",
            candidate_id=candidate_id,
            cycle=cycle,
            page=1,
            per_page=_PAGE_SIZE,
            decimal_json=True,
        )
        page = FecScheduleAStatePageRaw.model_validate(payload)
    except UpstreamCapacityError:
        raise
    except (FecRateLimited, requests.RequestException, ValidationError, ValueError, RuntimeError) as exc:
        logger.warning(
            "FEC state aggregates unavailable for %s/%d (%s)",
            candidate_id,
            cycle,
            type(exc).__name__,
        )
        raise FecAggregateUnavailableError("FEC state aggregates are unavailable") from None

    if len(page.results) >= _PAGE_SIZE or page.pagination.count > _PAGE_SIZE:
        raise FecAggregateUnavailableError(
            "FEC state aggregate result exceeds the supported complete-page bound"
        )
    if page.pagination.is_count_exact is True and page.pagination.count != len(page.results):
        raise FecAggregateUnavailableError("FEC state aggregate count did not match its rows")
    if page.pagination.pages not in (None, 0, 1) or (
        page.results and page.pagination.pages == 0
    ):
        raise FecAggregateUnavailableError("FEC state aggregate response requires pagination")
    if page.pagination.is_count_exact is False and page.pagination.pages is None:
        raise FecAggregateUnavailableError("FEC state aggregate completeness could not be verified")
    if page.pagination.pages == 1 and not page.results:
        raise FecAggregateUnavailableError("FEC state aggregate page count conflicts with its rows")
    if any(row.candidate_id != candidate_id or row.cycle != cycle for row in page.results):
        raise FecAggregateUnavailableError("FEC state aggregate returned a different candidate or cycle")
    states = [row.state for row in page.results]
    if len(states) != len(set(states)):
        raise FecAggregateUnavailableError("FEC state aggregate contains duplicate state groups")

    return CandidateReceiptGeographyOut(
        candidate_id=candidate_id,
        finance_cycle=cycle,
        fetched_at=datetime.now(UTC),
        state_group_count=len(page.results),
        source_count_exact=page.pagination.is_count_exact,
        states=[
            CandidateReceiptStateOut(
                state=row.state,
                state_full=row.state_full,
                receipt_count=row.count,
                amount=Decimal(row.total),
            )
            for row in sorted(
                page.results,
                key=lambda row: (
                    row.state is None,
                    -row.total,
                    row.state or "",
                ),
            )
        ],
    )
