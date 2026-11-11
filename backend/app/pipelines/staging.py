"""Atomic staging-file writes shared by every pipeline.

Each pipeline stages one JSON snapshot that a normalizer later reads. A plain
``write_text`` truncates the previous good file first, so a crash, a full disk
or a concurrent reader mid-write could see an empty or half-written snapshot.
``write_json_atomic`` writes a sibling temporary file, flushes it to disk and
renames it over the target, so readers see either the old snapshot or the
complete new one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


def write_json_atomic(path: Path, data: Any, *, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        tmp = Path(handle.name)
        try:
            json.dump(data, handle, indent=indent)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
