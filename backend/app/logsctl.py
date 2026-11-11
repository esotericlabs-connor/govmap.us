"""Operator maintenance for the on-server log files.

Two independent clear commands, run inside the backend container:

    docker compose exec backend python -m app.logsctl clear-logs
    docker compose exec backend python -m app.logsctl clear-bugs

`clear-logs` empties app.log and worker.log (and removes their rotations);
`clear-bugs` empties bug_reports.log. The worker shares the log volume, so
either container can run it. Truncating to zero is safe while a process holds
the file open — the logger writes in append mode (O_APPEND), so its next write
lands at the new end of the empty file (no sparse gap).
"""

from __future__ import annotations

import glob
import os
import sys

from app.config import settings
from app.logging_setup import APP_LOG, WORKER_LOG

_BUG_LOG = "bug_reports.log"


def _truncate(path: str) -> bool:
    if not os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8"):
        pass  # opening in "w" truncates to empty
    return True


def clear_logs() -> None:
    for name in (APP_LOG, WORKER_LOG):
        base = os.path.join(settings.log_dir, name)
        _truncate(base)
        for rotated in glob.glob(base + ".*"):  # app.log.1, app.log.2, …
            try:
                os.remove(rotated)
            except OSError:
                pass
    print(f"cleared {APP_LOG} and {WORKER_LOG} (+ rotations) in {settings.log_dir}")


def clear_bugs() -> None:
    _truncate(os.path.join(settings.log_dir, _BUG_LOG))
    print(f"cleared {_BUG_LOG} in {settings.log_dir}")


_COMMANDS = {"clear-logs": clear_logs, "clear-bugs": clear_bugs}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in _COMMANDS:
        print(f"usage: python -m app.logsctl {{{' | '.join(_COMMANDS)}}}", file=sys.stderr)
        return 2
    _COMMANDS[argv[0]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
