"""Tee the app's own logs to a persistent file the operator can grab.

Attaches a size-capped RotatingFileHandler to the ``app`` logger (the namespace
every module uses via ``logging.getLogger(__name__)``), so all our runtime
output — the pipeline self-diagnostics (HUD page keys, committee-meeting keys,
finance rate-limit aborts) plus every warning/error — lands in
``<log_dir>/app.log``. Records still propagate to stdout, so ``docker logs``
keeps working too; this just adds a durable file on the bind-mounted volume.

Framework noise (uvicorn, SQLAlchemy) is excluded by attaching to ``app`` rather
than the root logger. Fail-soft: if the log dir isn't writable, the app runs on
without file logging rather than crashing at startup.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from app.config import settings

_APP_LOG = "app.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUPS = 3                  # app.log + 3 rotations, bounded on disk
_configured = False


def app_log_path() -> str:
    return os.path.join(settings.log_dir, _APP_LOG)


def setup_file_logging() -> None:
    """Idempotently attach the app.log file handler. Safe to call on every
    startup; a second call is a no-op."""
    global _configured
    if _configured:
        return
    try:
        os.makedirs(settings.log_dir, exist_ok=True)
        handler = RotatingFileHandler(
            app_log_path(), maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        app_logger = logging.getLogger("app")
        app_logger.setLevel(logging.INFO)
        app_logger.addHandler(handler)
        _configured = True
        app_logger.info("file logging started -> %s", app_log_path())
    except OSError as exc:
        # Never let logging setup take the app down.
        logging.getLogger("app").warning("file logging disabled (%s): %s", settings.log_dir, exc)
