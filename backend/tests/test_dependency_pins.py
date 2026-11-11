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
