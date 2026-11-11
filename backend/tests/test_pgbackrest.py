import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="requires Linux Bash")

_REPO = Path(__file__).resolve().parents[2]
_SCHEDULER = _REPO / "backup" / "pgbackrest-run.sh"

_PGBACKREST = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_PGBACKREST_LOG"
if [[ " $* " == *" check "* && "${FAKE_PGBACKREST_CHECK_FAIL:-0}" == "1" ]]; then
  exit 1
fi
if [[ " $* " == *" backup "* && "${FAKE_PGBACKREST_BACKUP_FAIL:-0}" == "1" ]]; then
  exit 1
fi
if [[ " $* " == *" info "* ]]; then
  printf '[{}]\\n'
fi
"""

_JQ = """#!/usr/bin/env bash
cat >/dev/null
printf '%s\\n' "$FAKE_PGBACKREST_LAST_FULL"
"""

_SLEEP = """#!/usr/bin/env python3
import os
import signal
import sys

with open(os.environ["FAKE_SLEEP_LOG"], "a", encoding="utf-8") as log:
    log.write(sys.argv[1] + "\\n")
os.kill(os.getppid(), signal.SIGTERM)
"""

_CURL = """#!/usr/bin/env python3
import os
import sys

with open(os.environ["FAKE_CURL_LOG"], "a", encoding="utf-8") as log:
    log.write(sys.stdin.read())
sys.exit(int(os.environ.get("FAKE_CURL_EXIT", "0")))
"""


def _install(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def scheduler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install(bin_dir / "pgbackrest", _PGBACKREST)
    _install(bin_dir / "jq", _JQ)
    _install(bin_dir / "curl", _CURL)
    _install(bin_dir / "sleep", _SLEEP)

    pgbackrest_log = tmp_path / "pgbackrest.log"
    sleep_log = tmp_path / "sleep.log"
    curl_log = tmp_path / "curl.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_PGBACKREST_LOG", str(pgbackrest_log))
    monkeypatch.setenv("FAKE_SLEEP_LOG", str(sleep_log))
    monkeypatch.setenv("FAKE_CURL_LOG", str(curl_log))
    monkeypatch.setenv("FAKE_PGBACKREST_LAST_FULL", str(int(time.time())))
    for name in (
        "PGBACKREST_ENABLED",
        "PGBACKREST_TIME_UTC",
        "PGBACKREST_ARCHIVE_HEARTBEAT_URL",
        "PGBACKREST_BACKUP_HEARTBEAT_URL",
        "FAKE_PGBACKREST_BACKUP_FAIL",
        "FAKE_PGBACKREST_CHECK_FAIL",
        "FAKE_CURL_EXIT",
    ):
        monkeypatch.delenv(name, raising=False)
    return pgbackrest_log, sleep_log, curl_log


def _run_scheduler() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_SCHEDULER)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_pgbackrest_scheduler_idles_when_disabled(
    scheduler: tuple[Path, Path, Path],
) -> None:
    pgbackrest_log, sleep_log, _ = scheduler

    result = _run_scheduler()

    assert result.returncode == 143
    assert "disabled" in result.stdout
    assert _lines(pgbackrest_log) == []
    assert _lines(sleep_log) == ["86400"]


def test_pgbackrest_scheduler_checks_archive_and_waits_for_daily_slot(
    scheduler: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    pgbackrest_log, sleep_log, curl_log = scheduler
    monkeypatch.setenv("PGBACKREST_ENABLED", "true")
    monkeypatch.setenv("PGBACKREST_TIME_UTC", "03:30")
    monkeypatch.setenv("PGBACKREST_ARCHIVE_HEARTBEAT_URL", "https://hc.example.test/archive")
    monkeypatch.setenv("PGBACKREST_BACKUP_HEARTBEAT_URL", "https://hc.example.test/full")

    result = _run_scheduler()

    assert result.returncode == 143
    assert "--stanza=govmap check" in _lines(pgbackrest_log)[0]
    assert any("info --output=json" in line for line in _lines(pgbackrest_log))
    assert "daily at 03:30 UTC" in result.stdout
    assert int(_lines(sleep_log)[0]) <= 900
    assert "https://hc.example.test/archive" in "\n".join(_lines(curl_log))


def test_pgbackrest_scheduler_catches_up_a_stale_full_backup(
    scheduler: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    pgbackrest_log, _, curl_log = scheduler
    monkeypatch.setenv("PGBACKREST_ENABLED", "true")
    monkeypatch.setenv("FAKE_PGBACKREST_LAST_FULL", str(int(time.time()) - 25 * 3600))
    monkeypatch.setenv("PGBACKREST_BACKUP_HEARTBEAT_URL", "https://hc.example.test/full")

    result = _run_scheduler()

    assert result.returncode == 143
    assert "catch-up backup" in result.stdout
    assert any("--type=full backup" in line for line in _lines(pgbackrest_log))
    assert "https://hc.example.test/full" in "\n".join(_lines(curl_log))


def test_pgbackrest_scheduler_retries_a_failed_catch_up_backup(
    scheduler: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    pgbackrest_log, sleep_log, curl_log = scheduler
    monkeypatch.setenv("PGBACKREST_ENABLED", "true")
    monkeypatch.setenv("FAKE_PGBACKREST_LAST_FULL", "0")
    monkeypatch.setenv("FAKE_PGBACKREST_BACKUP_FAIL", "1")
    monkeypatch.setenv("PGBACKREST_BACKUP_HEARTBEAT_URL", "https://hc.example.test/full")

    result = _run_scheduler()

    assert result.returncode == 143
    assert "full backup failed" in result.stdout
    assert "Retry" in result.stdout
    assert int(_lines(sleep_log)[0]) <= 900
    assert _lines(curl_log) == []
    assert any("--type=full backup" in line for line in _lines(pgbackrest_log))


@pytest.mark.parametrize("value", ["2:30", "24:00", "03:60", "0330", "03:30 "])
def test_pgbackrest_scheduler_rejects_invalid_time(
    scheduler: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    pgbackrest_log, sleep_log, _ = scheduler
    monkeypatch.setenv("PGBACKREST_ENABLED", "true")
    monkeypatch.setenv("PGBACKREST_TIME_UTC", value)

    result = _run_scheduler()

    assert result.returncode == 1
    assert "PGBACKREST_TIME_UTC" in result.stdout
    assert _lines(pgbackrest_log) == []
    assert _lines(sleep_log) == []


@pytest.mark.parametrize(
    "value",
    ["http://hc.example.test/path", 'https://hc.example.test/"bad', "https://hc.example.test/\\bad"],
)
def test_pgbackrest_scheduler_rejects_malformed_heartbeat_url(
    scheduler: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    pgbackrest_log, sleep_log, _ = scheduler
    monkeypatch.setenv("PGBACKREST_ENABLED", "true")
    monkeypatch.setenv("PGBACKREST_ARCHIVE_HEARTBEAT_URL", value)

    result = _run_scheduler()

    assert result.returncode == 1
    assert "heartbeat URLs" in result.stdout
    assert _lines(pgbackrest_log) == []
    assert _lines(sleep_log) == []


def test_pgbackrest_scheduler_does_not_ping_after_failed_archive_check(
    scheduler: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    pgbackrest_log, _, curl_log = scheduler
    monkeypatch.setenv("PGBACKREST_ENABLED", "true")
    monkeypatch.setenv("FAKE_PGBACKREST_CHECK_FAIL", "1")

    result = _run_scheduler()

    assert result.returncode == 143
    assert "archive check failed" in result.stdout
    assert "info --output=json" in "\n".join(_lines(pgbackrest_log))
    assert _lines(curl_log) == []


def test_pgbackrest_configuration_uses_seven_day_time_retention() -> None:
    config = (_REPO / "backup" / "pgbackrest.conf").read_text(encoding="utf-8")
    dockerfile = (_REPO / "backup" / "Dockerfile").read_text(encoding="utf-8")

    assert "repo1-retention-full=7" in config
    assert "repo1-retention-full-type=time" in config
    assert "archive-async=y" in config
    assert "archive-push-batch-size=1GiB" in config
    assert "archive-push-queue-max=4GiB" in config
    assert "spool-path=/tmp/pgbackrest" in config
    assert "pg1-path=/var/lib/postgresql/data" in config
    assert "pg1-socket-path=/var/run/postgresql" in config
    assert "postgresql16 postgresql16-client" in dockerfile


def test_both_images_bake_the_same_pgbackrest_configuration() -> None:
    # PostgreSQL (archive-push) and the sidecar (backup, check) must agree on
    # the repository, stanza and archive settings.
    backup = (_REPO / "backup" / "pgbackrest.conf").read_text(encoding="utf-8")
    database = (_REPO / "database" / "pgbackrest.conf").read_text(encoding="utf-8")
    assert database == backup
    for image in ("backup", "database"):
        dockerfile = (_REPO / image / "Dockerfile").read_text(encoding="utf-8")
        assert "COPY pgbackrest.conf /etc/pgbackrest/pgbackrest.conf" in dockerfile, image


def test_paas_compose_never_bind_mounts_a_repository_file() -> None:
    # Coolify resolves relative bind sources on the host, where repository
    # files don't exist; Docker then creates an empty directory there and the
    # container fails to start. Files must be baked into images instead.
    compose = yaml.safe_load((_REPO / "docker-compose.PaaS.yml").read_text(encoding="utf-8"))
    for name, service in compose["services"].items():
        for volume in service.get("volumes", []):
            source = volume.get("source", "") if isinstance(volume, dict) else str(volume).split(":", 1)[0]
            if source.startswith("."):
                assert not (_REPO / source).is_file(), f"{name}: {volume}"


def _service_block(compose: str, name: str) -> str:
    # A service ends at the next service or top-level key, together with the
    # comment lines that introduce it, so a neighbour's settings never leak in.
    block = compose.split(f"\n  {name}:\n", 1)[1]
    return re.split(r"\n(?:  #[^\n]*\n)*(?:  )?[a-z][a-z0-9_-]*:\n", block, maxsplit=1)[0]


def test_pgbackrest_compose_mounts_private_repo_and_read_only_database_files() -> None:
    compose = (_REPO / "docker-compose.PaaS.yml").read_text(encoding="utf-8")
    database = _service_block(compose, "postgres")
    service = _service_block(compose, "pgbackrest")

    assert "build: ./database" in database
    assert "PGBACKREST_ENABLED: ${PGBACKREST_ENABLED:-false}" in database
    assert "- ./pgbackrest:/pgbackrest" in database
    assert "- postgres-socket:/var/run/postgresql" in database
    assert "entrypoint: [\"/usr/local/bin/govmap-pgbackrest-scheduler\"]" in service
    assert "postgres-data:/var/lib/postgresql/data:ro" in service
    assert "postgres-socket:/var/run/postgresql" in service
    assert "- ./pgbackrest:/pgbackrest" in service
    assert "docker.sock" not in service
    assert "privileged" not in service


def test_database_image_declares_postgresql_provider_before_installing_pgbackrest() -> None:
    dockerfile = (_REPO / "database" / "Dockerfile").read_text(encoding="utf-8")

    # Without the empty provider, apk satisfies pgbackrest's generic `postgresql`
    # dependency with a second PostgreSQL server beside the official 16 build.
    provider = dockerfile.index("apk add --no-cache --virtual postgresql=16.0")
    install = dockerfile.index("apk add --no-cache pgbackrest")
    assert provider < install


def test_postgres_entrypoint_enables_archiving_only_after_explicit_opt_in() -> None:
    entrypoint = (_REPO / "database" / "entrypoint.sh").read_text(encoding="utf-8")

    assert 'PGBACKREST_ENABLED:-false' in entrypoint
    assert "archive_mode=on" in entrypoint
    assert "archive_timeout=300" in entrypoint
    assert "archive-push %p" in entrypoint
    assert "not owned by uid $uid" in entrypoint
