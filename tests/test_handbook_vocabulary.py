"""Unit tests for ``common.handbook.vocabulary``.

Covers all three branches: built-in (``sasquatch_pr``), neutral
fallback derived from a real L2 (``spec_example``), and synthetic
minimal instance (no description, empty fields).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quicksight_gen.common.handbook import (
    HandbookVocabulary,
    InvestigationPersonaVocabulary,
    MerchantVocabulary,
    vocabulary_for,
)
from quicksight_gen.common.handbook.vocabulary import (
    _extract_institution_name,
    _institution_acronym,
)
from quicksight_gen.common.l2.loader import load_instance
from quicksight_gen.common.l2.primitives import Identifier, L2Instance


_FIXTURES = Path(__file__).parent / "l2"


# -- Helpers -----------------------------------------------------------------


def _load(name: str) -> L2Instance:
    return load_instance(_FIXTURES / f"{name}.yaml")


def _minimal_instance(
    *, instance: str = "acme_treasury", description: str | None = None
) -> L2Instance:
    """Empty-tuples-everywhere L2Instance for the synthetic-minimal test."""
    return L2Instance(
        instance=Identifier(instance),
        accounts=(),
        account_templates=(),
        rails=(),
        transfer_templates=(),
        chains=(),
        limit_schedules=(),
        description=description,
    )


# -- Built-in: sasquatch_pr --------------------------------------------------


class TestSasquatchPRVocabulary:
    def test_picks_snb_branch(self):
        vocab = vocabulary_for(_load("sasquatch_pr"))
        assert vocab.institution.name == "Sasquatch National Bank"
        assert vocab.institution.acronym == "SNB"

    def test_carries_region_and_legacy_entity(self):
        vocab = vocabulary_for(_load("sasquatch_pr"))
        assert vocab.institution.region == "Pacific Northwest"
        assert vocab.institution.legacy_entity == "Farmers Exchange Bank"

    def test_description_pulled_from_l2(self):
        l2 = _load("sasquatch_pr")
        vocab = vocabulary_for(l2)
        # The description is the L2's description, stripped.
        assert vocab.institution.description.startswith(
            "Sasquatch National Bank's combined treasury"
        )
        assert vocab.institution.description == (
            l2.description.strip() if l2.description else ""
        )

    def test_stakeholders_present(self):
        vocab = vocabulary_for(_load("sasquatch_pr"))
        names = {s.name for s in vocab.stakeholders}
        assert "Federal Reserve Bank" in names
        assert "Payment Gateway Processor" in names

    def test_gl_accounts_pulled_from_snb_persona(self):
        vocab = vocabulary_for(_load("sasquatch_pr"))
        codes = {g.code for g in vocab.gl_accounts}
        # Sample a few codes that SNB_PERSONA carries.
        assert {"gl-1010", "gl-1810", "gl-1815"}.issubset(codes)

    def test_merchants_present_with_account_ids(self):
        vocab = vocabulary_for(_load("sasquatch_pr"))
        assert len(vocab.merchants) >= 5
        for m in vocab.merchants:
            assert isinstance(m, MerchantVocabulary)
            assert m.account_id.startswith("cust-900-")
            assert m.sector  # non-empty

    def test_investigation_personas_cover_demo_actors(self):
        vocab = vocabulary_for(_load("sasquatch_pr"))
        names = {p.name for p in vocab.investigation_personas}
        assert "Juniper Ridge LLC" in names
        assert "Cascadia Trust Bank" in names
        # All three shell entities for the layering chain.
        for letter in ("A", "B", "C"):
            assert f"Shell Company {letter}" in names

    def test_investigation_personas_carry_seed_account_ids(self):
        vocab = vocabulary_for(_load("sasquatch_pr"))
        ids = {p.account_id for p in vocab.investigation_personas}
        assert "cust-900-0007-juniper-ridge-llc" in ids
        assert "ext-cascadia-trust-bank" in ids
        assert "cust-700-0010-shell-company-a" in ids


# -- Neutral fallback: spec_example -----------------------------------------


class TestSpecExampleNeutralFallback:
    def test_picks_neutral_branch(self):
        vocab = vocabulary_for(_load("spec_example"))
        # spec_example's description opens with "Generic SPEC-shaped
        # instance…" — no proper-noun run, so we get the placeholder.
        assert vocab.institution.name == "Your Institution"
        assert vocab.institution.acronym == "the institution"

    def test_no_persona_leakage(self):
        vocab = vocabulary_for(_load("spec_example"))
        # Hard contract — the audit's central O.0 finding is "zero
        # Sasquatch / Bigfoot / SNB / FRB strings in spec_example
        # output". The vocabulary is the substitution surface that has
        # to enforce that.
        for forbidden in ("Sasquatch", "Bigfoot", "SNB", "Federal Reserve"):
            assert forbidden not in vocab.institution.name
            assert forbidden not in vocab.institution.description
            for s in vocab.stakeholders:
                assert forbidden not in s.name
            for m in vocab.merchants:
                assert forbidden not in m.name
            for p in vocab.investigation_personas:
                assert forbidden not in p.name

    def test_neutral_branch_has_empty_persona_tuples(self):
        vocab = vocabulary_for(_load("spec_example"))
        assert vocab.stakeholders == ()
        assert vocab.merchants == ()
        assert vocab.investigation_personas == ()
        assert vocab.flavor == ()


# -- Synthetic minimal: empty-everything L2 ---------------------------------


class TestSyntheticMinimalInstance:
    def test_no_description_uses_default_phrase(self):
        vocab = vocabulary_for(_minimal_instance(description=None))
        assert "L2-fed institution" in vocab.institution.description
        assert vocab.institution.name == "Your Institution"

    def test_proper_noun_description_extracts_name(self):
        vocab = vocabulary_for(
            _minimal_instance(
                description=(
                    "Acme Treasury Bank serves a small community of municipal "
                    "treasurers with internal liquidity sweeps."
                )
            )
        )
        assert vocab.institution.name == "Acme Treasury Bank"
        assert vocab.institution.acronym == "ATB"

    def test_minimal_instance_returns_handbook_vocabulary_type(self):
        vocab = vocabulary_for(_minimal_instance())
        assert isinstance(vocab, HandbookVocabulary)


# -- Helper coverage ---------------------------------------------------------


class TestExtractInstitutionName:
    def test_pulls_first_proper_noun_run(self):
        assert (
            _extract_institution_name("First National Trust serves Acme.")
            == "First National Trust"
        )

    def test_handles_apostrophe_after_name(self):
        # "Sasquatch National Bank's combined treasury…" — the apostrophe
        # ends the proper-noun run cleanly.
        assert (
            _extract_institution_name(
                "Sasquatch National Bank's combined treasury and merchant view."
            )
            == "Sasquatch National Bank"
        )

    def test_no_proper_noun_falls_back_to_placeholder(self):
        assert (
            _extract_institution_name("a generic test instance for cleanliness.")
            == "Your Institution"
        )

    def test_capped_at_five_words(self):
        # Don't grab the entire sentence even when it's all capitalized.
        result = _extract_institution_name(
            "First National Bank Of The Pacific Northwest Region"
        )
        # The regex caps at 5 capitalized tokens (1 + {1,4}).
        assert len(result.split()) <= 5


class TestInstitutionAcronym:
    def test_multi_word_makes_initials(self):
        assert _institution_acronym("First National Bank") == "FNB"
        assert _institution_acronym("Sasquatch National Bank") == "SNB"

    def test_single_word_falls_back_to_phrase(self):
        assert _institution_acronym("Acme") == "the institution"

    def test_placeholder_falls_back_to_phrase(self):
        assert _institution_acronym("Your Institution") == "the institution"


# -- L2 instance dispatcher --------------------------------------------------


class TestVocabularyForDispatch:
    def test_returns_handbook_vocabulary(self):
        for name in ("sasquatch_pr", "spec_example"):
            vocab = vocabulary_for(_load(name))
            assert isinstance(vocab, HandbookVocabulary)

    @pytest.mark.parametrize(
        "instance_name", ["acme_treasury", "first_national", "anything_else"]
    )
    def test_unknown_instance_uses_neutral_branch(self, instance_name: str):
        # Any non-sasquatch_pr instance routes to the neutral fallback —
        # zero persona leakage by construction.
        vocab = vocabulary_for(_minimal_instance(instance=instance_name))
        assert vocab.stakeholders == ()
        assert vocab.merchants == ()
        assert vocab.investigation_personas == ()
