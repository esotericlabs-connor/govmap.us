import ast
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="requires Linux Bash and GNU tar")

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def test_restore_guide_shell_and_embedded_python_syntax() -> None:
    guide = (_SCRIPTS.parent / "docs" / "backup-service.md").read_text(encoding="utf-8")
    blocks = re.findall(r"^\s*```bash\n(.*?)^\s*```\s*$", guide, re.MULTILINE | re.DOTALL)
    assert blocks
    for block in blocks:
        result = subprocess.run(
            ["bash", "-n"], input=block, capture_output=True, text=True, check=False, timeout=10
        )
        assert result.returncode == 0, result.stderr
    helpers = re.findall(r"<<'PY'\n(.*?)\nPY\n", guide, re.DOTALL)
    assert len(helpers) == 1
    ast.parse(helpers[0])


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
        "backup-database.sh",
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


def _database_backup_args(context: BackupContext) -> tuple[str, ...]:
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


def test_database_backup_selects_resource_and_publishes_encrypted_dump(
    backup_context: BackupContext,
) -> None:
    result = _run(
        backup_context, "backup-database.sh", *_database_backup_args(backup_context)
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
def test_database_backup_fails_closed_without_replacing_prior_backup(
    backup_context: BackupContext,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    value: str,
) -> None:
    previous = backup_context.destination / "previous.dump.age"
    previous.write_bytes(b"previous backup")
    monkeypatch.setenv(environment, value)
    result = _run(
        backup_context, "backup-database.sh", *_database_backup_args(backup_context)
    )
    assert result.returncode != 0
    assert previous.read_bytes() == b"previous backup"
    assert not list(backup_context.destination.glob("govmap-testresource-*.dump.age"))
    assert not list(backup_context.destination.glob(".govmap-db-work-*"))


def test_database_backup_refuses_repository_destination(
    backup_context: BackupContext,
) -> None:
    result = _run(
        backup_context,
        "backup-database.sh",
        "--resource-id",
        "testresource",
        "--destination",
        str(backup_context.repository),
        "--recipients-file",
        str(backup_context.recipients),
    )
    assert result.returncode != 0
    assert not _docker_calls(backup_context)


def test_database_backup_refuses_remote_docker_context(
    backup_context: BackupContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_ENDPOINT", "ssh://example.invalid")
    result = _run(
        backup_context, "backup-database.sh", *_database_backup_args(backup_context)
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


@pytest.mark.parametrize(
    ("config_directory", "config_field"),
    [
        ("deployment-config", "deployment_config"),
        ("previous-config", "previous_config"),
    ],
)
def test_restore_guide_identifies_current_and_earlier_configuration(
    tmp_path: Path, config_directory: str, config_field: str
) -> None:
    bundle = tmp_path / "bundle"
    config = bundle / config_directory
    config.mkdir(parents=True)
    manifest = bundle / "MANIFEST.txt"
    manifest.write_text(
        "created_utc=2026-01-01T00:00:00Z\n"
        "resource_id=testresource\n"
        "postgres_image=postgres:16-alpine\n"
        "alembic_revision=0013\n"
        f"{config_field}=included\n",
        encoding="utf-8",
    )
    guide = (_SCRIPTS.parent / "docs" / "backup-service.md").read_text(encoding="utf-8")
    blocks = [block.split("\n```", 1)[0].strip() for block in guide.split("```bash\n")[1:]]
    manifest_checks = [shlex.split(block) for block in blocks if block.startswith("sudo grep -E ")]
    directory_checks = [
        shlex.split(block)
        for block in blocks
        if block.startswith("sudo find ") and "-name '*-config'" in block
    ]
    assert len(manifest_checks) == len(directory_checks) == 1

    manifest_command = manifest_checks[0]
    manifest_command[-1] = str(manifest)
    result = subprocess.run(
        manifest_command[1:], capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert f"{config_field}=included\n" in result.stdout

    directory_command = directory_checks[0]
    directory_command[2] = str(bundle)
    result = subprocess.run(
        directory_command[1:], capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{config}\n"
