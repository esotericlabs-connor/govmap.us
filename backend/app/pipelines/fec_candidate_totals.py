"""Layer 1: bounded FEC candidate-finance and candidate/committee bulk files."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import zipfile
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from pydantic import ValidationError

from app.config import settings
from app.pipelines.batch import BatchResult
from app.pipelines.staging import write_json_atomic
from app.schemas.campaign_money import (
    FecBulkFileRaw,
    FecCampaignMoneySnapshotRaw,
    FecCandidateFinanceRaw,
    FecCommitteeLinkRaw,
)
from app.services.bounded_http import read_body
from app.services.upstream import request_slot

logger = logging.getLogger(__name__)

SOURCE_NAME = "fec_candidate_totals"
BULK_ROOT = "https://www.fec.gov/files/bulk-downloads"
_ARCHIVE_REDIRECT_ROOT = (
    "https://cg-519a459a-0ea3-42c2-b7bc-fa1143481f74."
    "s3-us-gov-west-1.amazonaws.com/bulk-downloads"
)
STAGING_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "staging" / "fec_candidate_totals_raw.json"
)

_MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
_MAX_TEXT_BYTES = 32 * 1024 * 1024
_MAX_CANDIDATES = 20_000
_MAX_LINKAGES = 100_000
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_AMOUNT_PATTERN = re.compile(r"^-?(?:\d+(?:\.\d{1,2})?|\.\d{1,2})$")
_AMOUNT_FIELDS = {
    5: "receipts",
    6: "transfers_from_authorized",
    7: "disbursements",
    8: "transfers_to_authorized",
    9: "cash_beginning",
    10: "cash_on_hand",
    11: "candidate_contributions",
    12: "candidate_loans",
    13: "other_loans",
    14: "candidate_loan_repayments",
    15: "other_loan_repayments",
    16: "debts",
    17: "individual_contributions",
    25: "other_committee_contributions",
    26: "party_contributions",
    28: "individual_refunds",
    29: "committee_refunds",
}


class CampaignMoneySnapshotIncompleteError(RuntimeError):
    """The FEC files cannot be safely loaded as a complete downloaded snapshot."""


def _file_url(cycle: int, filename: str) -> str:
    return f"{BULK_ROOT}/{cycle}/{filename}"


def source_urls(cycle: int) -> tuple[str, str]:
    suffix = f"{cycle % 100:02d}"
    return (
        _file_url(cycle, f"weball{suffix}.zip"),
        _file_url(cycle, f"ccl{suffix}.zip"),
    )


def _download(cycle: int, filename: str) -> tuple[bytes, FecBulkFileRaw]:
    url = _file_url(cycle, filename)
    expected_redirect = f"{_ARCHIVE_REDIRECT_ROOT}/{cycle}/{filename}"
    for hop in range(2):
        with request_slot("fec"):
            response = requests.get(
                url,
                timeout=45,
                stream=True,
                allow_redirects=False,
            )
            try:
                if response.status_code in _REDIRECT_STATUSES:
                    if hop or response.headers.get("Location") != expected_redirect:
                        raise CampaignMoneySnapshotIncompleteError(
                            f"FEC {filename} returned an unexpected archive redirect"
                        )
                    url = expected_redirect
                    continue
                if response.status_code != 200:
                    raise RuntimeError(f"FEC {filename} returned HTTP {response.status_code}")
                modified = response.headers.get("Last-Modified")
                last_modified = None
                if modified:
                    try:
                        last_modified = parsedate_to_datetime(modified)
                    except (TypeError, ValueError, IndexError, OverflowError) as exc:
                        raise CampaignMoneySnapshotIncompleteError(
                            f"FEC {filename} has an invalid Last-Modified header"
                        ) from exc
                    if last_modified.tzinfo is None:
                        raise CampaignMoneySnapshotIncompleteError(
                            f"FEC {filename} has a timezone-free Last-Modified header"
                        )
                body = read_body(
                    response,
                    max_bytes=_MAX_ARCHIVE_BYTES,
                    deadline_s=90,
                    label=f"FEC {filename}",
                )
            finally:
                response.close()
        return body, FecBulkFileRaw(
            name=filename,
            sha256=hashlib.sha256(body).hexdigest(),
            last_modified=last_modified,
        )
    raise CampaignMoneySnapshotIncompleteError(f"FEC {filename} exceeded its archive redirect limit")


def _archive_text(body: bytes, expected_name: str) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries = archive.infolist()
            if len(entries) != 1 or entries[0].filename != expected_name:
                raise CampaignMoneySnapshotIncompleteError(
                    f"FEC archive does not contain only {expected_name}"
                )
            entry = entries[0]
            if entry.file_size > _MAX_TEXT_BYTES:
                raise CampaignMoneySnapshotIncompleteError(
                    f"FEC {expected_name} exceeds the uncompressed size limit"
                )
            with archive.open(entry) as handle:
                content = handle.read(_MAX_TEXT_BYTES + 1)
            if len(content) != entry.file_size or len(content) > _MAX_TEXT_BYTES:
                raise CampaignMoneySnapshotIncompleteError(
                    f"FEC {expected_name} has an unexpected uncompressed size"
                )
            return content.decode("utf-8-sig")
    except (zipfile.BadZipFile, UnicodeDecodeError, OSError, EOFError) as exc:
        raise CampaignMoneySnapshotIncompleteError(
            f"FEC {expected_name} is not a valid UTF-8 archive"
        ) from exc


def _amount(value: str) -> str | None:
    if not value:
        return None
    if not _AMOUNT_PATTERN.fullmatch(value):
        raise ValueError("invalid FEC monetary amount")
    return value


def _coverage_end(value: str) -> date | None:
    return datetime.strptime(value, "%m/%d/%Y").date() if value else None


def _candidate_rows(text: str) -> list[FecCandidateFinanceRaw]:
    candidates: list[FecCandidateFinanceRaw] = []
    seen: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        cells = line.split("|")
        if len(cells) != 30:
            raise CampaignMoneySnapshotIncompleteError(
                f"FEC candidate summary row {line_number} does not have 30 fields"
            )
        try:
            candidate_id = cells[0]
            data: dict[str, object] = {
                "candidate_id": candidate_id,
                "name": cells[1] or None,
                "office": candidate_id[:1],
                "incumbent_challenge": cells[2] or None,
                "party": cells[4] or None,
                "state": cells[18] or None,
                "district": cells[19] or None,
                "coverage_end": _coverage_end(cells[27]),
            }
            data.update({name: _amount(cells[index]) for index, name in _AMOUNT_FIELDS.items()})
            candidate = FecCandidateFinanceRaw.model_validate(data)
        except ValueError as exc:
            raise CampaignMoneySnapshotIncompleteError(
                f"FEC candidate summary row {line_number} is invalid"
            ) from exc
        if candidate.candidate_id in seen:
            raise CampaignMoneySnapshotIncompleteError("FEC candidate summary repeats an ID")
        seen.add(candidate.candidate_id)
        candidates.append(candidate)
        if len(candidates) > _MAX_CANDIDATES:
            raise CampaignMoneySnapshotIncompleteError("FEC candidate summary exceeds its row cap")
    if not candidates:
        raise CampaignMoneySnapshotIncompleteError("FEC candidate summary is empty")
    return candidates


def _linkage_rows(text: str, cycle: int) -> list[FecCommitteeLinkRaw]:
    links: list[FecCommitteeLinkRaw] = []
    seen: set[int] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        cells = line.split("|")
        if len(cells) != 7:
            raise CampaignMoneySnapshotIncompleteError(
                f"FEC committee linkage row {line_number} does not have 7 fields"
            )
        try:
            link = FecCommitteeLinkRaw.model_validate(
                {
                    "subject_id": cells[0],
                    "candidate_election_year": cells[1],
                    "fec_election_year": cells[2],
                    "committee_id": cells[3] or None,
                    "committee_type": cells[4] or None,
                    "designation": cells[5] or None,
                    "linkage_id": cells[6],
                }
            )
        except ValidationError as exc:
            raise CampaignMoneySnapshotIncompleteError(
                f"FEC committee linkage row {line_number} is invalid"
            ) from exc
        if link.fec_election_year != cycle:
            raise CampaignMoneySnapshotIncompleteError("FEC linkage is for a different cycle")
        if link.linkage_id in seen:
            raise CampaignMoneySnapshotIncompleteError("FEC committee linkage repeats an ID")
        seen.add(link.linkage_id)
        links.append(link)
        if len(links) > _MAX_LINKAGES:
            raise CampaignMoneySnapshotIncompleteError("FEC committee linkage exceeds its row cap")
    if not links:
        raise CampaignMoneySnapshotIncompleteError("FEC committee linkage is empty")
    return links


def snapshot_revision(
    candidates: list[FecCandidateFinanceRaw], linkages: list[FecCommitteeLinkRaw]
) -> str:
    data = {
        "candidates": [
            row.model_dump(mode="json") for row in sorted(candidates, key=lambda row: row.candidate_id)
        ],
        "linkages": [
            row.model_dump(mode="json") for row in sorted(linkages, key=lambda row: row.linkage_id)
        ],
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def run() -> BatchResult:
    cycle = settings.fec_cycle
    if not 2000 <= cycle <= 2098 or cycle % 2:
        raise ValueError("FEC bulk finance cycle must be an even year from 2000 through 2098")
    suffix = f"{cycle % 100:02d}"
    summary_body, summary_file = _download(cycle, f"weball{suffix}.zip")
    linkage_body, linkage_file = _download(cycle, f"ccl{suffix}.zip")
    candidates = _candidate_rows(_archive_text(summary_body, f"weball{suffix}.txt"))
    linkages = _linkage_rows(_archive_text(linkage_body, "ccl.txt"), cycle)
    snapshot = FecCampaignMoneySnapshotRaw(
        source=SOURCE_NAME,
        finance_cycle=cycle,
        complete=True,
        candidate_count=len(candidates),
        linkage_count=len(linkages),
        summary_file=summary_file,
        linkage_file=linkage_file,
        snapshot_revision=snapshot_revision(candidates, linkages),
        fetched_at=datetime.now(UTC),
        candidates=candidates,
        linkages=linkages,
    )
    write_json_atomic(STAGING_PATH, snapshot.model_dump(mode="json"))
    logger.info(
        "%s: staged %d candidate summaries and %d linkages for cycle %d",
        SOURCE_NAME,
        len(candidates),
        len(linkages),
        cycle,
    )
    return BatchResult(total=len(candidates), succeeded=len(candidates), failed=0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
