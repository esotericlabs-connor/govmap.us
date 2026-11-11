"""Safety checks for normalizers that delete and reload a whole table.

A source outage, a shape change or a broken join can turn a "full refresh" into
an empty or truncated snapshot. Replacing good stored data with that snapshot
would silently blank pages, so the normalizer refuses and keeps the last good
load; the refresh records the failure instead.
"""

from __future__ import annotations


def check_replacement(
    table: str, new_rows: int, current_rows: int, *, min_ratio: float = 0.0
) -> None:
    """Raise ValueError unless replacing `current_rows` with `new_rows` is safe.

    An empty snapshot is always refused. `min_ratio` additionally refuses a
    snapshot smaller than that fraction of the current table, for datasets whose
    size cannot legitimately collapse between refreshes.
    """
    if new_rows <= 0:
        raise ValueError(
            f"{table}: refusing to replace {current_rows} stored rows with an empty snapshot"
        )
    if current_rows and new_rows < current_rows * min_ratio:
        raise ValueError(
            f"{table}: refusing to replace {current_rows} stored rows with only {new_rows} "
            f"(below {min_ratio:.0%} of the current table)"
        )
