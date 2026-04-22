"""Parity tests between SNB_PERSONA and the shipped mapping.yaml.example.

The mapping file is auto-derived from ``common/persona.SNB_PERSONA``
so a rename in one place doesn't silently de-sync. If this test fails,
the dataclass moved but the YAML wasn't regenerated — the failure
prints the regenerated body so the fix is paste-ready.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quicksight_gen.common import persona as persona_mod
from quicksight_gen.common.persona import (
    SNB_PERSONA,
    derive_mapping_yaml_text,
)


_MAPPING_PATH = (
    Path(persona_mod.__file__).parent.parent
    / "training"
    / "mapping.yaml.example"
)


class TestMappingDerivation:
    def test_shipped_yaml_matches_derived(self):
        shipped = _MAPPING_PATH.read_text(encoding="utf-8")
        derived = derive_mapping_yaml_text()
        if shipped != derived:
            pytest.fail(
                "training/mapping.yaml.example drifted from "
                "common/persona.SNB_PERSONA. Regenerate by running:\n\n"
                "    .venv/bin/python -c 'from pathlib import Path; "
                "from quicksight_gen.common import persona; "
                "from quicksight_gen.common.persona import "
                "derive_mapping_yaml_text; "
                "Path(persona.__file__).parent.parent / \"training\" / "
                "\"mapping.yaml.example\"' "
                "...or update SNB_PERSONA so the derivation matches the "
                "shipped file.\n\nDerived body:\n\n" + derived
            )

    def test_persona_strings_are_non_empty(self):
        # Guard against accidentally landing an empty key in the mapping.
        for s in SNB_PERSONA.institution:
            assert s, "empty institution string"
        for s in SNB_PERSONA.stakeholders:
            assert s, "empty stakeholder string"
        for g in SNB_PERSONA.gl_accounts:
            assert g.code, "GLAccount with empty code"
            assert g.name, f"GLAccount {g.code!r} has empty name"
        for s in SNB_PERSONA.account_labels:
            assert s, "empty account label"
        for s in SNB_PERSONA.merchants:
            assert s, "empty merchant"
        for s in SNB_PERSONA.flavor:
            assert s, "empty flavor term"
