"""Layer 1 pipeline: pull the unitedstates/congress-legislators data family,
validate, and stage.

Source: https://github.com/unitedstates/congress-legislators — no auth, no rate
limit. One "source" that yields three staged files (legislators, committees,
committee memberships), which feed the members, id_crosswalk, committees, and
committee_memberships tables. This is the golden pipeline pattern the later
sources clone (see CODE-MANIFEST): pull -> validate (skip bad rows, fail loudly
if nothing survives) -> stage. It stays DB-free (network + filesystem only);
status is recorded by app.pipelines.refresh.

Run directly: `python -m app.pipelines.congress_legislators`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import requests
import yaml
from pydantic import BaseModel, ValidationError

from app.schemas.committee import CommitteeMemberRaw, CommitteeRaw
from app.schemas.member import LegislatorRaw

logger = logging.getLogger(__name__)

BASE = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main"
LEGISLATORS_URL = f"{BASE}/legislators-current.yaml"
COMMITTEES_URL = f"{BASE}/committees-current.yaml"
MEMBERSHIP_URL = f"{BASE}/committee-membership-current.yaml"

SOURCE_NAME = "congress_legislators"

# backend/app/pipelines/congress_legislators.py -> parents[2] == backend/
STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING_LEGISLATORS = STAGING_DIR / "legislators_raw.json"
STAGING_COMMITTEES = STAGING_DIR / "committees_raw.json"
STAGING_MEMBERSHIP = STAGING_DIR / "committee_membership_raw.json"


def _fetch_yaml(url: str):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return yaml.safe_load(response.text)


def _validate_list(records: list, model: type[BaseModel], label: str) -> list[dict]:
    """Validate each record; skip and log individually bad ones, but raise if
    nothing survives (a source-shape change, not a one-off quirk)."""
    valid: list[dict] = []
    for record in records:
        try:
            valid.append(model.model_validate(record).model_dump(mode="json"))
        except ValidationError as exc:
            logger.warning("skipping invalid %s record: %s", label, exc)
    if not valid:
        raise ValueError(f"no {label} records passed validation")
    return valid


def _stage(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def run() -> int:
    # Legislators
    legislators_raw = _fetch_yaml(LEGISLATORS_URL)
    if not isinstance(legislators_raw, list) or not legislators_raw:
        raise ValueError("expected a non-empty list of legislator records")
    legislators = _validate_list(legislators_raw, LegislatorRaw, "legislator")
    _stage(STAGING_LEGISLATORS, legislators)

    # Committees (+ subcommittees nested)
    committees_raw = _fetch_yaml(COMMITTEES_URL)
    if not isinstance(committees_raw, list) or not committees_raw:
        raise ValueError("expected a non-empty list of committees")
    committees = _validate_list(committees_raw, CommitteeRaw, "committee")
    _stage(STAGING_COMMITTEES, committees)

    # Committee memberships: mapping {committee_code: [member entries]}
    membership_raw = _fetch_yaml(MEMBERSHIP_URL)
    if not isinstance(membership_raw, dict) or not membership_raw:
        raise ValueError("expected a non-empty committee-membership mapping")
    membership: dict[str, list[dict]] = {}
    for code, members in membership_raw.items():
        validated = []
        for m in members or []:
            try:
                validated.append(CommitteeMemberRaw.model_validate(m).model_dump(mode="json"))
            except ValidationError as exc:
                logger.warning("skipping invalid membership entry in %s: %s", code, exc)
        membership[code] = validated
    _stage(STAGING_MEMBERSHIP, membership)

    logger.info(
        "congress_legislators: staged %d legislators, %d committees, %d membership groups",
        len(legislators),
        len(committees),
        len(membership),
    )
    return len(legislators)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
