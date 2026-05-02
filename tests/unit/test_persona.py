"""Sanity tests for the L2-loaded persona block.

Until Q.5.e the SNB persona content lived in a hardcoded
``SNB_PERSONA`` constant on ``common/persona.py``; it now lives in
``tests/l2/sasquatch_pr.yaml``'s ``persona:`` block and gets loaded
into ``L2Instance.persona`` by ``loader.py``. These tests exercise
both the loader (``persona`` parses to the right shape against the
bundled fixture) and the dataclass (every persona string non-empty).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quicksight_gen.common.l2.loader import load_instance
from quicksight_gen.common.persona import DemoPersona


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SASQUATCH_PR = _REPO_ROOT / "tests" / "l2" / "sasquatch_pr.yaml"
_SPEC_EXAMPLE = _REPO_ROOT / "tests" / "l2" / "spec_example.yaml"


@pytest.fixture(scope="module")
def sasquatch_persona() -> DemoPersona:
    inst = load_instance(_SASQUATCH_PR)
    assert inst.persona is not None, (
        "sasquatch_pr.yaml must carry a persona: block (Q.5.e contract)"
    )
    return inst.persona


class TestSasquatchPersonaNonEmpty:
    def test_institution_strings_non_empty(
        self, sasquatch_persona: DemoPersona
    ) -> None:
        for s in sasquatch_persona.institution:
            assert s, "empty institution string"

    def test_stakeholder_strings_non_empty(
        self, sasquatch_persona: DemoPersona
    ) -> None:
        for s in sasquatch_persona.stakeholders:
            assert s, "empty stakeholder string"

    def test_gl_accounts_have_code_and_name(
        self, sasquatch_persona: DemoPersona
    ) -> None:
        for g in sasquatch_persona.gl_accounts:
            assert g.code, "GLAccount with empty code"
            assert g.name, f"GLAccount {g.code!r} has empty name"

    def test_merchants_non_empty(
        self, sasquatch_persona: DemoPersona
    ) -> None:
        for s in sasquatch_persona.merchants:
            assert s, "empty merchant"

    def test_flavor_strings_non_empty(
        self, sasquatch_persona: DemoPersona
    ) -> None:
        for s in sasquatch_persona.flavor:
            assert s, "empty flavor term"


class TestPersonaOptional:
    def test_spec_example_has_no_persona_block(self) -> None:
        """spec_example.yaml carries no persona block — loader returns None."""
        inst = load_instance(_SPEC_EXAMPLE)
        assert inst.persona is None

    def test_demo_persona_default_is_all_empty(self) -> None:
        """A bare DemoPersona() instantiates with empty-tuple fields."""
        p = DemoPersona()
        assert p.institution == ()
        assert p.stakeholders == ()
        assert p.gl_accounts == ()
        assert p.merchants == ()
        assert p.flavor == ()
