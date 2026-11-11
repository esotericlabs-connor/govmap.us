"""requirements.in holds the hand-edited top-level pins; requirements.txt is
the compiled, hash-locked install set the image and CI use. A pin bumped in one
file but not the other would ship a version nobody reviewed or audited."""

import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;\\]+)")


def _pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _PIN.match(line.strip())
        if match:
            name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
            pins[name] = match.group(2)
    return pins


def test_every_top_level_pin_matches_the_lock() -> None:
    declared = _pins(_BACKEND / "requirements.in")
    locked = _pins(_BACKEND / "requirements.txt")
    assert declared, "requirements.in has no pins"
    mismatched = {
        name: (version, locked.get(name))
        for name, version in declared.items()
        if locked.get(name) != version
    }
    assert mismatched == {}


def test_every_locked_package_carries_a_hash() -> None:
    # The image installs with --require-hashes; a plain copy of requirements.in
    # committed over the lock should fail here, with the package named, before
    # it fails the image build.
    text = (_BACKEND / "requirements.txt").read_text(encoding="utf-8")
    entries = [
        " ".join(part.strip() for part in entry.split("\\\n"))
        for entry in re.split(r"(?<!\\)\n", text)
        if entry.strip() and not entry.lstrip().startswith("#")
    ]
    assert entries, "requirements.txt has no entries"
    unhashed = [
        entry.split()[0]
        for entry in entries
        if not re.search(r"--hash=sha256:[0-9a-f]{64}\b", entry)
    ]
    assert unhashed == []
