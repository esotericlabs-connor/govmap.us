import asyncio
import logging
import os
import re
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
import yaml
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import logging_setup, logsctl, worker
from app import scheduler as scheduler_module
from app.config import Settings
from app.sources import SOURCES

ROOT = Path(__file__).resolve().parents[2]
HEAD = "test_head"
# run_worker installs loop signal handlers, which only POSIX event loops support.
_posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal handling")


def _paas() -> dict:
    compose = yaml.safe_load((ROOT / "docker-compose.PaaS.yml").read_text(encoding="utf-8"))
    return compose["services"]


async def _until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


@pytest.fixture
def heartbeat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "heartbeat"
    monkeypatch.setattr(worker, "HEARTBEAT_PATH", path)
    monkeypatch.setattr(worker, "HEARTBEAT_SECONDS", 0.01)
    return path


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Mock:
    fake = Mock()
    fake.dispose = AsyncMock()
    monkeypatch.setattr(worker, "engine", fake)
    return fake


# --- schema gate ----------------------------------------------------------------


def test_expected_heads_come_from_this_images_migrations() -> None:
    assert worker.MIGRATIONS_DIR == ROOT / "backend" / "migrations"
    heads = worker.expected_heads()
    assert len(heads) == 1
    assert heads == set(ScriptDirectory(str(worker.MIGRATIONS_DIR)).get_heads())


def test_schema_wait_retries_until_the_backend_has_migrated(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    results: list[set[str] | Exception] = [OSError("private password"), {"0013"}, {HEAD}]
    calls = 0

    async def heads() -> set[str]:
        nonlocal calls
        result = results[calls]
        calls += 1
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(worker, "database_heads", heads)
    monkeypatch.setattr(worker, "SCHEMA_POLL_SECONDS", 0)
    caplog.set_level(logging.INFO, logger="app.worker")

    async def scenario() -> bool:
        return await worker.wait_for_schema({HEAD}, asyncio.Event())

    assert asyncio.run(scenario()) is True
    assert calls == 3
    assert "database unavailable (OSError)" in caplog.text
    assert "database schema is at 0013" in caplog.text
    assert "private" not in caplog.text


def test_schema_wait_gives_up_on_a_schema_it_was_not_built_for(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # A database migrated past this image (e.g. after a rollback) never matches.
    monkeypatch.setattr(worker, "database_heads", AsyncMock(return_value={"9999_newer"}))
    monkeypatch.setattr(worker, "SCHEMA_WAIT_SECONDS", 0)
    caplog.set_level(logging.INFO, logger="app.worker")

    async def scenario() -> bool:
        return await worker.wait_for_schema({HEAD}, asyncio.Event())

    assert asyncio.run(scenario()) is False
    assert any(
        r.levelno == logging.ERROR and "did not reach test_head" in r.getMessage()
        for r in caplog.records
    )


def test_schema_wait_stops_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    heads = AsyncMock(return_value={HEAD})
    monkeypatch.setattr(worker, "database_heads", heads)

    async def scenario() -> bool:
        stop = asyncio.Event()
        stop.set()
        return await worker.wait_for_schema({HEAD}, stop)

    assert asyncio.run(scenario()) is False
    heads.assert_not_called()


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
def test_database_heads_reads_alembic_version_on_postgres() -> None:
    version_table = Table("alembic_version", MetaData())
    head = next(iter(worker.expected_heads()))
    script = ScriptDirectory(str(worker.MIGRATIONS_DIR))

    async def scenario() -> None:
        db = create_async_engine(os.environ["TEST_DATABASE_URL"], poolclass=NullPool)
        try:
            # Never touch a version table this test didn't create.
            assert await worker.database_heads(db) == set()
            try:
                async with db.begin() as conn:
                    await conn.run_sync(
                        lambda sync: MigrationContext.configure(sync).stamp(script, head)
                    )
                assert await worker.database_heads(db) == {head}
            finally:
                async with db.begin() as conn:
                    await conn.run_sync(lambda sync: version_table.drop(sync, checkfirst=True))
        finally:
            await db.dispose()

    asyncio.run(scenario())


# --- worker lifecycle -------------------------------------------------------------


@_posix_only
def test_idle_worker_heartbeats_without_the_database_and_stops_on_sigterm(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    heartbeat: Path,
    engine: Mock,
) -> None:
    monkeypatch.setattr(worker.settings, "scheduler_enabled", False)
    heads = AsyncMock()
    start = Mock()
    monkeypatch.setattr(worker, "database_heads", heads)
    monkeypatch.setattr(scheduler_module, "start_scheduler", start)
    caplog.set_level(logging.INFO, logger="app.worker")

    async def scenario() -> int:
        run = asyncio.create_task(worker.run_worker())
        await _until(heartbeat.exists)
        os.kill(os.getpid(), signal.SIGTERM)
        return await asyncio.wait_for(run, 5)

    assert asyncio.run(scenario()) == 0
    heads.assert_not_called()
    start.assert_not_called()
    engine.dispose.assert_awaited_once()
    assert not heartbeat.exists()
    assert "SCHEDULER_ENABLED=false" in caplog.text


@_posix_only
def test_worker_runs_the_schedule_and_lets_a_cancelled_refresh_clean_up(
    monkeypatch: pytest.MonkeyPatch, heartbeat: Path, engine: Mock
) -> None:
    events: list[str] = []

    async def probe() -> None:
        events.append("started")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            # Stands in for recording the run's outcome and releasing its lock:
            # a second cancellation would interrupt it.
            await asyncio.sleep(0.05)
            events.append("cleaned up")
            raise

    monkeypatch.setattr(worker.settings, "scheduler_enabled", True)
    monkeypatch.setattr(worker, "expected_heads", lambda: {HEAD})
    monkeypatch.setattr(worker, "database_heads", AsyncMock(return_value={HEAD}))
    monkeypatch.setattr(scheduler_module, "scheduler", scheduler_module.new_scheduler())
    monkeypatch.setattr(scheduler_module, "JOBS", [("probe", probe, {"trigger": "date"})])

    async def scenario() -> int:
        run = asyncio.create_task(worker.run_worker())
        await _until(lambda: "started" in events and heartbeat.exists())
        os.kill(os.getpid(), signal.SIGTERM)
        return await asyncio.wait_for(run, 5)

    assert asyncio.run(scenario()) == 0
    assert events == ["started", "cleaned up"]
    assert not scheduler_module.scheduler.running
    assert not scheduler_module._running_jobs
    engine.dispose.assert_awaited_once()
    assert not heartbeat.exists()


@_posix_only
def test_worker_exits_nonzero_when_the_schema_never_arrives(
    monkeypatch: pytest.MonkeyPatch, heartbeat: Path, engine: Mock
) -> None:
    start = Mock()
    monkeypatch.setattr(worker.settings, "scheduler_enabled", True)
    monkeypatch.setattr(worker, "expected_heads", lambda: {HEAD})
    monkeypatch.setattr(worker, "database_heads", AsyncMock(return_value={"0013"}))
    monkeypatch.setattr(worker, "SCHEMA_WAIT_SECONDS", 0)
    monkeypatch.setattr(scheduler_module, "start_scheduler", start)

    assert asyncio.run(worker.run_worker()) == 1
    start.assert_not_called()
    engine.dispose.assert_awaited_once()
    assert not heartbeat.exists()


@_posix_only
def test_worker_exits_nonzero_if_the_scheduler_is_not_running(
    monkeypatch: pytest.MonkeyPatch, heartbeat: Path, engine: Mock
) -> None:
    monkeypatch.setattr(worker.settings, "scheduler_enabled", True)
    monkeypatch.setattr(worker, "expected_heads", lambda: {HEAD})
    monkeypatch.setattr(worker, "database_heads", AsyncMock(return_value={HEAD}))
    monkeypatch.setattr(scheduler_module, "scheduler", scheduler_module.new_scheduler())
    monkeypatch.setattr(scheduler_module, "start_scheduler", Mock())

    assert asyncio.run(worker.run_worker()) == 1
    engine.dispose.assert_awaited_once()
    assert not heartbeat.exists()


@_posix_only
@pytest.mark.usefixtures("engine")
def test_stale_heartbeat_is_removed_at_start(
    monkeypatch: pytest.MonkeyPatch, heartbeat: Path
) -> None:
    heartbeat.write_text("", encoding="utf-8")
    seen: list[bool] = []

    async def heads() -> set[str]:
        seen.append(heartbeat.exists())
        return {"0013"}

    monkeypatch.setattr(worker.settings, "scheduler_enabled", True)
    monkeypatch.setattr(worker, "expected_heads", lambda: {HEAD})
    monkeypatch.setattr(worker, "database_heads", heads)
    monkeypatch.setattr(worker, "SCHEMA_WAIT_SECONDS", 0)

    assert asyncio.run(worker.run_worker()) == 1
    assert seen == [False]


# --- logs -------------------------------------------------------------------------


def test_worker_logs_to_its_own_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_setup, "_configured", False)
    monkeypatch.setattr(logging_setup.settings, "log_dir", str(tmp_path))
    app_logger = logging.getLogger("app")
    before = list(app_logger.handlers)
    level = app_logger.level
    try:
        logging_setup.setup_file_logging(logging_setup.WORKER_LOG)
        logging.getLogger("app.worker").info("worker probe line")
    finally:
        for handler in [h for h in app_logger.handlers if h not in before]:
            app_logger.removeHandler(handler)
            handler.close()
        app_logger.setLevel(level)
    assert "worker probe line" in (tmp_path / "worker.log").read_text(encoding="utf-8")
    assert not (tmp_path / "app.log").exists()


def test_clear_logs_empties_api_and_worker_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(logsctl.settings, "log_dir", str(tmp_path))
    for name in ("app.log", "app.log.1", "worker.log", "worker.log.2", "bug_reports.log"):
        (tmp_path / name).write_text("line\n", encoding="utf-8")
    logsctl.clear_logs()
    assert (tmp_path / "app.log").read_text(encoding="utf-8") == ""
    assert (tmp_path / "worker.log").read_text(encoding="utf-8") == ""
    assert not (tmp_path / "app.log.1").exists()
    assert not (tmp_path / "worker.log.2").exists()
    assert (tmp_path / "bug_reports.log").read_text(encoding="utf-8") == "line\n"
    assert "worker.log" in capsys.readouterr().out


# --- deployment -------------------------------------------------------------------

_API_ONLY = {
    "CORS_ORIGINS",
    "API_DOCS_ENABLED",
    "TRUSTED_PROXY_CIDRS",
    "INTERNAL_USER",
    "INTERNAL_PASSWORD",
    "TURNSTILE_SECRET_KEY",
}
_BUDGETS = {
    "CONGRESS_REQUESTS_PER_HOUR": "congress_requests_per_hour",
    "FEC_REQUESTS_PER_HOUR": "fec_requests_per_hour",
    "GOVINFO_REQUESTS_PER_HOUR": "govinfo_requests_per_hour",
}
_DEFAULTED = re.compile(r"\$\{(?P<name>[A-Z_]+):-(?P<value>\d+)\}")


def test_only_the_worker_schedules_refreshes() -> None:
    services = _paas()
    assert services["backend"]["environment"]["SCHEDULER_ENABLED"] == "false"
    assert services["worker"]["environment"]["SCHEDULER_ENABLED"] == "${SCHEDULER_ENABLED:-true}"
    # The legacy single-VM compose keeps scheduling inside the API process.
    legacy = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    assert "worker" not in legacy
    assert legacy["backend"]["environment"]["SCHEDULER_ENABLED"] == "${SCHEDULER_ENABLED:-true}"


def test_worker_service_runs_the_backend_image_without_api_settings() -> None:
    services = _paas()
    backend, worker_service = services["backend"], services["worker"]
    assert worker_service["build"] == backend["build"]
    assert worker_service["build"]["args"]["SOURCE_COMMIT"] == "${SOURCE_COMMIT:-unknown}"
    assert worker_service["command"] == ["python", "-m", "app.worker"]
    assert worker_service["restart"] == "unless-stopped"
    assert worker_service["depends_on"] == {"postgres": {"condition": "service_healthy"}}
    assert "ports" not in worker_service
    assert "govmap-logs:/app/logs" in worker_service["volumes"]
    assert "worker-staging:/app/data/staging" in worker_service["volumes"]

    api_env, worker_env = backend["environment"], worker_service["environment"]
    assert not set(worker_env) & _API_ONLY
    assert set(worker_env) == set(api_env) - _API_ONLY
    for key, value in worker_env.items():
        if key not in _BUDGETS and key != "SCHEDULER_ENABLED":
            assert value == api_env[key], key


def test_only_the_worker_keeps_staging_across_redeploys() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.PaaS.yml").read_text(encoding="utf-8"))
    assert "worker-staging" in compose["volumes"]
    # The image's WORKDIR is /app, so the mount must cover every staging file.
    backend_dir = ROOT / "backend"
    for spec in SOURCES.values():
        for path in spec.staging_files:
            assert path.parent.relative_to(backend_dir) == Path("data", "staging"), path
    for name, service in compose["services"].items():
        if name != "worker":
            assert not any(
                str(volume).startswith("worker-staging:") for volume in service.get("volumes", [])
            ), name


@pytest.mark.parametrize(("variable", "field"), sorted(_BUDGETS.items()))
def test_api_and_worker_budget_shares_fit_the_single_process_limit(
    variable: str, field: str
) -> None:
    services = _paas()
    api = _DEFAULTED.fullmatch(services["backend"]["environment"][variable])
    shared = _DEFAULTED.fullmatch(services["worker"]["environment"][variable])
    assert api is not None and shared is not None
    assert api["name"] == f"API_{variable}"
    assert shared["name"] == f"WORKER_{variable}"
    limit = Settings.model_fields[field].default
    assert int(api["value"]) + int(shared["value"]) <= limit


def test_worker_healthcheck_reads_the_heartbeat() -> None:
    worker_service = _paas()["worker"]
    check = worker_service["healthcheck"]
    command = " ".join(check["test"])
    assert check["test"][:2] == ["CMD", "python"]
    assert f"'{worker.HEARTBEAT_PATH.as_posix()}'" in command
    assert f"> {worker.HEARTBEAT_MAX_AGE_SECONDS})" in command
    assert worker.HEARTBEAT_MAX_AGE_SECONDS >= 3 * worker.HEARTBEAT_SECONDS
    assert check["interval"] == "30s"
    assert check["timeout"] == "6s"
    assert check["retries"] == 3
    assert check["start_period"] == "120s"
    grace = worker_service["stop_grace_period"]
    assert grace.endswith("s") and int(grace[:-1]) > worker.SHUTDOWN_TIMEOUT_SECONDS
