import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="requires Linux Bash and GNU tar")

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
_DOCKER = """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["FAKE_DOCKER_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")

if args[:2] == ["context", "inspect"]:
    print(os.environ.get("FAKE_DOCKER_ENDPOINT", "unix:///var/run/docker.sock"))
elif args[:1] == ["info"]:
    pass
elif args[:1] == ["inspect"]:
    print("postgres:16-alpine")
elif args[:1] == ["ps"]:
    print(os.environ.get(
        "FAKE_RUNNING_CONTAINERS",
        "postgres-testresource-20261109T123048"
    ))
elif args[:1] == ["exec"]:
    index = 1
    while args[index].startswith("-"):
        index += 1
    command = args[index + 1]
    if command == "pg_isready":
        if os.environ.get("FAKE_PG_READY_FAIL") == "1":
            sys.exit(1)
    elif command == "pg_dump":
        sys.stdout.buffer.write(b"synthetic database dump")
        if os.environ.get("FAKE_DUMP_FAIL") == "1":
            sys.exit(1)
    elif command == "pg_restore":
        if sys.stdin.buffer.read() != b"synthetic database dump":
            sys.exit(1)
        if os.environ.get("FAKE_VERIFY_FAIL") == "1":
            sys.exit(1)
    elif command == "psql":
        print("0013")
    else:
        sys.exit(1)
elif args[:1] == ["cp"]:
    sys.stdout.buffer.write(b"synthetic log archive")
    if os.environ.get("FAKE_LOG_FAIL") == "1":
        sys.exit(1)
else:
    sys.exit(1)
"""
_AGE = """#!/usr/bin/env python3
import os
import sys

args = sys.argv[1:]
if args[0] != "--encrypt":
    sys.exit(1)
sys.stdout.buffer.write(b"synthetic-age:" + sys.stdin.buffer.read())
if os.environ.get("FAKE_AGE_FAIL") == "1":
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


@dataclass(frozen=True)
class BackupContext:
    repository: Path
    destination: Path
    recipients: Path
    docker_log: Path
    curl_log: Path


@pytest.fixture
def backup_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BackupContext:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    for name in (
        "backup-common.sh",
        "backup-coolify-database.sh",
        "backup-coolify-daily.sh",
    ):
        shutil.copyfile(_SCRIPTS / name, scripts / name)

    destination = tmp_path / "backups"
    destination.mkdir()
    recipients = tmp_path / "recipients.txt"
    recipients.write_text("synthetic recipient\n", encoding="utf-8")
    docker_log = tmp_path / "docker.log"
    curl_log = tmp_path / "curl.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, content in (("docker", _DOCKER), ("age", _AGE), ("curl", _CURL)):
        executable = bin_dir / name
        executable.write_text(content, encoding="utf-8")
        executable.chmod(0o755)

    for name in (
        "FAKE_AGE_FAIL",
        "FAKE_CURL_EXIT",
        "FAKE_DOCKER_ENDPOINT",
        "FAKE_DUMP_FAIL",
        "FAKE_LOG_FAIL",
        "FAKE_PG_READY_FAIL",
        "FAKE_RUNNING_CONTAINERS",
        "FAKE_VERIFY_FAIL",
        "GOVMAP_BACKUP_DIR",
        "GOVMAP_CONFIG_DIR",
        "GOVMAP_HEARTBEAT_URL",
        "GOVMAP_RESOURCE_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))
    monkeypatch.setenv("FAKE_CURL_LOG", str(curl_log))
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    return BackupContext(repository, destination, recipients, docker_log, curl_log)


def _run(context: BackupContext, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(context.repository / "scripts" / script), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _coolify_backup_args(context: BackupContext) -> tuple[str, ...]:
    return (
        "--resource-id",
        "testresource",
        "--destination",
        str(context.destination),
        "--recipients-file",
        str(context.recipients),
    )


def _docker_calls(context: BackupContext) -> list[list[str]]:
    if not context.docker_log.exists():
        return []
    return [
        json.loads(line)
        for line in context.docker_log.read_text(encoding="utf-8").splitlines()
    ]


def _curl_calls(context: BackupContext) -> list[dict[str, object]]:
    if not context.curl_log.exists():
        return []
    return [
        json.loads(line)
        for line in context.curl_log.read_text(encoding="utf-8").splitlines()
    ]


def test_coolify_database_backup_selects_resource_and_publishes_encrypted_dump(
    backup_context: BackupContext,
) -> None:
    result = _run(
        backup_context, "backup-coolify-database.sh", *_coolify_backup_args(backup_context)
    )
    assert result.returncode == 0, result.stderr
    output = Path(result.stdout.strip())
    assert output.parent == backup_context.destination
    assert output.name.startswith("govmap-testresource-")
    assert output.name.endswith(".dump.age")
    assert output.read_bytes() == b"synthetic-age:synthetic database dump"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert not list(backup_context.destination.glob(".govmap-db-work-*"))


@pytest.mark.parametrize(
    ("environment", "value"),
    [
        ("FAKE_RUNNING_CONTAINERS", ""),
        (
            "FAKE_RUNNING_CONTAINERS",
            "postgres-testresource-20261109T123048\npostgres-testresource-20261109T123049",
        ),
        ("FAKE_PG_READY_FAIL", "1"),
        ("FAKE_DUMP_FAIL", "1"),
        ("FAKE_AGE_FAIL", "1"),
    ],
)
def test_coolify_database_backup_fails_closed_without_replacing_prior_backup(
    backup_context: BackupContext,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    value: str,
) -> None:
    previous = backup_context.destination / "previous.dump.age"
    previous.write_bytes(b"previous backup")
    monkeypatch.setenv(environment, value)
    result = _run(
        backup_context, "backup-coolify-database.sh", *_coolify_backup_args(backup_context)
    )
    assert result.returncode != 0
    assert previous.read_bytes() == b"previous backup"
    assert not list(backup_context.destination.glob("govmap-testresource-*.dump.age"))
    assert not list(backup_context.destination.glob(".govmap-db-work-*"))


def test_coolify_database_backup_refuses_repository_destination(
    backup_context: BackupContext,
) -> None:
    result = _run(
        backup_context,
        "backup-coolify-database.sh",
        "--resource-id",
        "testresource",
        "--destination",
        str(backup_context.repository),
        "--recipients-file",
        str(backup_context.recipients),
    )
    assert result.returncode != 0
    assert not _docker_calls(backup_context)


def test_coolify_database_backup_refuses_remote_docker_context(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_ENDPOINT", "ssh://example.invalid")
    result = _run(
        backup_context, "backup-coolify-database.sh", *_coolify_backup_args(backup_context)
    )
    assert result.returncode != 0
    assert not list(backup_context.destination.iterdir())
    assert not any(call[0] in ("ps", "exec") for call in _docker_calls(backup_context))


@pytest.mark.parametrize("existing_kind", ["file", "directory", "symlink"])
def test_publish_refuses_any_existing_destination(
    backup_context: BackupContext, existing_kind: str
) -> None:
    temporary = backup_context.destination / ".partial"
    temporary.write_bytes(b"new encrypted output")
    destination = backup_context.destination / "existing"
    if existing_kind == "file":
        destination.write_bytes(b"previous backup")
    elif existing_kind == "directory":
        destination.mkdir()
    else:
        destination.symlink_to("missing-target")

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; backup_publish "$2" "$3"',
            "backup-publish-test",
            str(backup_context.repository / "scripts" / "backup-common.sh"),
            str(temporary),
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode != 0
    assert temporary.read_bytes() == b"new encrypted output"
    if existing_kind == "file":
        assert destination.read_bytes() == b"previous backup"
    elif existing_kind == "directory":
        assert not list(destination.iterdir())
    else:
        assert destination.is_symlink() and os.readlink(destination) == "missing-target"


_DAILY_CONTAINERS = "postgres-testresource-20261109T123048\nbackend-testresource-20261109T123048"
_HEARTBEAT = "https://hc-ping.example/synthetic-secret-token"


def _daily_args(context: BackupContext) -> tuple[str, ...]:
    context.destination.chmod(0o700)
    return ("--resource-id", "testresource", "--destination", str(context.destination))


def _bundle_members(bundle: Path) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    with tarfile.open(bundle, "r:gz") as archive:
        for member in archive.getmembers():
            extracted = archive.extractfile(member) if member.isfile() else None
            if extracted is not None:
                members[member.name] = extracted.read()
    return members


def test_daily_bundle_contains_verified_dump_logs_config_and_manifest(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FAKE_RUNNING_CONTAINERS", _DAILY_CONTAINERS)
    config = tmp_path / "coolify-app"
    config.mkdir()
    (config / ".env").write_text("SYNTHETIC_SECRET=example\n", encoding="utf-8")
    result = _run(
        backup_context,
        "backup-coolify-daily.sh",
        *_daily_args(backup_context),
        "--config-dir",
        str(config),
    )
    assert result.returncode == 0, result.stderr
    output = Path(result.stdout.strip())
    assert output == backup_context.destination / "govmap-backup.tar.gz"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    members = _bundle_members(output)
    assert members["govmap-backup/database.dump"] == b"synthetic database dump"
    assert members["govmap-backup/logs.tar"] == b"synthetic log archive"
    assert members["govmap-backup/coolify-config/.env"] == b"SYNTHETIC_SECRET=example\n"
    manifest = members["govmap-backup/MANIFEST.txt"].decode()
    assert "alembic_revision=0013" in manifest
    assert "postgres_container=postgres-testresource-20261109T123048" in manifest
    checksums = members["govmap-backup/SHA256SUMS"].decode()
    for name in ("database.dump", "logs.tar", "MANIFEST.txt", "RESTORE.txt", "coolify-config/.env"):
        assert f"./{name}\n" in checksums
    assert sorted(p.name for p in backup_context.destination.iterdir()) == [
        ".govmap-backup.lock",
        "govmap-backup.tar.gz",
    ]
    restore_inputs = [call for call in _docker_calls(backup_context) if "pg_restore" in call]
    assert restore_inputs == [
        ["exec", "-i", "postgres-testresource-20261109T123048", "pg_restore", "--list"]
    ]
    assert not _curl_calls(backup_context)


def test_daily_bundle_reads_systemd_environment_and_replaces_previous_bundle(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup_context.destination.chmod(0o700)
    previous = backup_context.destination / "govmap-backup.tar.gz"
    previous.write_bytes(b"yesterday")
    monkeypatch.setenv("FAKE_RUNNING_CONTAINERS", _DAILY_CONTAINERS)
    monkeypatch.setenv("GOVMAP_RESOURCE_ID", "testresource")
    monkeypatch.setenv("GOVMAP_BACKUP_DIR", str(backup_context.destination))
    result = _run(backup_context, "backup-coolify-daily.sh")
    assert result.returncode == 0, result.stderr
    members = _bundle_members(previous)
    assert members["govmap-backup/database.dump"] == b"synthetic database dump"
    assert "coolify_config=not included" in members["govmap-backup/MANIFEST.txt"].decode()


@pytest.mark.parametrize(
    ("environment", "value"),
    [
        ("FAKE_RUNNING_CONTAINERS", "postgres-testresource-20261109T123048"),
        (
            "FAKE_RUNNING_CONTAINERS",
            _DAILY_CONTAINERS + "\npostgres-testresource-20261109T123049",
        ),
        ("FAKE_PG_READY_FAIL", "1"),
        ("FAKE_DUMP_FAIL", "1"),
        ("FAKE_VERIFY_FAIL", "1"),
        ("FAKE_LOG_FAIL", "1"),
    ],
)
def test_daily_bundle_failure_keeps_previous_bundle_and_skips_heartbeat(
    backup_context: BackupContext,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    value: str,
) -> None:
    args = _daily_args(backup_context)
    previous = backup_context.destination / "govmap-backup.tar.gz"
    previous.write_bytes(b"yesterday")
    monkeypatch.setenv("FAKE_RUNNING_CONTAINERS", _DAILY_CONTAINERS)
    monkeypatch.setenv("GOVMAP_HEARTBEAT_URL", _HEARTBEAT)
    monkeypatch.setenv(environment, value)
    result = _run(backup_context, "backup-coolify-daily.sh", *args)
    assert result.returncode != 0
    assert previous.read_bytes() == b"yesterday"
    assert not list(backup_context.destination.glob(".govmap-backup-work-*"))
    assert not _curl_calls(backup_context)


def test_daily_bundle_refuses_group_accessible_destination(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_RUNNING_CONTAINERS", _DAILY_CONTAINERS)
    backup_context.destination.chmod(0o750)
    result = _run(
        backup_context,
        "backup-coolify-daily.sh",
        "--resource-id",
        "testresource",
        "--destination",
        str(backup_context.destination),
    )
    assert result.returncode != 0
    assert "group or others" in result.stderr
    assert not list(backup_context.destination.iterdir())


def test_daily_bundle_pings_heartbeat_without_exposing_url_in_arguments(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_RUNNING_CONTAINERS", _DAILY_CONTAINERS)
    monkeypatch.setenv("GOVMAP_HEARTBEAT_URL", _HEARTBEAT)
    result = _run(backup_context, "backup-coolify-daily.sh", *_daily_args(backup_context))
    assert result.returncode == 0, result.stderr
    calls = _curl_calls(backup_context)
    assert len(calls) == 1
    assert calls[0]["stdin"] == f'url = "{_HEARTBEAT}"\n'
    arguments = calls[0]["args"]
    assert isinstance(arguments, list)
    assert "--fail" in arguments
    assert not any("synthetic-secret-token" in argument for argument in arguments)


def test_daily_bundle_heartbeat_failure_warns_but_keeps_new_bundle(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_RUNNING_CONTAINERS", _DAILY_CONTAINERS)
    monkeypatch.setenv("GOVMAP_HEARTBEAT_URL", _HEARTBEAT)
    monkeypatch.setenv("FAKE_CURL_EXIT", "22")
    result = _run(backup_context, "backup-coolify-daily.sh", *_daily_args(backup_context))
    assert result.returncode == 0, result.stderr
    assert "heartbeat ping failed" in result.stderr
    assert "synthetic-secret-token" not in result.stderr
    output = backup_context.destination / "govmap-backup.tar.gz"
    assert _bundle_members(output)["govmap-backup/database.dump"] == b"synthetic database dump"


@pytest.mark.parametrize(
    "url",
    ["http://hc-ping.example/token", "https://hc-ping.example/a b", 'https://x/"y'],
)
def test_daily_bundle_rejects_unsafe_heartbeat_url_before_backing_up(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("FAKE_RUNNING_CONTAINERS", _DAILY_CONTAINERS)
    monkeypatch.setenv("GOVMAP_HEARTBEAT_URL", url)
    result = _run(backup_context, "backup-coolify-daily.sh", *_daily_args(backup_context))
    assert result.returncode != 0
    assert "https://" in result.stderr
    assert not _docker_calls(backup_context)
    assert not _curl_calls(backup_context)
