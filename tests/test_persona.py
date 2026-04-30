"""Sanity tests for the SNB_PERSONA dataclass.

The legacy ``mapping.yaml.example`` parity test was dropped in O.1.l
when the training/ kit + the substitution machinery were removed —
docs now render via mkdocs-macros against the L2-fed
``HandbookVocabulary`` (see ``tests/test_handbook_vocabulary.py``).
This file keeps the smaller "every persona string is non-empty"
guard so a typo in ``SNB_PERSONA`` surfaces loudly.
"""

from __future__ import annotations

from quicksight_gen.common.persona import SNB_PERSONA


class TestSNBPersonaNonEmpty:
    def test_institution_strings_non_empty(self):
        for s in SNB_PERSONA.institution:
            assert s, "empty institution string"

    def test_stakeholder_strings_non_empty(self):
        for s in SNB_PERSONA.stakeholders:
            assert s, "empty stakeholder string"

    def test_gl_accounts_have_code_and_name(self):
        for g in SNB_PERSONA.gl_accounts:
            assert g.code, "GLAccount with empty code"
            assert g.name, f"GLAccount {g.code!r} has empty name"

    def test_merchants_non_empty(self):
        for s in SNB_PERSONA.merchants:
            assert s, "empty merchant"

    def test_flavor_strings_non_empty(self):
        for s in SNB_PERSONA.flavor:
            assert s, "empty flavor term"
