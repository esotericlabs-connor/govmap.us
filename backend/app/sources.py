"""Registry of the upstream sources GovMap refreshes.

One entry per refresh source (the name recorded in pipeline_status and
source_runs). URLs and staging paths are read from the pipeline modules, so the
registry can't drift from what the code actually fetches. Refresh cadence lives
in app.scheduler.JOBS; tests/test_sources.py checks that every registered
source has a refresher and a scheduled job, and the reverse.

`rights` stays None until the source's terms of use have been reviewed and
recorded; nothing here asserts a license.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.pipelines import (
    congress_committee_meetings,
    congress_gov_bills,
    congress_legislators,
    congress_member_sponsored,
    fec_candidates,
    fec_election_calendar,
    fec_finance,
    house_clerk_votes,
    senate_lis_votes,
    voteview_senate_votes,
    zip_crosswalk,
)


@dataclass(frozen=True)
class Endpoint:
    url: str
    # True when the publisher is the government body that produces the record.
    official: bool


@dataclass(frozen=True)
class SourceSpec:
    name: str
    title: str
    publisher: str
    endpoints: tuple[Endpoint, ...]
    # Environment variable holding the credential, or None for open access.
    auth_env: str | None
    staging_files: tuple[Path, ...]
    rights: str | None = None


_CONGRESS_GOV = Endpoint(congress_gov_bills.API_BASE, official=True)

SOURCES: dict[str, SourceSpec] = {
    spec.name: spec
    for spec in (
        SourceSpec(
            name="congress_legislators",
            title="Current legislators, committees, and committee memberships",
            publisher="@unitedstates congress-legislators project",
            endpoints=(
                Endpoint(congress_legislators.LEGISLATORS_URL, official=False),
                Endpoint(congress_legislators.COMMITTEES_URL, official=False),
                Endpoint(congress_legislators.MEMBERSHIP_URL, official=False),
            ),
            auth_env=None,
            staging_files=(
                congress_legislators.STAGING_LEGISLATORS,
                congress_legislators.STAGING_COMMITTEES,
                congress_legislators.STAGING_MEMBERSHIP,
            ),
        ),
        SourceSpec(
            name="congress_gov_bills",
            title="Recently updated bills with actions and cosponsors",
            publisher="Library of Congress (Congress.gov API)",
            endpoints=(_CONGRESS_GOV,),
            auth_env="CONGRESS_GOV_API_KEY",
            staging_files=(congress_gov_bills.STAGING_BILLS,),
        ),
        SourceSpec(
            name="votes",
            title="House and Senate roll-call votes",
            publisher="Clerk of the House; Senate LIS (Voteview fallback)",
            endpoints=(
                Endpoint(house_clerk_votes.HOUSE_BASE, official=True),
                Endpoint(senate_lis_votes.SENATE_MENU, official=True),
                Endpoint(senate_lis_votes.SENATE_VOTES, official=True),
                Endpoint(voteview_senate_votes.VOTEVIEW_BASE, official=False),
            ),
            auth_env=None,
            staging_files=(house_clerk_votes.STAGING, senate_lis_votes.STAGING),
        ),
        SourceSpec(
            name="member_sponsored",
            title="Legislation sponsored by each current member",
            publisher="Library of Congress (Congress.gov API)",
            endpoints=(_CONGRESS_GOV,),
            auth_env="CONGRESS_GOV_API_KEY",
            staging_files=(congress_member_sponsored.STAGING_PATH,),
        ),
        SourceSpec(
            name="fec_candidates",
            title="FEC candidate registrations and contest metadata",
            publisher="Federal Election Commission (OpenFEC API)",
            endpoints=(Endpoint(fec_finance.FEC_BASE, official=True),),
            auth_env="FEC_API_KEY",
            staging_files=(fec_candidates.STAGING_PATH,),
        ),
        SourceSpec(
            name="fec_election_calendar",
            title="FEC-reported federal election dates",
            publisher="Federal Election Commission (OpenFEC API)",
            endpoints=(
                Endpoint(f"{fec_finance.FEC_BASE}/calendar-dates/", official=True),
            ),
            auth_env="FEC_API_KEY",
            staging_files=(fec_election_calendar.STAGING_PATH,),
        ),
        SourceSpec(
            name="fec_finance",
            title="Campaign-finance totals per member",
            publisher="Federal Election Commission (OpenFEC API)",
            endpoints=(Endpoint(fec_finance.FEC_BASE, official=True),),
            auth_env="FEC_API_KEY",
            staging_files=(fec_finance.STAGING_PATH,),
        ),
        SourceSpec(
            name="committee_meetings",
            title="Committee meetings and hearings",
            publisher="Library of Congress (Congress.gov API)",
            endpoints=(_CONGRESS_GOV,),
            auth_env="CONGRESS_GOV_API_KEY",
            staging_files=(congress_committee_meetings.STAGING_PATH,),
        ),
        SourceSpec(
            name="backfill_bills",
            title="Enrichment of sponsored-legislation bills not yet detailed",
            publisher="Library of Congress (Congress.gov API)",
            endpoints=(_CONGRESS_GOV,),
            auth_env="CONGRESS_GOV_API_KEY",
            # Reads and writes the database directly; no staging file.
            staging_files=(),
        ),
        SourceSpec(
            name="zip_districts",
            title="ZIP code to congressional district crosswalk",
            publisher="HUD Office of Policy Development and Research (USPS crosswalk)",
            endpoints=(Endpoint(zip_crosswalk.HUD_URL, official=True),),
            auth_env="HUD_API_TOKEN",
            staging_files=(zip_crosswalk.STAGING_PATH,),
        ),
    )
}
