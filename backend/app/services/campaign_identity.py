"""Find separately reported finance records using exact crosswalk evidence."""

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign_money import CampaignMoneyCoverage, CandidateFinanceSummary
from app.models.crosswalk import IdCrosswalk
from app.schemas.campaign_money import RelatedCandidateOut, RelatedCandidatesOut
from app.schemas.member import CandidateMemberMatchOut
from app.services.candidate_identity import candidate_member_matches

logger = logging.getLogger(__name__)
_CANDIDATE_ID = re.compile(r"^[HSP][A-Z0-9]{8}$")


async def related_candidate_finances(
    db: AsyncSession, candidate_id: str, member_match: CandidateMemberMatchOut
) -> RelatedCandidatesOut:
    confirmed_others: list[str] = []
    withheld_count = 0
    if member_match.status == "matched":
        if member_match.profile is None:
            raise RuntimeError("Matched candidate is missing its member profile")
        profile_id = member_match.profile.bioguide_id
        crosswalk_ids = (
            await db.execute(
                select(IdCrosswalk.fec_ids).where(IdCrosswalk.bioguide_id == profile_id)
            )
        ).scalar_one()
        if candidate_id not in crosswalk_ids:
            raise RuntimeError("Matched candidate is missing from its crosswalk")
        other_ids = set(crosswalk_ids) - {candidate_id}
        valid_ids = sorted(value for value in other_ids if _CANDIDATE_ID.fullmatch(value))
        invalid_count = len(other_ids) - len(valid_ids)
        if invalid_count:
            logger.warning("Withholding %d invalid FEC IDs for %s", invalid_count, profile_id)

        matches = await candidate_member_matches(db, valid_ids)
        confirmed_others = [
            value
            for value in valid_ids
            if matches[value].status == "matched"
            and matches[value].profile is not None
            and matches[value].profile.bioguide_id == profile_id
        ]
        withheld_count = len(other_ids) - len(confirmed_others)
    confirmed = [candidate_id, *confirmed_others]
    cycles: dict[str, list[int]] = {value: [] for value in confirmed}
    rows = (
        await db.execute(
            select(CandidateFinanceSummary.candidate_id, CandidateFinanceSummary.finance_cycle)
            .join(
                CampaignMoneyCoverage,
                CampaignMoneyCoverage.finance_cycle == CandidateFinanceSummary.finance_cycle,
            )
            .where(CandidateFinanceSummary.candidate_id.in_(confirmed))
            .order_by(
                CandidateFinanceSummary.candidate_id,
                CandidateFinanceSummary.finance_cycle.desc(),
            )
        )
    ).all()
    for related_id, cycle in rows:
        cycles[related_id].append(cycle)
    return RelatedCandidatesOut(
        candidates=[
            RelatedCandidateOut(candidate_id=value, finance_cycles=cycles[value])
            for value in confirmed
        ],
        withheld_count=withheld_count,
    )
