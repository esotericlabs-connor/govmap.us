"""Parsers for untrusted upstream XML and YAML documents.

No source GovMap pulls declares XML entities or uses YAML aliases (checked
against the live House Clerk, Senate LIS and congress-legislators files), so
both are refused outright instead of relying solely on parser expansion limits:
an entity or alias bomb is a few hundred bytes that passes any byte cap and
expands only after parsing, during traversal or serialization.
"""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET
from xml.parsers import expat

import yaml
from yaml.composer import ComposerError


def _refuse_entity_declarations(body: bytes, label: str) -> None:
    def entity_declared(*_args: object) -> None:
        raise ValueError(f"{label}: XML entity declarations are not accepted")

    # A separate expat pass, because ElementTree's C parser exposes no hook for
    # entity declarations. Malformed input is left for ElementTree to report
    # as its usual ParseError.
    scanner = expat.ParserCreate()
    scanner.EntityDeclHandler = entity_declared
    try:
        scanner.Parse(body, True)
    except expat.ExpatError:
        pass


def parse_xml(body: bytes, *, label: str) -> ET.Element:
    """Parse an XML document that declares no entities."""
    _refuse_entity_declarations(body, label)
    return ET.fromstring(body)


class _NoAliasSafeLoader(yaml.SafeLoader):
    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise ComposerError(
                None, None, "YAML aliases are not accepted", event.start_mark
            )
        return super().compose_node(parent, index)


def load_yaml(body: bytes) -> Any:
    """``yaml.safe_load`` that also refuses aliases."""
    return yaml.load(body, Loader=_NoAliasSafeLoader)
