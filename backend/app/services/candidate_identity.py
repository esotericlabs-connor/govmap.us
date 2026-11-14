"""Resolve FEC source identities to existing profiles through shared IDs only."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crosswalk import IdCrosswalk
from app.models.member import Member
from app.schemas.member import CandidateMemberMatchOut, CandidateMemberProfileOut

logger = logging.getLogger(__name__)


async def candidate_member_matches(
    db: AsyncSession, candidate_ids: list[str]
) -> dict[str, CandidateMemberMatchOut]:
    matches = {
        candidate_id: CandidateMemberMatchOut(status="unmatched") for candidate_id in candidate_ids
    }
    if not matches:
        return matches
    rows = (
        await db.execute(
            select(Member, IdCrosswalk.fec_ids)
            .join(IdCrosswalk, IdCrosswalk.bioguide_id == Member.bioguide_id)
            .where(IdCrosswalk.fec_ids.overlap(list(matches)))
        )
    ).all()
    profiles: dict[str, dict[str, CandidateMemberProfileOut]] = {}
    for member, fec_ids in rows:
        profile = CandidateMemberProfileOut.model_validate(member)
        for candidate_id in set(fec_ids):
            if candidate_id in matches:
                profiles.setdefault(candidate_id, {})[profile.bioguide_id] = profile
    for candidate_id, candidates in profiles.items():
        if len(candidates) == 1:
            matches[candidate_id] = CandidateMemberMatchOut(
                status="matched", profile=next(iter(candidates.values()))
            )
        else:
            logger.warning(
                "Withholding member link for FEC ID %s: %d conflicting Bioguide matches",
                candidate_id,
                len(candidates),
            )
            matches[candidate_id] = CandidateMemberMatchOut(status="ambiguous")
    return matches
