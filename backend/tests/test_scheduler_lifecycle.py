import asyncio
import logging
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app import main
from app.config import Settings


def test_scheduler_is_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    assert Settings(_env_file=None).scheduler_enabled is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("false", False), ("1", True), ("0", False)],
)
def test_scheduler_setting_reads_environment(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv("SCHEDULER_ENABLED", value)
    assert Settings(_env_file=None).scheduler_enabled is expected


@pytest.mark.parametrize("value", ["", "invalid"])
def test_invalid_scheduler_setting_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SCHEDULER_ENABLED", value)
    with pytest.raises(ValidationError, match="scheduler_enabled"):
        Settings(_env_file=None)


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("application_fails", [False, True])
def test_lifespan_respects_scheduler_setting(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    enabled: bool,
    application_fails: bool,
) -> None:
    setup_logging = Mock()
    start = Mock()
    stop = Mock()
    monkeypatch.setattr(main, "setup_file_logging", setup_logging)
    monkeypatch.setattr(main, "start_scheduler", start)
    monkeypatch.setattr(main, "stop_scheduler", stop)
    monkeypatch.setattr(main.settings, "scheduler_enabled", enabled)
    caplog.set_level(logging.INFO, logger="app.main")

    async def serve() -> None:
        async with main.lifespan(main.app):
            setup_logging.assert_called_once_with()
            if enabled:
                start.assert_called_once_with()
            else:
                start.assert_not_called()
            stop.assert_not_called()
            if application_fails:
                raise RuntimeError("application failed")

    if application_fails:
        with pytest.raises(RuntimeError, match="application failed"):
            asyncio.run(serve())
    else:
        asyncio.run(serve())

    if enabled:
        start.assert_called_once_with()
        stop.assert_called_once_with()
    else:
        start.assert_not_called()
        stop.assert_not_called()
        assert "SCHEDULER_ENABLED=false" in caplog.text
