import io
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
elif args[:1] == ["info"] or args[:2] == ["image", "inspect"]:
    pass
elif args[:1] == ["inspect"]:
    print(os.environ.get("FAKE_LOG_VOLUME", "govmap_govmap-logs"))
elif args[:1] == ["run"]:
    sys.stdout.buffer.write(b"synthetic log archive")
    if os.environ.get("FAKE_LOG_FAIL") == "1":
        sys.exit(1)
elif args[:1] == ["compose"]:
    if "ps" in args:
        if "--status" in args:
            if os.environ.get("FAKE_BACKEND_RUNNING") == "1":
                print("a" * 64)
        else:
            print("a" * 64)
    elif "exec" in args:
        command = args[args.index("-c") + 1]
        if "pg_dump" in command:
            sys.stdout.buffer.write(b"synthetic database dump")
            if os.environ.get("FAKE_DUMP_FAIL") == "1":
                sys.exit(1)
        elif "psql" in command:
            print(os.environ.get("FAKE_OBJECTS", "0"))
        elif "pg_restore" in command:
            if sys.stdin.buffer.read() != b"synthetic database dump":
                sys.exit(1)
            if os.environ.get("FAKE_RESTORE_FAIL") == "1":
                sys.exit(1)
        else:
            sys.exit(1)
    else:
        sys.exit(1)
else:
    sys.exit(1)
"""
_AGE = """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

args = sys.argv[1:]
if args[0] == "--encrypt":
    data = sys.stdin.buffer.read()
    recipients = Path(args[args.index("--recipients-file") + 1])
    recipient_log = os.environ.get("FAKE_AGE_RECIPIENT_LOG")
    if recipient_log:
        with open(recipient_log, "a", encoding="utf-8") as log:
            log.write(recipients.read_text(encoding="utf-8").strip() + "\\n")
    rotate_recipients = os.environ.get("FAKE_ROTATE_RECIPIENTS")
    if rotate_recipients and data == b"synthetic database dump":
        Path(rotate_recipients).write_text("rotated recipient\\n", encoding="utf-8")
    sys.stdout.buffer.write(b"synthetic-age:" + data)
    if data == b"synthetic database dump":
        stage = "database"
    elif data == b"synthetic log archive":
        stage = "logs"
    else:
        stage = "archive"
    if os.environ.get("FAKE_AGE_FAIL") == "1" or os.environ.get("FAKE_AGE_FAIL_ON") == stage:
        sys.exit(1)
elif args[0] == "--decrypt":
    if os.environ.get("FAKE_DECRYPT_FAIL") == "1":
        sys.exit(1)
    data = Path(args[-1]).read_bytes()
    if not data.startswith(b"synthetic-age:"):
        sys.exit(1)
    sys.stdout.buffer.write(data[len(b"synthetic-age:"):])
else:
    sys.exit(1)
"""


@dataclass(frozen=True)
class BackupContext:
    repository: Path
    destination: Path
    recipients: Path
    identity: Path
    docker_log: Path


@pytest.fixture
def backup_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BackupContext:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    for name in (
        "backup-common.sh",
        "backup-database.sh",
        "backup-govmap.sh",
        "duplicati-database-hook.sh",
        "restore-database.sh",
    ):
        shutil.copyfile(_SCRIPTS / name, scripts / name)
    (repository / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (repository / ".env").write_text("SYNTHETIC_CONFIG=example\n", encoding="utf-8")
    (repository / ".git").mkdir()
    (repository / ".git" / "config").write_text("synthetic git config\n", encoding="utf-8")
    assets = repository / "frontend" / "public"
    assets.mkdir(parents=True)
    (assets / "asset.txt").write_text("application asset\n", encoding="utf-8")
    (assets / "asset-link.txt").symlink_to("./asset.txt")
    dependencies = repository / "frontend" / "node_modules"
    dependencies.mkdir()
    (dependencies / "excluded.txt").write_text("not backed up\n", encoding="utf-8")

    destination = tmp_path / "backups"
    destination.mkdir()
    recipients = tmp_path / "recipients.txt"
    recipients.write_text("synthetic recipient\n", encoding="utf-8")
    identity = tmp_path / "identity.txt"
    identity.write_text("synthetic identity\n", encoding="utf-8")
    docker_log = tmp_path / "docker.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, content in (("docker", _DOCKER), ("age", _AGE)):
        executable = bin_dir / name
        executable.write_text(content, encoding="utf-8")
        executable.chmod(0o755)

    for name in (
        "FAKE_AGE_FAIL",
        "FAKE_AGE_FAIL_ON",
        "FAKE_AGE_RECIPIENT_LOG",
        "FAKE_BACKEND_RUNNING",
        "FAKE_DECRYPT_FAIL",
        "FAKE_DOCKER_ENDPOINT",
        "FAKE_DUMP_FAIL",
        "FAKE_LOG_FAIL",
        "FAKE_LOG_VOLUME",
        "FAKE_OBJECTS",
        "FAKE_RESTORE_FAIL",
        "FAKE_ROTATE_RECIPIENTS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    return BackupContext(repository, destination, recipients, identity, docker_log)


def _run(context: BackupContext, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(context.repository / "scripts" / script), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _backup_args(context: BackupContext) -> tuple[str, ...]:
    return (
        "--destination",
        str(context.destination),
        "--recipients-file",
        str(context.recipients),
    )


def _restore_args(context: BackupContext, backup: Path) -> tuple[str, ...]:
    return (
        "--backup",
        str(backup),
        "--identity-file",
        str(context.identity),
        "--confirm-isolated-empty-target",
    )


def _docker_calls(context: BackupContext) -> list[list[str]]:
    if not context.docker_log.exists():
        return []
    return [
        json.loads(line)
        for line in context.docker_log.read_text(encoding="utf-8").splitlines()
    ]


def test_database_backup_publishes_private_encrypted_dump(backup_context: BackupContext) -> None:
    result = _run(backup_context, "backup-database.sh", *_backup_args(backup_context))
    assert result.returncode == 0, result.stderr
    output = Path(result.stdout.strip())
    assert output.parent == backup_context.destination
    assert output.name.endswith(".dump.age")
    assert output.read_bytes() == b"synthetic-age:synthetic database dump"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert list(backup_context.destination.iterdir()) == [output]


@pytest.mark.parametrize("failure", ["FAKE_DUMP_FAIL", "FAKE_AGE_FAIL"])
def test_database_failure_keeps_previous_backup(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    previous = backup_context.destination / "previous.dump.age"
    previous.write_bytes(b"previous backup")
    monkeypatch.setenv(failure, "1")
    result = _run(backup_context, "backup-database.sh", *_backup_args(backup_context))
    assert result.returncode != 0
    assert not result.stdout
    assert previous.read_bytes() == b"previous backup"
    assert list(backup_context.destination.iterdir()) == [previous]


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


def test_backup_refuses_repository_destination(backup_context: BackupContext) -> None:
    result = _run(
        backup_context,
        "backup-database.sh",
        "--destination",
        str(backup_context.repository),
        "--recipients-file",
        str(backup_context.recipients),
    )
    assert result.returncode != 0
    assert not _docker_calls(backup_context)


def test_backup_refuses_remote_docker_context(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_ENDPOINT", "ssh://example.invalid")
    result = _run(backup_context, "backup-database.sh", *_backup_args(backup_context))
    assert result.returncode != 0
    assert not list(backup_context.destination.iterdir())
    assert not any(call[0] == "compose" for call in _docker_calls(backup_context))


def test_full_archive_contains_configuration_database_and_logs(
    backup_context: BackupContext,
) -> None:
    result = _run(backup_context, "backup-govmap.sh", *_backup_args(backup_context))
    assert result.returncode == 0, result.stderr
    output = Path(result.stdout.strip())
    encrypted = output.read_bytes()
    assert encrypted.startswith(b"synthetic-age:")
    with tarfile.open(fileobj=io.BytesIO(encrypted[len(b"synthetic-age:") :]), mode="r:") as archive:
        names = archive.getnames()
        assert "app/.env" in names
        assert "app/.git/config" in names
        assert "app/frontend/public/asset.txt" in names
        assert "app/frontend/node_modules/excluded.txt" not in names
        link = archive.getmember("app/frontend/public/asset-link.txt")
        assert link.issym() and link.linkname == "./asset.txt"
        database = archive.extractfile("database.dump.age")
        logs = archive.extractfile("logs.tar.age")
        assert database is not None and database.read() == b"synthetic-age:synthetic database dump"
        assert logs is not None and logs.read() == b"synthetic-age:synthetic log archive"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert list(backup_context.destination.iterdir()) == [output]
    log_reader = next(call for call in _docker_calls(backup_context) if call[0] == "run")
    assert "--network" in log_reader and log_reader[log_reader.index("--network") + 1] == "none"
    assert any("readonly" in arg for arg in log_reader)


@pytest.mark.parametrize(
    ("failure", "value"),
    [
        ("FAKE_DUMP_FAIL", "1"),
        ("FAKE_LOG_FAIL", "1"),
        ("FAKE_AGE_FAIL", "1"),
        ("FAKE_AGE_FAIL_ON", "logs"),
        ("FAKE_AGE_FAIL_ON", "archive"),
    ],
)
def test_full_archive_failure_leaves_no_partial_files(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch, failure: str, value: str
) -> None:
    previous = backup_context.destination / "previous.tar.age"
    previous.write_bytes(b"previous backup")
    monkeypatch.setenv(failure, value)
    result = _run(backup_context, "backup-govmap.sh", *_backup_args(backup_context))
    assert result.returncode != 0
    assert not result.stdout
    assert previous.read_bytes() == b"previous backup"
    assert list(backup_context.destination.iterdir()) == [previous]


def test_full_archive_uses_one_recipient_snapshot(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipient_log = backup_context.recipients.parent / "recipient-log"
    monkeypatch.setenv("FAKE_AGE_RECIPIENT_LOG", str(recipient_log))
    monkeypatch.setenv("FAKE_ROTATE_RECIPIENTS", str(backup_context.recipients))
    result = _run(backup_context, "backup-govmap.sh", *_backup_args(backup_context))
    assert result.returncode == 0, result.stderr
    assert backup_context.recipients.read_text(encoding="utf-8") == "rotated recipient\n"
    assert recipient_log.read_text(encoding="utf-8").splitlines() == ["synthetic recipient"] * 3


def test_full_archive_tar_failure_preserves_previous_backup(backup_context: BackupContext) -> None:
    previous = backup_context.destination / "previous.tar.age"
    previous.write_bytes(b"previous backup")
    fake_tar = backup_context.recipients.parent / "bin" / "tar"
    fake_tar.write_text("#!/bin/sh\nprintf 'partial archive'\nexit 1\n", encoding="utf-8")
    fake_tar.chmod(0o755)
    result = _run(backup_context, "backup-govmap.sh", *_backup_args(backup_context))
    assert result.returncode != 0
    assert not result.stdout
    assert previous.read_bytes() == b"previous backup"
    assert list(backup_context.destination.iterdir()) == [previous]


def test_full_archive_requires_persistent_log_volume(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_LOG_VOLUME", "")
    result = _run(backup_context, "backup-govmap.sh", *_backup_args(backup_context))
    assert result.returncode != 0
    assert not list(backup_context.destination.iterdir())


def test_duplicati_hook_publishes_database_dump(backup_context: BackupContext) -> None:
    result = _run(backup_context, "duplicati-database-hook.sh", *_backup_args(backup_context))
    assert result.returncode == 0, result.stderr
    output = Path(result.stdout.strip())
    assert output.parent == backup_context.destination
    assert output.read_bytes() == b"synthetic-age:synthetic database dump"


def test_duplicati_hook_rejects_help_instead_of_skipping_the_backup(
    backup_context: BackupContext,
) -> None:
    result = _run(backup_context, "duplicati-database-hook.sh", "--help")
    assert result.returncode == 5
    assert not result.stdout
    assert not _docker_calls(backup_context)


@pytest.mark.parametrize("exit_code", [1, 2, 4, 127])
def test_duplicati_hook_maps_all_backup_failures_to_error(
    backup_context: BackupContext, exit_code: int
) -> None:
    database_script = backup_context.repository / "scripts" / "backup-database.sh"
    database_script.write_text(f"#!/usr/bin/env bash\nexit {exit_code}\n", encoding="utf-8")
    result = _run(backup_context, "duplicati-database-hook.sh", *_backup_args(backup_context))
    assert result.returncode == 5
    assert f"exit {exit_code}" in result.stderr
    assert not result.stdout
    assert not list(backup_context.destination.iterdir())


def test_restore_requires_explicit_confirmation(backup_context: BackupContext) -> None:
    backup = backup_context.destination / "database.dump.age"
    backup.write_bytes(b"synthetic-age:synthetic database dump")
    result = _run(
        backup_context,
        "restore-database.sh",
        "--backup",
        str(backup),
        "--identity-file",
        str(backup_context.identity),
    )
    assert result.returncode != 0
    assert not _docker_calls(backup_context)


@pytest.mark.parametrize(
    "failure",
    ["FAKE_BACKEND_RUNNING", "FAKE_OBJECTS", "FAKE_DECRYPT_FAIL"],
)
def test_restore_refuses_unsafe_target_or_invalid_backup(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    backup = backup_context.destination / "database.dump.age"
    backup.write_bytes(b"synthetic-age:synthetic database dump")
    monkeypatch.setenv(failure, "1")
    result = _run(backup_context, "restore-database.sh", *_restore_args(backup_context, backup))
    assert result.returncode != 0
    assert not any("pg_restore" in " ".join(call) for call in _docker_calls(backup_context))


def test_restore_uses_a_single_transaction_without_dropping_existing_data(
    backup_context: BackupContext,
) -> None:
    backup = backup_context.destination / "database.dump.age"
    backup.write_bytes(b"synthetic-age:synthetic database dump")
    result = _run(backup_context, "restore-database.sh", *_restore_args(backup_context, backup))
    assert result.returncode == 0, result.stderr
    restore = next(call for call in _docker_calls(backup_context) if "pg_restore" in " ".join(call))
    command = " ".join(restore)
    assert "--single-transaction" in command
    assert "--exit-on-error" in command
    assert "--clean" not in command
    assert "--create" not in command


def test_restore_failure_requires_inspection(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = backup_context.destination / "database.dump.age"
    backup.write_bytes(b"synthetic-age:synthetic database dump")
    monkeypatch.setenv("FAKE_RESTORE_FAIL", "1")
    result = _run(backup_context, "restore-database.sh", *_restore_args(backup_context, backup))
    assert result.returncode != 0
    assert "inspect the target" in result.stderr
    assert "restore completed" not in result.stdout.lower()
