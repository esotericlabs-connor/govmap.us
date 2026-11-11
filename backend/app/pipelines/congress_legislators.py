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

import logging
from dataclasses import dataclass
from pathlib import Path

import requests
from pydantic import BaseModel, ValidationError

from app.pipelines.staging import write_json_atomic
from app.schemas.committee import CommitteeMemberRaw, CommitteeRaw
from app.schemas.member import LegislatorRaw
from app.services.bounded_http import read_body
from app.services.safe_parse import load_yaml

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

# The largest file (legislators-current.yaml) is about 1 MiB.
_MAX_YAML_BYTES = 16 * 1024 * 1024
_BODY_DEADLINE_SECONDS = 120


def _fetch_yaml(url: str):
    response = requests.get(url, timeout=30, stream=True)
    try:
        response.raise_for_status()
        body = read_body(
            response,
            max_bytes=_MAX_YAML_BYTES,
            deadline_s=_BODY_DEADLINE_SECONDS,
            label=url.rsplit("/", 1)[-1],
        )
    finally:
        response.close()
    return load_yaml(body)


def _record_ident(record) -> str:
    """Best-effort identifier for a skipped record so a dropped member is never a
    silent mystery — bioguide + name for legislators, else any name/code."""
    if not isinstance(record, dict):
        return "<non-dict>"
    bioguide = (record.get("id") or {}).get("bioguide")
    if bioguide:
        name = (record.get("name") or {}).get("official_full") or ""
        return f"{bioguide} {name}".strip()
    name = record.get("name")
    if isinstance(name, str):
        return name[:60]
    return str(record.get("thomas_id") or record.get("committee_id") or "<unknown>")


def _validate_list(
    records: list, model: type[BaseModel], label: str
) -> tuple[list[dict], int]:
    """Validate each record; skip and log individually bad ones (naming the
    record so a dropped member is diagnosable), but raise if nothing survives (a
    source-shape change, not a one-off quirk). Returns (valid, skipped count)."""
    valid: list[dict] = []
    skipped = 0
    for record in records:
        try:
            valid.append(model.model_validate(record).model_dump(mode="json"))
        except ValidationError as exc:
            skipped += 1
            logger.warning("skipping invalid %s record [%s]: %s", label, _record_ident(record), exc)
    if skipped:
        logger.warning("%s: skipped %d of %d records as invalid", label, skipped, len(records))
    if not valid:
        raise ValueError(f"no {label} records passed validation")
    return valid, skipped


def _stage(path: Path, data) -> None:
    write_json_atomic(path, data, indent=2)


@dataclass(frozen=True)
class LegislatorsPull:
    legislators: int
    # Legislator records that failed validation. The roster load won't mark
    # anyone as departed unless this is 0: a skipped sitting member would
    # otherwise look like a departure.
    skipped_legislators: int


def run() -> LegislatorsPull:
    # Legislators
    legislators_raw = _fetch_yaml(LEGISLATORS_URL)
    if not isinstance(legislators_raw, list) or not legislators_raw:
        raise ValueError("expected a non-empty list of legislator records")
    legislators, skipped_legislators = _validate_list(legislators_raw, LegislatorRaw, "legislator")
    _stage(STAGING_LEGISLATORS, legislators)

    # Committees (+ subcommittees nested)
    committees_raw = _fetch_yaml(COMMITTEES_URL)
    if not isinstance(committees_raw, list) or not committees_raw:
        raise ValueError("expected a non-empty list of committees")
    committees, _ = _validate_list(committees_raw, CommitteeRaw, "committee")
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
        "congress_legislators: staged %d legislators (%d skipped), %d committees, "
        "%d membership groups",
        len(legislators),
        skipped_legislators,
        len(committees),
        len(membership),
    )
    return LegislatorsPull(legislators=len(legislators), skipped_legislators=skipped_legislators)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
