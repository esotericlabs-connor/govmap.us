"""Candidate-level FEC financial summaries, without donor-level assertions."""

import logging
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import begin_consistent_read, get_db
from app.models.campaign_money import (
    CampaignMoneyCoverage,
    CandidateCommitteeLink,
    CandidateFinanceSummary,
)
from app.models.election import ElectionCandidate
from app.schemas.campaign_money import (
    CampaignMoneyCoverageOut,
    CandidateFinanceOut,
    CandidateMoneyDetailOut,
    CandidateMoneyListOut,
    CandidateReceiptGeographyOut,
    CatalogMatchOut,
    CommitteeLinkOut,
    ReportingDateOut,
)
from app.services.campaign_identity import related_candidate_finances
from app.services.candidate_identity import candidate_member_matches
from app.services.fec_receipt_aggregates import (
    FecAggregateUnavailableError,
    candidate_receipt_geography,
)
from app.services.search import match_words
from app.types import MAX_LIST_OFFSET

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/money", tags=["campaign money"])
_MAX_REPORTING_DATES = 100


async def _coverage(db: AsyncSession, cycle: int) -> CampaignMoneyCoverage | None:
    # A refresh replaces all three tables atomically. Keep every query in this
    # response on the same database snapshot, including the coverage metadata.
    await begin_consistent_read(db)
    return (
        await db.execute(
            select(CampaignMoneyCoverage).where(CampaignMoneyCoverage.finance_cycle == cycle)
        )
    ).scalar_one_or_none()


@router.get("/candidates", response_model=CandidateMoneyListOut)
async def list_candidate_money(
    db: AsyncSession = Depends(get_db),
    cycle: int = Query(default=settings.fec_cycle, ge=2000, le=2098, multiple_of=2),
    office: Literal["H", "S", "P"] = "H",
    state: str | None = Query(default=None, pattern=r"^[A-Za-z]{2}$"),
    district: str | None = Query(default=None, pattern=r"^[0-9]{2}$"),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    through: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=MAX_LIST_OFFSET),
    sort: Literal["receipts", "disbursements", "cash", "name", "name_desc"] = "receipts",
) -> CandidateMoneyListOut:
    if district is not None and (state is None or office != "H"):
        raise HTTPException(
            status_code=422, detail="A district filter requires a state and House office"
        )
    generated_at = datetime.now(UTC)
    coverage = await _coverage(db, cycle)
    if coverage is None:
        return CandidateMoneyListOut(
            generated_at=generated_at,
            finance_cycle=cycle,
            available=False,
            coverage=None,
            matching_count=0,
            filtered_count=0,
            reporting_dates=[],
            reporting_dates_truncated=False,
            selected_date=through,
            limit=limit,
            offset=offset,
            candidates=[],
        )

    filters = [
        CandidateFinanceSummary.finance_cycle == cycle,
        CandidateFinanceSummary.office == office,
    ]
    if state is not None:
        filters.append(CandidateFinanceSummary.state == state.upper())
    if district is not None:
        filters.append(CandidateFinanceSummary.district == district)
    if q is not None and q.strip():
        filters.append(
            match_words(q, CandidateFinanceSummary.name, CandidateFinanceSummary.candidate_id)
        )

    matching_count = (
        await db.execute(
            select(func.count()).select_from(CandidateFinanceSummary).where(*filters)
        )
    ).scalar_one()
    period_count = func.count(CandidateFinanceSummary.candidate_id).label("candidate_count")
    period_rows = (
        await db.execute(
            select(CandidateFinanceSummary.coverage_end, period_count)
            .where(*filters, CandidateFinanceSummary.coverage_end.is_not(None))
            .group_by(CandidateFinanceSummary.coverage_end)
            .order_by(period_count.desc(), CandidateFinanceSummary.coverage_end.desc())
            .limit(_MAX_REPORTING_DATES + 1)
        )
    ).all()
    periods = [
        ReportingDateOut(coverage_end=end, candidate_count=count)
        for end, count in period_rows[:_MAX_REPORTING_DATES]
        if end is not None
    ]
    selected_date = through
    if selected_date is None and periods:
        selected_date = next(
            (period.coverage_end for period in periods if period.coverage_end <= coverage.fetched_at.date()),
            periods[0].coverage_end,
        )

    filtered_count = 0
    candidates: list[CandidateFinanceOut] = []
    if selected_date is not None:
        selected_filters = [*filters, CandidateFinanceSummary.coverage_end == selected_date]
        filtered_count = (
            await db.execute(
                select(func.count()).select_from(CandidateFinanceSummary).where(*selected_filters)
            )
        ).scalar_one()
        rows = (
            await db.execute(
                select(CandidateFinanceSummary)
                .where(*selected_filters)
                .order_by(
                    {
                        "receipts": CandidateFinanceSummary.receipts.desc().nulls_last(),
                        "disbursements": CandidateFinanceSummary.disbursements.desc().nulls_last(),
                        "cash": CandidateFinanceSummary.cash_on_hand.desc().nulls_last(),
                        "name": CandidateFinanceSummary.name.asc().nulls_last(),
                        "name_desc": CandidateFinanceSummary.name.desc().nulls_last(),
                    }[sort],
                    CandidateFinanceSummary.candidate_id,
                )
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
        member_matches = await candidate_member_matches(db, [row.candidate_id for row in rows])
        candidates = [
            CandidateFinanceOut.model_validate(row).model_copy(
                update={"member_match": member_matches[row.candidate_id]}
            )
            for row in rows
        ]

    return CandidateMoneyListOut(
        generated_at=generated_at,
        finance_cycle=cycle,
        available=True,
        coverage=CampaignMoneyCoverageOut.model_validate(coverage),
        matching_count=matching_count,
        filtered_count=filtered_count,
        reporting_dates=periods,
        reporting_dates_truncated=len(period_rows) > _MAX_REPORTING_DATES,
        selected_date=selected_date,
        limit=limit,
        offset=offset,
        candidates=candidates,
    )


@router.get(
    "/candidates/{candidate_id}/receipt-geography",
    response_model=CandidateReceiptGeographyOut,
)
async def candidate_receipt_geography_endpoint(
    candidate_id: str = Path(pattern=r"^[HSP][A-Z0-9]{8}$"),
    cycle: int = Query(default=settings.fec_cycle, ge=2000, le=2098, multiple_of=2),
    db: AsyncSession = Depends(get_db),
) -> CandidateReceiptGeographyOut:
    if not settings.fec_api_key:
        raise HTTPException(status_code=503, detail="FEC aggregate API key is not configured")
    coverage = await _coverage(db, cycle)
    if coverage is None:
        raise HTTPException(status_code=404, detail="Candidate finance snapshot is not loaded")
    candidate = (
        await db.execute(
            select(CandidateFinanceSummary.candidate_id).where(
                CandidateFinanceSummary.finance_cycle == cycle,
                CandidateFinanceSummary.candidate_id == candidate_id,
            )
        )
    ).scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate finance record was not found")
    await db.commit()
    try:
        return await candidate_receipt_geography(candidate_id, cycle)
    except FecAggregateUnavailableError as exc:
        logger.warning("FEC aggregate request failed for %s/%d", candidate_id, cycle)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/candidates/{candidate_id}", response_model=CandidateMoneyDetailOut)
async def candidate_money_detail(
    candidate_id: str = Path(pattern=r"^[HSP][A-Z0-9]{8}$"),
    cycle: int = Query(default=settings.fec_cycle, ge=2000, le=2098, multiple_of=2),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=MAX_LIST_OFFSET),
    db: AsyncSession = Depends(get_db),
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    sort: Literal["recent", "committee", "designation"] = "recent",
) -> CandidateMoneyDetailOut:
    coverage = await _coverage(db, cycle)
    if coverage is None:
        raise HTTPException(status_code=404, detail="Candidate finance snapshot is not loaded")
    candidate = (
        await db.execute(
            select(CandidateFinanceSummary).where(
                CandidateFinanceSummary.finance_cycle == cycle,
                CandidateFinanceSummary.candidate_id == candidate_id,
            )
        )
    ).scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate finance record was not found")
    catalog = (
        await db.execute(
            select(ElectionCandidate).where(
                ElectionCandidate.finance_cycle == cycle,
                ElectionCandidate.candidate_id == candidate_id,
            )
        )
    ).scalar_one_or_none()
    link_filter = (
        CandidateCommitteeLink.finance_cycle == cycle,
        CandidateCommitteeLink.subject_id == candidate_id,
    )
    linkage_count = (
        await db.execute(
            select(func.count()).select_from(CandidateCommitteeLink).where(*link_filter)
        )
    ).scalar_one()
    filtered_links = list(link_filter)
    if q is not None and q.strip():
        filtered_links.append(
            match_words(
                q, CandidateCommitteeLink.committee_id,
                CandidateCommitteeLink.designation, CandidateCommitteeLink.committee_type,
            )
        )
    filtered_linkage_count = (
        await db.execute(
            select(func.count()).select_from(CandidateCommitteeLink).where(*filtered_links)
        )
    ).scalar_one()
    links = (
        await db.execute(
            select(CandidateCommitteeLink)
            .where(*filtered_links)
            .order_by(
                {
                    "recent": CandidateCommitteeLink.candidate_election_year.desc(),
                    "committee": CandidateCommitteeLink.committee_id.asc().nulls_last(),
                    "designation": CandidateCommitteeLink.designation.asc().nulls_last(),
                }[sort],
                CandidateCommitteeLink.designation,
                CandidateCommitteeLink.committee_id,
                CandidateCommitteeLink.linkage_id,
            )
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    member_matches = await candidate_member_matches(db, [candidate_id])
    related_candidates = await related_candidate_finances(
        db, candidate_id, member_matches[candidate_id]
    )
    return CandidateMoneyDetailOut(
        generated_at=datetime.now(UTC),
        coverage=CampaignMoneyCoverageOut.model_validate(coverage),
        candidate=CandidateFinanceOut.model_validate(candidate).model_copy(
            update={"member_match": member_matches[candidate_id]}
        ),
        catalog_match=CatalogMatchOut.model_validate(catalog) if catalog else None,
        related_candidates=related_candidates,
        linkage_count=linkage_count,
        filtered_linkage_count=filtered_linkage_count,
        limit=limit,
        offset=offset,
        linkages=[CommitteeLinkOut.model_validate(link) for link in links],
    )
