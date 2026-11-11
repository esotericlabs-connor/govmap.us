import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="requires Linux Bash and GNU tar")

_BACKUP_DIR = Path(__file__).resolve().parents[2] / "backup"
_HEARTBEAT = "https://hc.example.test/ping/synthetic-token"
_POSTGRES = """#!/usr/bin/env python3
import json
import os
import sys

name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
with open(os.environ["FAKE_PG_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({
        "name": name,
        "args": args,
        "host": os.environ.get("PGHOST"),
        "user": os.environ.get("PGUSER"),
        "database": os.environ.get("PGDATABASE"),
        "password_set": bool(os.environ.get("PGPASSWORD")),
    }) + "\\n")

if name == "pg_isready":
    sys.exit(1 if os.environ.get("FAKE_PG_READY_FAIL") == "1" else 0)
if name == "pg_dump":
    if args == ["--version"]:
        print("pg_dump (PostgreSQL) 16.9")
        sys.exit(0)
    sys.stdout.buffer.write(b"synthetic database dump")
    sys.exit(1 if os.environ.get("FAKE_DUMP_FAIL") == "1" else 0)
if name == "pg_restore":
    with open(args[-1], "rb") as dump:
        if dump.read() != b"synthetic database dump":
            sys.exit(1)
    sys.exit(1 if os.environ.get("FAKE_VERIFY_FAIL") == "1" else 0)
if name == "psql":
    command = " ".join(args)
    if "alembic_version" in command:
        print("0013")
    elif "server_version" in command:
        print("16.9")
    else:
        sys.exit(1)
    sys.exit(0)
sys.exit(1)
"""
_CURL = """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["FAKE_CURL_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"args": sys.argv[1:], "stdin": sys.stdin.read()}) + "\\n")
sys.exit(int(os.environ.get("FAKE_CURL_EXIT", "0")))
"""
# Records the requested duration, then stops the scheduler the way a
# container stop would, so each scheduler test ends after its first pause.
_SLEEP = """#!/usr/bin/env python3
import os
import signal
import sys

with open(os.environ["FAKE_SLEEP_LOG"], "a", encoding="utf-8") as log:
    log.write(sys.argv[1] + "\\n")
os.kill(os.getppid(), signal.SIGTERM)
"""
_FAKE_BACKUP = """#!/usr/bin/env bash
printf 'run\\n' >> "$FAKE_BACKUP_LOG"
exit "${FAKE_BACKUP_EXIT:-0}"
"""


@dataclass(frozen=True)
class Context:
    destination: Path
    logs: Path
    pg_log: Path
    curl_log: Path
    sleep_log: Path
    backup_log: Path
    bin_dir: Path


def _install(bin_dir: Path, name: str, content: str) -> None:
    executable = bin_dir / name
    executable.write_text(content, encoding="utf-8")
    executable.chmod(0o755)


@pytest.fixture
def context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Context:
    destination = tmp_path / "backups"
    destination.mkdir()
    destination.chmod(0o700)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_text("synthetic app log\n", encoding="utf-8")
    (logs / "bug_reports.log").write_text("synthetic bug report\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("pg_isready", "pg_dump", "pg_restore", "psql"):
        _install(bin_dir, name, _POSTGRES)
    _install(bin_dir, "curl", _CURL)

    for name in (
        "BACKUP_ENABLED",
        "BACKUP_HEARTBEAT_URL",
        "BACKUP_INTERVAL_MINUTES",
        "BACKUP_TIME_UTC",
        "FAKE_BACKUP_EXIT",
        "FAKE_CURL_EXIT",
        "FAKE_DUMP_FAIL",
        "FAKE_PG_READY_FAIL",
        "FAKE_VERIFY_FAIL",
        "PGDATABASE",
        "PGHOST",
        "PGPORT",
        "PGUSER",
    ):
        monkeypatch.delenv(name, raising=False)
    context = Context(
        destination=destination,
        logs=logs,
        pg_log=tmp_path / "pg.log",
        curl_log=tmp_path / "curl.log",
        sleep_log=tmp_path / "sleep.log",
        backup_log=tmp_path / "backup.log",
        bin_dir=bin_dir,
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("BACKUP_TARGET", "production")
    monkeypatch.setenv("BACKUP_DIR", str(destination))
    monkeypatch.setenv("BACKUP_LOG_DIR", str(logs))
    monkeypatch.setenv("PGPASSWORD", "synthetic-password")
    monkeypatch.setenv("FAKE_PG_LOG", str(context.pg_log))
    monkeypatch.setenv("FAKE_CURL_LOG", str(context.curl_log))
    monkeypatch.setenv("FAKE_SLEEP_LOG", str(context.sleep_log))
    monkeypatch.setenv("FAKE_BACKUP_LOG", str(context.backup_log))
    return context


def _backup() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_BACKUP_DIR / "backup.sh")],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _scheduler(context: Context) -> subprocess.CompletedProcess[str]:
    _install(context.bin_dir, "sleep", _SLEEP)
    _install(context.bin_dir, "govmap-backup", _FAKE_BACKUP)
    return subprocess.run(
        ["bash", str(_BACKUP_DIR / "run.sh")],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _pg_calls(context: Context) -> list[dict[str, object]]:
    return [json.loads(line) for line in _lines(context.pg_log)]


def _curl_calls(context: Context) -> list[dict[str, object]]:
    return [json.loads(line) for line in _lines(context.curl_log)]


def _write_previous_bundle(context: Context) -> Path:
    output = context.destination / "govmap-backup.tar.gz"
    output.write_bytes(b"previous bundle")
    return output


def test_backup_publishes_verified_bundle_and_pings_after_publish(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_HEARTBEAT_URL", _HEARTBEAT)

    result = _backup()

    assert result.returncode == 0, result.stderr
    output = context.destination / "govmap-backup.tar.gz"
    assert result.stdout.strip() == str(output)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert not list(context.destination.glob(".govmap-backup-work-*"))
    with tarfile.open(output, "r:gz") as archive:
        names = set(archive.getnames())
        manifest = archive.extractfile("govmap-backup/MANIFEST.txt")
        assert manifest is not None
        manifest_text = manifest.read().decode()
        dump = archive.extractfile("govmap-backup/database.dump")
        assert dump is not None
        assert dump.read() == b"synthetic database dump"
        logs = archive.extractfile("govmap-backup/logs.tar")
        assert logs is not None
        with tarfile.open(fileobj=logs) as log_archive:
            log_names = {Path(name).name for name in log_archive.getnames()}
    assert {
        "govmap-backup/database.dump",
        "govmap-backup/logs.tar",
        "govmap-backup/MANIFEST.txt",
        "govmap-backup/RESTORE.txt",
        "govmap-backup/SHA256SUMS",
    } <= names
    assert not any("config" in name for name in names)
    assert {"app.log", "bug_reports.log"} <= log_names
    assert "backup_target=production\n" in manifest_text
    assert "alembic_revision=0013\n" in manifest_text
    assert "postgres_server_version=16.9\n" in manifest_text
    assert "deployment_config=not included" in manifest_text

    calls = _pg_calls(context)
    assert all(call["host"] == "postgres" for call in calls)
    assert all(call["user"] == "govmap" and call["database"] == "govmap" for call in calls)
    assert all(call["password_set"] for call in calls)
    assert not any("synthetic-password" in json.dumps(call["args"]) for call in calls)

    curl = _curl_calls(context)
    assert len(curl) == 1
    assert _HEARTBEAT not in json.dumps(curl[0]["args"])
    assert curl[0]["stdin"] == f'url = "{_HEARTBEAT}"\n'


@pytest.mark.parametrize("kind", ["missing", "symlink", "file"])
def test_backup_fails_closed_without_real_destination_directory(
    context: Context, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    monkeypatch.setenv("BACKUP_HEARTBEAT_URL", _HEARTBEAT)
    destination = tmp_path / "configured-destination"
    if kind == "symlink":
        destination.symlink_to(context.destination)
    elif kind == "file":
        destination.write_bytes(b"not a directory")
    monkeypatch.setenv("BACKUP_DIR", str(destination))

    result = _backup()

    assert result.returncode != 0
    assert "must be an existing writable directory" in result.stderr
    assert _pg_calls(context) == []
    assert _curl_calls(context) == []
    assert not (context.destination / "govmap-backup.tar.gz").exists()


@pytest.mark.parametrize("target", [None, "", "unconfigured", "Production", "../prod", "a" * 33])
def test_backup_requires_named_target(
    context: Context, monkeypatch: pytest.MonkeyPatch, target: str | None
) -> None:
    monkeypatch.setenv("BACKUP_HEARTBEAT_URL", _HEARTBEAT)
    if target is None:
        monkeypatch.delenv("BACKUP_TARGET")
    else:
        monkeypatch.setenv("BACKUP_TARGET", target)

    result = _backup()

    assert result.returncode != 0
    assert "BACKUP_TARGET" in result.stderr
    assert _pg_calls(context) == []
    assert _curl_calls(context) == []


def test_backup_restricts_group_accessible_destination(context: Context) -> None:
    context.destination.chmod(0o755)

    result = _backup()

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(context.destination.stat().st_mode) == 0o700


def test_backup_requires_database_password(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PGPASSWORD")

    result = _backup()

    assert result.returncode != 0
    assert "PGPASSWORD" in result.stderr
    assert _pg_calls(context) == []


@pytest.mark.parametrize("failure", ["FAKE_PG_READY_FAIL", "FAKE_DUMP_FAIL", "FAKE_VERIFY_FAIL"])
def test_backup_failure_keeps_previous_bundle_without_heartbeat(
    context: Context, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    monkeypatch.setenv("BACKUP_HEARTBEAT_URL", _HEARTBEAT)
    monkeypatch.setenv(failure, "1")
    previous = _write_previous_bundle(context)

    result = _backup()

    assert result.returncode != 0
    assert previous.read_bytes() == b"previous bundle"
    assert not list(context.destination.glob(".govmap-backup-work-*"))
    assert _curl_calls(context) == []


@pytest.mark.parametrize(
    "url", ["http://hc.example.test/ping/x", "https://a.test/x b", 'https://a.test/"x']
)
def test_backup_rejects_unsafe_heartbeat_url_before_dumping(
    context: Context, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("BACKUP_HEARTBEAT_URL", url)

    result = _backup()

    assert result.returncode != 0
    assert "BACKUP_HEARTBEAT_URL" in result.stderr
    assert _pg_calls(context) == []
    assert _curl_calls(context) == []


def test_failed_heartbeat_warns_but_keeps_published_bundle(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_HEARTBEAT_URL", _HEARTBEAT)
    monkeypatch.setenv("FAKE_CURL_EXIT", "22")

    result = _backup()

    assert result.returncode == 0, result.stderr
    assert "heartbeat ping failed" in result.stderr
    assert (context.destination / "govmap-backup.tar.gz").is_file()


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can read any file"
)
def test_unreadable_log_file_is_skipped_not_fatal(context: Context) -> None:
    secret = context.logs / "unreadable.log"
    secret.write_text("x\n", encoding="utf-8")
    secret.chmod(0)
    try:
        result = _backup()
    finally:
        secret.chmod(0o600)

    assert result.returncode == 0, result.stderr
    assert (context.destination / "govmap-backup.tar.gz").is_file()


def test_scheduler_idles_when_disabled(context: Context) -> None:
    result = _scheduler(context)

    assert result.returncode == 143
    assert "disabled" in result.stdout
    assert _lines(context.sleep_log) == ["86400"]
    assert _lines(context.backup_log) == []


@pytest.mark.parametrize("age_hours", [None, 25])
def test_scheduler_catches_up_when_bundle_missing_or_stale(
    context: Context, monkeypatch: pytest.MonkeyPatch, age_hours: int | None
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    if age_hours is not None:
        bundle = _write_previous_bundle(context)
        stale = time.time() - age_hours * 3600
        os.utime(bundle, (stale, stale))

    result = _scheduler(context)

    assert result.returncode == 143
    assert _lines(context.backup_log) == ["run"]
    assert "catch-up" in result.stdout
    sleeps = _lines(context.sleep_log)
    assert len(sleeps) == 1
    assert 0 < int(sleeps[0]) <= 86400


def test_scheduler_skips_catch_up_for_recent_bundle(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setenv("BACKUP_TIME_UTC", "04:15")
    _write_previous_bundle(context)

    result = _scheduler(context)

    assert result.returncode == 143
    assert _lines(context.backup_log) == []
    assert "T04:15:00Z" in result.stdout
    assert 0 < int(_lines(context.sleep_log)[0]) <= 86400


@pytest.mark.parametrize(
    ("interval", "anchor", "minutes"),
    [
        ("30", "02:30", {"00", "30"}),
        ("60", "02:10", {"10"}),
        ("15", "00:05", {"05", "20", "35", "50"}),
    ],
)
def test_scheduler_runs_on_the_interval_grid(
    context: Context,
    monkeypatch: pytest.MonkeyPatch,
    interval: str,
    anchor: str,
    minutes: set[str],
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setenv("BACKUP_INTERVAL_MINUTES", interval)
    monkeypatch.setenv("BACKUP_TIME_UTC", anchor)
    _write_previous_bundle(context)

    result = _scheduler(context)

    assert result.returncode == 143
    assert _lines(context.backup_log) == []
    assert f"every {interval} minutes" in result.stdout
    assert 0 < int(_lines(context.sleep_log)[0]) <= int(interval) * 60
    next_run = re.search(r"Next backup at \d{4}-\d{2}-\d{2}T\d{2}:(\d{2}):(\d{2})Z", result.stdout)
    assert next_run is not None
    assert next_run[1] in minutes
    assert next_run[2] == "00"


def test_scheduler_catches_up_after_one_interval(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setenv("BACKUP_INTERVAL_MINUTES", "30")
    bundle = _write_previous_bundle(context)
    stale = time.time() - 31 * 60
    os.utime(bundle, (stale, stale))

    result = _scheduler(context)

    assert result.returncode == 143
    assert _lines(context.backup_log) == ["run"]
    assert "catch-up" in result.stdout
    assert 0 < int(_lines(context.sleep_log)[0]) <= 1800


@pytest.mark.parametrize("value", ["0", "4", "7", "50", "1441", "2880", "030", "30m", " 30", "-30"])
def test_scheduler_rejects_invalid_interval(
    context: Context, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setenv("BACKUP_INTERVAL_MINUTES", value)

    result = _scheduler(context)

    assert result.returncode == 1
    assert "BACKUP_INTERVAL_MINUTES" in result.stdout
    assert _lines(context.sleep_log) == []
    assert _lines(context.backup_log) == []


def test_scheduler_continues_after_failed_backup(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setenv("FAKE_BACKUP_EXIT", "1")

    result = _scheduler(context)

    assert result.returncode == 143
    assert "Backup failed with exit status 1" in result.stdout
    assert len(_lines(context.sleep_log)) == 1


@pytest.mark.parametrize("value", ["2:30", "24:00", "02:60", "0230", "02:30 "])
def test_scheduler_rejects_invalid_time(
    context: Context, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setenv("BACKUP_TIME_UTC", value)

    result = _scheduler(context)

    assert result.returncode == 1
    assert "BACKUP_TIME_UTC" in result.stdout
    assert _lines(context.sleep_log) == []
    assert _lines(context.backup_log) == []


def _service_block(compose: str, name: str) -> str:
    # A service ends at the next service or top-level key, together with the
    # comment lines that introduce it, so a neighbour's settings never leak in.
    block = compose.split(f"\n  {name}:\n", 1)[1]
    return re.split(r"\n(?:  #[^\n]*\n)*(?:  )?[a-z][a-z0-9_-]*:\n", block, maxsplit=1)[0]


def test_compose_backup_service_is_hardened_and_fails_closed() -> None:
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.PaaS.yml").read_text(
        encoding="utf-8"
    )
    service = _service_block(compose, "backup")
    assert "BACKUP_ENABLED: ${BACKUP_ENABLED:-false}" in service
    assert "BACKUP_TARGET: ${BACKUP_TARGET:-unconfigured}" in service
    assert "BACKUP_INTERVAL_MINUTES: ${BACKUP_INTERVAL_MINUTES:-1440}" in service
    assert "- ./backups:/backups" in service
    assert "${" not in service.split("volumes:", 1)[1]
    assert "- govmap-logs:/logs:ro" in service
    assert "read_only: true" in service
    assert "- ALL" in service
    assert service.split("cap_add:", 1)[1].split("security_opt:", 1)[0].split() == [
        "-",
        "CHOWN",
        "-",
        "SETUID",
        "-",
        "SETGID",
    ]
    assert "no-new-privileges:true" in service
    assert "docker.sock" not in service
    assert "privileged" not in service
    assert "user:" not in service


_ENTRYPOINT_TOOL = """#!/usr/bin/env bash
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$FAKE_ENTRYPOINT_LOG"
case "$(basename "$0")" in
  id) printf '%s\\n' "$FAKE_UID" ;;
  stat) printf '%s\\n' "$FAKE_OWNER" ;;
esac
"""


def _entrypoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    uid: str,
    owner: str,
    populated: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "entrypoint-bin"
    bin_dir.mkdir()
    for name in ("id", "stat", "chmod", "chown", "setpriv", "govmap-backup-scheduler"):
        _install(bin_dir, name, _ENTRYPOINT_TOOL)
    log = tmp_path / "entrypoint.log"
    destination = tmp_path / "entrypoint-backups"
    destination.mkdir()
    if populated:
        (destination / "unrelated.txt").write_text("x\n", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_ENTRYPOINT_LOG", str(log))
    monkeypatch.setenv("FAKE_UID", uid)
    monkeypatch.setenv("FAKE_OWNER", owner)
    monkeypatch.setenv("BACKUP_DIR", str(destination))
    result = subprocess.run(
        ["bash", str(_BACKUP_DIR / "entrypoint.sh")],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    calls = [
        line.replace(str(destination), "DIR")
        for line in _lines(log)
        if not line.startswith(("id ", "stat "))
    ]
    return result, calls


_DROP = "setpriv --reuid=70 --regid=70 --clear-groups --inh-caps=-all -- govmap-backup-scheduler"
_ADOPT = ["chown 0:0 -- DIR", "chmod 700 -- DIR", "chown 70:70 -- DIR"]


@pytest.mark.parametrize("owner", ["0", "1000"])
def test_entrypoint_adopts_new_empty_directory_then_drops_privileges(
    context: Context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, owner: str
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", "true")

    result, calls = _entrypoint(tmp_path, monkeypatch, uid="0", owner=owner)

    assert result.returncode == 0, result.stderr
    assert calls == [*_ADOPT, _DROP]


def test_entrypoint_adopts_non_empty_root_owned_directory(
    context: Context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", "true")

    result, calls = _entrypoint(tmp_path, monkeypatch, uid="0", owner="0", populated=True)

    assert result.returncode == 0, result.stderr
    assert calls == [*_ADOPT, _DROP]


@pytest.mark.parametrize(
    ("enabled", "target", "owner", "populated"),
    [
        ("true", "production", "70", False),
        ("true", "production", "1000", True),
        ("false", "production", "0", False),
        ("false", "production", "1000", False),
        ("true", "unconfigured", "1000", False),
        ("true", "../prod", "0", False),
    ],
)
def test_entrypoint_leaves_directory_alone_unless_enabled_named_and_safe_to_adopt(
    context: Context,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    enabled: str,
    target: str,
    owner: str,
    populated: bool,
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", enabled)
    monkeypatch.setenv("BACKUP_TARGET", target)

    result, calls = _entrypoint(
        tmp_path, monkeypatch, uid="0", owner=owner, populated=populated
    )

    assert result.returncode == 0, result.stderr
    assert calls == [_DROP]


def test_entrypoint_runs_scheduler_directly_when_not_root(
    context: Context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_ENABLED", "true")

    result, calls = _entrypoint(tmp_path, monkeypatch, uid="70", owner="0")

    assert result.returncode == 0, result.stderr
    assert calls == ["govmap-backup-scheduler "]
