"""Layer 1 pipeline: pull unitedstates/congress-legislators, validate, stage.

Source: https://github.com/unitedstates/congress-legislators — no auth, no
rate limit. This is the pilot source proving the pull -> validate -> stage
contract end-to-end before the remaining 24 sources are built the same way;
see CODE-MANIFEST.md.

Run directly: `python -m app.pipelines.congress_legislators` (from backend/,
with DATABASE_URL etc. loaded — this script itself needs no DB access, only
network + filesystem).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from pydantic import ValidationError

from app.schemas.member import LegislatorRaw
from app.schemas.pipeline_status import PipelineSourceStatus, PipelineStatus

logger = logging.getLogger(__name__)

SOURCE_URL = (
    "https://raw.githubusercontent.com/unitedstates/congress-legislators"
    "/main/legislators-current.yaml"
)
SOURCE_NAME = "congress_legislators"

# backend/app/pipelines/congress_legislators.py -> parents[2] == backend/
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STAGING_PATH = DATA_DIR / "staging" / "legislators_raw.json"
STATUS_PATH = DATA_DIR / "pipeline_status.json"


def fetch_raw_yaml() -> list[dict]:
    response = requests.get(SOURCE_URL, timeout=30)
    response.raise_for_status()
    records = yaml.safe_load(response.text)
    if not isinstance(records, list) or not records:
        raise ValueError("expected a non-empty list of legislator records")
    return records


def validate_records(records: list[dict]) -> list[dict]:
    """Validate each raw record; skip and log individually invalid ones
    rather than failing the whole run on one bad record, but fail loudly
    (raise) if nothing at all comes out valid — that's a source-shape
    change, not a one-off data quirk."""
    valid: list[dict] = []
    for record in records:
        try:
            validated = LegislatorRaw.model_validate(record)
        except ValidationError as exc:
            bioguide = record.get("id", {}).get("bioguide", "unknown")
            logger.warning("skipping invalid legislator record %s: %s", bioguide, exc)
            continue
        valid.append(validated.model_dump(mode="json"))
    if not valid:
        raise ValueError("no legislator records passed validation")
    return valid


def write_status(record_count: int, status: str, detail: str | None = None) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = PipelineStatus()
    if STATUS_PATH.exists():
        current = PipelineStatus.model_validate_json(STATUS_PATH.read_text())
    current.sources[SOURCE_NAME] = PipelineSourceStatus(
        last_updated=datetime.now(timezone.utc),
        record_count=record_count,
        status=status,
        detail=detail,
    )
    STATUS_PATH.write_text(current.model_dump_json(indent=2))


def run() -> int:
    try:
        raw_records = fetch_raw_yaml()
        valid_records = validate_records(raw_records)
    except Exception as exc:  # fail loudly, never write stale data silently
        logger.exception("congress_legislators pipeline failed")
        write_status(record_count=0, status="error", detail=str(exc))
        raise

    STAGING_PATH.parent.mkdir(parents=True, exist_ok=True)
    STAGING_PATH.write_text(json.dumps(valid_records, indent=2))
    write_status(record_count=len(valid_records), status="ok")
    logger.info("congress_legislators: staged %d records", len(valid_records))
    return len(valid_records)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
