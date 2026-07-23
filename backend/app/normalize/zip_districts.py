"""Layer 2 normalizer: staging JSON -> Postgres `zip_districts` table.

The crosswalk is a full-replace dataset (a redistricting can move a ZIP between
districts, and old rows must not linger), so this truncates and reloads inside a
single transaction. Inserts are chunked to stay under asyncpg's 32767 bind-param
limit (3 columns per row).

Run directly: `python -m app.normalize.zip_districts` (after the zip_crosswalk
pipeline has staged data and DATABASE_URL is set).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy import delete, insert

from app.db import async_session_factory
from app.models.zip_district import ZipDistrict

logger = logging.getLogger(__name__)

# backend/app/normalize/zip_districts.py -> parents[2] == backend/
STAGING_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "staging" / "zip_districts_raw.json"
)

# 3 columns/row; keep well under the 32767 bind-param cap.
CHUNK_ROWS = 8000


async def load_zip_districts() -> int:
    if not STAGING_PATH.exists():
        raise FileNotFoundError(
            f"no staging data at {STAGING_PATH} — run the zip_crosswalk pipeline first"
        )

    rows = json.loads(STAGING_PATH.read_text())
    if not rows:
        raise ValueError("staged zip_districts is empty")

    async with async_session_factory() as session:
        await session.execute(delete(ZipDistrict))
        for start in range(0, len(rows), CHUNK_ROWS):
            chunk = rows[start : start + CHUNK_ROWS]
            await session.execute(insert(ZipDistrict), chunk)
        await session.commit()

    logger.info("normalized and loaded %d ZIP→district rows", len(rows))
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(load_zip_districts())
