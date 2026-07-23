"""Layer 1 pipeline: ZIP → congressional-district crosswalk.

Source: the U.S. Census Bureau 2020 ZCTA↔Congressional-District **relationship
file** (public domain, no auth, no rate limit) — the same self-contained,
fetch-at-refresh pattern as the other pipelines. We key on ZCTA5 (ZIP Code
Tabulation Areas), which is the Census stand-in for USPS ZIP codes: for a
"find your representatives" lookup ZCTA ≈ ZIP, and it avoids the auth-gated HUD
crosswalk. `district` 0 means an at-large / single-district state (or a
non-voting delegate seat coded 00).

The file is pipe-delimited with a header row; we resolve the ZCTA and CD
columns *by name prefix* so the same code works whether the current relationship
file is published as `cd119`, `cd118`, … We try the newest Congress first and
fall back, so a redistricting-year publish gap never breaks the pull.

Run directly: `python -m app.pipelines.zip_crosswalk`.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

SOURCE_NAME = "zip_crosswalk"

# backend/app/pipelines/zip_crosswalk.py -> parents[2] == backend/
STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING_PATH = STAGING_DIR / "zip_districts_raw.json"

_REL_BASE = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520"
# Newest Congress first; fall back if that file isn't published yet.
CANDIDATE_URLS = [
    f"{_REL_BASE}/tab20_zcta520_cd119_natl.txt",
    f"{_REL_BASE}/tab20_zcta520_cd118_natl.txt",
]

# 2-digit state/territory FIPS → USPS abbreviation. Anything not here (e.g. a
# stray "00") is dropped as out-of-scope.
FIPS_TO_USPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP",
    "72": "PR", "78": "VI",
}


def _fetch_relationship_file() -> str:
    last_exc: Exception | None = None
    for url in CANDIDATE_URLS:
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            logger.info("zip_crosswalk: using %s", url)
            return resp.text
        except requests.RequestException as exc:  # noqa: PERF203
            last_exc = exc
            logger.warning("zip_crosswalk: %s unavailable (%s)", url, exc)
    raise RuntimeError(
        f"no Census ZCTA→CD relationship file reachable ({last_exc})"
    )


def _column(fieldnames: list[str], prefix: str) -> str:
    for name in fieldnames:
        if name.upper().startswith(prefix):
            return name
    raise ValueError(f"no column starting with {prefix!r} in {fieldnames}")


def _parse(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    if not reader.fieldnames:
        raise ValueError("relationship file has no header row")

    zcta_col = _column(reader.fieldnames, "GEOID_ZCTA5")
    cd_col = _column(reader.fieldnames, "GEOID_CD")
    # Optional: land area of the ZCTA∩CD part — used to drop water-only slivers
    # so a ZIP doesn't pick up a district it barely (or doesn't) touch.
    area_col = next(
        (c for c in reader.fieldnames if c.upper().startswith("AREALAND_PART")),
        None,
    )

    seen: set[tuple[str, str, int]] = set()
    rows: list[dict] = []
    for record in reader:
        zcta = (record.get(zcta_col) or "").strip()
        cd = (record.get(cd_col) or "").strip()
        if len(zcta) != 5 or not zcta.isdigit() or len(cd) < 4:
            continue
        if area_col is not None:
            try:
                if float(record.get(area_col) or 0) <= 0:
                    continue
            except ValueError:
                pass  # unparseable area — keep the row rather than lose a rep

        state = FIPS_TO_USPS.get(cd[:2])
        if state is None:
            continue
        try:
            district = int(cd[2:])
        except ValueError:
            continue

        key = (zcta, state, district)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"zip": zcta, "state": state, "district": district})

    if not rows:
        raise ValueError("no ZIP→district rows parsed from relationship file")
    return rows


def _stage(rows: list[dict]) -> None:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_PATH.write_text(json.dumps(rows))


def run() -> int:
    rows = _parse(_fetch_relationship_file())
    _stage(rows)
    logger.info(
        "zip_crosswalk: staged %d ZIP→district rows (%d distinct ZIPs)",
        len(rows),
        len({r["zip"] for r in rows}),
    )
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
