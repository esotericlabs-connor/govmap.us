"""Layer 1 pipeline: ZIP → congressional-district crosswalk (HUD USPS).

Source: the HUD USPS ZIP Code Crosswalk API (huduser.gov), **type 5 = ZIP →
Congressional District**. This is the authoritative ZIP→CD mapping — the Census
Bureau publishes *no* ZCTA↔CD relationship file (its `rel2020/zcta520/` set
pairs ZCTAs with county/place/tract/tabblock/cousub only, confirmed by listing
the directory). HUD keys on real USPS ZIP codes and refreshes quarterly.

Requires HUD_API_TOKEN (free). The token is sent as a Bearer header, never a URL
param, so it can't leak into logs/exceptions. Skipped (raises, non-fatal) when
unset, like the other keyed pipelines. A ZIP that straddles districts yields
multiple rows; `district` 0 = at-large / single-district state.

Run directly: `python -m app.pipelines.zip_crosswalk`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from app.config import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "zip_crosswalk"

# backend/app/pipelines/zip_crosswalk.py -> parents[2] == backend/
STAGING_DIR = Path(__file__).resolve().parents[2] / "data" / "staging"
STAGING_PATH = STAGING_DIR / "zip_districts_raw.json"

HUD_URL = "https://www.huduser.gov/hudapi/public/usps"
_TYPE_ZIP_CD = 5  # HUD crosswalk type: ZIP → Congressional District

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


def _fetch() -> list[dict]:
    if not settings.hud_api_token:
        raise RuntimeError(
            "HUD_API_TOKEN is not set — required for the ZIP→district crosswalk "
            "(free token at https://www.huduser.gov/portal/dataset/uspszip-api.html)"
        )
    resp = requests.get(
        HUD_URL,
        params={"type": _TYPE_ZIP_CD, "query": "All"},
        headers={"Authorization": f"Bearer {settings.hud_api_token}"},
        timeout=180,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data") or {}
    results = data.get("results") or []
    if not results:
        raise RuntimeError(
            f"HUD returned no ZIP→CD results (payload keys: {list(payload.keys())}; "
            f"data keys: {list(data.keys())})"
        )
    return results


def _parse(results: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, int]] = set()
    rows: list[dict] = []
    for r in results:
        zip5 = str(r.get("zip") or "").strip()
        # HUD returns the target-geography id as `geoid`; for a CD that's the
        # 4-char STATEFP(2)+CD(2), e.g. "0603" = CA-3.
        geoid = str(r.get("geoid") or r.get("cd") or "").strip()
        if len(zip5) != 5 or not zip5.isdigit() or len(geoid) < 4:
            continue
        state = FIPS_TO_USPS.get(geoid[:2])
        if state is None:
            continue
        try:
            district = int(geoid[2:4])
        except ValueError:
            continue
        key = (zip5, state, district)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"zip": zip5, "state": state, "district": district})

    if not rows:
        raise ValueError("no ZIP→district rows parsed from HUD response")
    return rows


def _stage(rows: list[dict]) -> None:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_PATH.write_text(json.dumps(rows))


def run() -> int:
    rows = _parse(_fetch())
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
