import asyncio
import json
import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import main
from app.config import Settings
from app.models.pipeline_status import PipelineStatusRow
from app.routers import health

SHA = "a" * 40


def _session(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(health, "async_session_factory", factory)
    return session


def test_liveness_does_not_touch_database(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session(monkeypatch)
    monkeypatch.setattr(health.settings, "app_commit_sha", SHA)
    response = asyncio.run(health.health())
    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "ok", "commit_sha": SHA}
    assert response.headers["cache-control"] == "no-store"
    session.execute.assert_not_called()


def test_unknown_commit_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health.settings, "app_commit_sha", "unknown")
    assert json.loads(asyncio.run(health.health()).body)["commit_sha"] is None


def test_commit_reads_image_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_COMMIT_SHA", SHA)
    assert Settings(_env_file=None).app_commit_sha == SHA
    monkeypatch.delenv("APP_COMMIT_SHA")
    assert Settings(_env_file=None).app_commit_sha == "unknown"


@pytest.mark.parametrize("sha", ["", "main", "a" * 7, "a" * 41, "A" * 40, "private-value"])
def test_invalid_commit_setting_is_rejected(sha: str) -> None:
    with pytest.raises(ValidationError, match="app_commit_sha"):
        Settings(_env_file=None, app_commit_sha=sha)


def test_readiness_reads_schema_without_requiring_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(monkeypatch)
    monkeypatch.setattr(health.settings, "app_commit_sha", SHA)
    response = asyncio.run(health.ready())
    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "ok", "commit_sha": SHA}
    assert response.headers["cache-control"] == "no-store"
    statement = session.execute.call_args.args[0]
    assert statement.compare(select(PipelineStatusRow.source).limit(1))
    session.commit.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        asyncpg.InvalidPasswordError("private database URL"),
        OperationalError("private database URL", {}, Exception("private password")),
        SQLAlchemyError("private database URL"),
        TimeoutError("private database URL"),
        OSError("private database URL"),
    ],
)
def test_expected_readiness_failure_is_503_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    session = _session(monkeypatch)
    session.execute.side_effect = error
    caplog.set_level(logging.WARNING, logger="app.routers.health")
    response = asyncio.run(health.ready())
    assert response.status_code == 503
    assert json.loads(response.body)["status"] == "unavailable"
    assert response.headers["cache-control"] == "no-store"
    assert "database readiness check failed" in caplog.text
    assert "private" not in caplog.text
    assert b"private" not in response.body


def test_readiness_timeout_cancels_slow_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(monkeypatch)
    cancelled = False

    async def slow_execute(statement: object) -> None:
        nonlocal cancelled
        try:
            await asyncio.sleep(60)
        finally:
            cancelled = True

    session.execute.side_effect = slow_execute
    assert health.READINESS_TIMEOUT_SECONDS == 3
    monkeypatch.setattr(health, "READINESS_TIMEOUT_SECONDS", 0.01)
    response = asyncio.run(health.ready())
    assert response.status_code == 503
    assert cancelled


def test_cancellation_is_not_converted_to_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(monkeypatch)
    session.execute.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(health.ready())


def test_unexpected_error_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session(monkeypatch)
    session.execute.side_effect = RuntimeError("unexpected programming error")
    with pytest.raises(RuntimeError, match="programming error"):
        asyncio.run(health.ready())


def test_health_routes_are_registered() -> None:
    paths = [getattr(route, "path", None) for route in main.app.routes]
    assert paths.count("/health") == 1
    assert paths.count("/ready") == 1


@pytest.mark.parametrize("compose_name", ["docker-compose.yml", "docker-compose.PaaS.yml"])
def test_compose_health_checks_and_build_sha(compose_name: str) -> None:
    root = Path(__file__).resolve().parents[2]
    services = yaml.safe_load((root / compose_name).read_text(encoding="utf-8"))["services"]
    for service, port, path, timeout in [
        ("backend", 8000, "/ready", "6s"),
        ("frontend", 3000, "/health", "8s"),
    ]:
        config = services[service]
        assert config["build"]["args"]["SOURCE_COMMIT"] == "${SOURCE_COMMIT:-unknown}"
        assert "APP_COMMIT_SHA" not in config["environment"]
        check = config["healthcheck"]
        assert check["test"][0] == "CMD"
        assert f"http://127.0.0.1:{port}{path}" in " ".join(check["test"])
        assert check["timeout"] == timeout
        assert check["interval"] == "30s"
        assert check["retries"] == 3
        assert check["start_period"] == "120s"
    if compose_name.endswith("PaaS.yml"):
        assert "ports" not in services["backend"]
        assert "ports" not in services["frontend"]
    for service in ["backend", "frontend"]:
        dockerfile = (root / service / "Dockerfile").read_text(encoding="utf-8")
        assert "ARG SOURCE_COMMIT=unknown" in dockerfile
        assert "APP_COMMIT_SHA=$SOURCE_COMMIT" in dockerfile


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="isolated CI PostgreSQL only"
)
def test_readiness_against_isolated_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    url = os.environ["TEST_DATABASE_URL"]
    assert url.startswith("postgresql+asyncpg://")

    async def verify() -> None:
        engine = create_async_engine(url)
        monkeypatch.setattr(
            health, "async_session_factory", async_sessionmaker(engine)
        )
        try:
            # This database belongs exclusively to the CI job, not the app.
            async with engine.begin() as connection:
                await connection.run_sync(PipelineStatusRow.__table__.create)
            assert (await health.ready()).status_code == 200
            async with engine.begin() as connection:
                await connection.run_sync(PipelineStatusRow.__table__.drop)
            assert (await health.ready()).status_code == 503
        finally:
            await engine.dispose()

        from sqlalchemy.engine import make_url

        bad_engine = create_async_engine(
            make_url(url).set(password="wrong-ci-only-password")
        )
        monkeypatch.setattr(
            health, "async_session_factory", async_sessionmaker(bad_engine)
        )
        try:
            assert (await health.ready()).status_code == 503
        finally:
            await bad_engine.dispose()

    asyncio.run(verify())
