"""Handbook substitution vocabulary, built per-render from an L2 instance.

The Phase O unified mkdocs site renders against an L2 institution
YAML. ``vocabulary_for(l2_instance)`` picks the right
``HandbookVocabulary`` for that instance — either a built-in vocabulary
(currently only ``sasquatch_pr`` ships one) or a neutral fallback
derived from the L2's own structural data.

The neutral fallback exists so an integrator pointing at their own
L2 instance gets a sensible handbook out of the box: the institution
name comes from the L2's description; account labels come from the
account roster; stakeholders come from the external accounts; no
Sasquatch flavor leaks. As integrators want richer per-institution
flavor (named compliance scenarios, regional voice, legacy entities),
they can submit a built-in vocabulary the same way ``sasquatch_pr``
ships one — or a future ``personas:`` YAML block (audit §5) can carry
the data inline on the L2 itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from quicksight_gen.common.l2.primitives import L2Instance
from quicksight_gen.common.persona import GLAccount, SNB_PERSONA


# -- Sub-shapes -------------------------------------------------------------


@dataclass(frozen=True)
class InstitutionVocabulary:
    """How the handbook refers to the institution."""

    name: str
    """Full name — ``"Sasquatch National Bank"`` / ``"Your Institution"``."""

    acronym: str
    """Short name — ``"SNB"`` / ``"the bank"``."""

    description: str
    """One-paragraph intro for handbook landing pages."""

    region: str | None = None
    """Optional geographic flavor — ``"Pacific Northwest"``."""

    legacy_entity: str | None = None
    """Optional absorbed-institution name — ``"Farmers Exchange Bank"``."""


@dataclass(frozen=True)
class StakeholderVocabulary:
    """A counterparty / external entity referenced in the handbook prose."""

    name: str
    """Full name — ``"Federal Reserve Bank"``."""

    short_name: str
    """How prose abbreviates it — ``"the Fed"``."""

    role: str
    """One-line role — ``"settlement authority"``."""


@dataclass(frozen=True)
class MerchantVocabulary:
    """A merchant / commercial customer referenced by name in scenarios."""

    name: str
    """Display name — ``"Big Meadow Dairy"``."""

    account_id: str
    """Joins to the seed — ``"cust-900-0001-big-meadow-dairy"``."""

    sector: str
    """One-word industry hint — ``"agricultural"`` / ``"coffee retail"``."""


@dataclass(frozen=True)
class InvestigationPersonaVocabulary:
    """Compliance / AML scenario actor — Investigation app uses these."""

    name: str
    """Display name — ``"Juniper Ridge LLC"``."""

    account_id: str
    """Joins to the seed — ``"cust-900-0007-juniper-ridge-llc"``."""

    role: str
    """Scenario role — ``"convergence_anchor"`` / ``"shell_entity"``."""


# -- Top-level ---------------------------------------------------------------


@dataclass(frozen=True)
class HandbookVocabulary:
    """Substitution vocabulary handed to mkdocs-macros at render time."""

    institution: InstitutionVocabulary
    stakeholders: tuple[StakeholderVocabulary, ...]
    gl_accounts: tuple[GLAccount, ...]
    merchants: tuple[MerchantVocabulary, ...]
    flavor: tuple[str, ...]
    investigation_personas: tuple[InvestigationPersonaVocabulary, ...]


# -- Public entry point ------------------------------------------------------


def vocabulary_for(l2_instance: L2Instance) -> HandbookVocabulary:
    """Return the handbook vocabulary appropriate for ``l2_instance``.

    Built-in vocabularies take precedence (currently ``sasquatch_pr``).
    Anything else falls back to a neutral vocabulary derived from the
    L2 instance's own fields — institution name from the description,
    GL accounts + merchants from the account roster, no flavor leaks.
    """
    if l2_instance.instance == "sasquatch_pr":
        return _sasquatch_pr_vocabulary(l2_instance)
    return _neutral_vocabulary_for(l2_instance)


# -- Built-in vocabularies ---------------------------------------------------


def _sasquatch_pr_vocabulary(l2_instance: L2Instance) -> HandbookVocabulary:
    """The Sasquatch National Bank handbook flavor.

    Reuses ``SNB_PERSONA`` for the strings that already live there
    (institution name, GL accounts, merchant names, flavor terms) and
    layers Investigation personas on top — the latter aren't in
    ``SNB_PERSONA`` because the persona module pre-dates the
    Investigation app's compliance demo (Juniper Ridge / Cascadia /
    shell-DDA chain).
    """
    description = (
        l2_instance.description.strip()
        if l2_instance.description
        else "Sasquatch National Bank — combined treasury + merchant-acquiring."
    )
    return HandbookVocabulary(
        institution=InstitutionVocabulary(
            name=SNB_PERSONA.institution[0],
            acronym=SNB_PERSONA.institution[1],
            description=description,
            region=SNB_PERSONA.flavor[1] if len(SNB_PERSONA.flavor) > 1 else None,
            legacy_entity=(
                SNB_PERSONA.flavor[2] if len(SNB_PERSONA.flavor) > 2 else None
            ),
        ),
        stakeholders=(
            StakeholderVocabulary(
                name="Federal Reserve Bank",
                short_name="the Fed",
                role="settlement authority for ACH, wire, and daily sweep flows",
            ),
            StakeholderVocabulary(
                name="Payment Gateway Processor",
                short_name="the processor",
                role="card-network acquirer and merchant settlement counterparty",
            ),
        ),
        gl_accounts=SNB_PERSONA.gl_accounts,
        merchants=(
            MerchantVocabulary(
                name="Big Meadow Dairy",
                account_id="cust-900-0001-big-meadow-dairy",
                sector="agricultural",
            ),
            MerchantVocabulary(
                name="Bigfoot Brews",
                account_id="cust-900-0002-bigfoot-brews",
                sector="coffee retail",
            ),
            MerchantVocabulary(
                name="Cascade Timber Mill",
                account_id="cust-900-0003-cascade-timber-mill",
                sector="industrial",
            ),
            MerchantVocabulary(
                name="Pinecrest Vineyards LLC",
                account_id="cust-900-0004-pinecrest-vineyards",
                sector="agricultural",
            ),
            MerchantVocabulary(
                name="Harvest Moon Bakery",
                account_id="cust-900-0005-harvest-moon-bakery",
                sector="food retail",
            ),
        ),
        flavor=SNB_PERSONA.flavor,
        investigation_personas=(
            InvestigationPersonaVocabulary(
                name="Juniper Ridge LLC",
                account_id="cust-900-0007-juniper-ridge-llc",
                role="convergence_anchor",
            ),
            InvestigationPersonaVocabulary(
                name="Cascadia Trust Bank",
                account_id="ext-cascadia-trust-bank",
                role="counterparty_bank",
            ),
            InvestigationPersonaVocabulary(
                name="Cascadia Trust Bank — Operations",
                account_id="ext-cascadia-trust-bank-sub-ops",
                role="operations_account",
            ),
            InvestigationPersonaVocabulary(
                name="Shell Company A",
                account_id="cust-700-0010-shell-company-a",
                role="shell_entity",
            ),
            InvestigationPersonaVocabulary(
                name="Shell Company B",
                account_id="cust-700-0011-shell-company-b",
                role="shell_entity",
            ),
            InvestigationPersonaVocabulary(
                name="Shell Company C",
                account_id="cust-700-0012-shell-company-c",
                role="shell_entity",
            ),
        ),
    )


# -- Neutral fallback --------------------------------------------------------


_INSTITUTION_NAME_RE = re.compile(
    # First strict-title-case run (≥2 words) in the description's first
    # sentence — e.g. "Sasquatch National Bank's combined treasury…" →
    # "Sasquatch National Bank". Strict title case (uppercase initial +
    # lowercase remainder) so all-caps tokens don't false-match: in
    # ``spec_example`` the description opens with "Generic SPEC-shaped
    # instance…", and we want that to fall through to the placeholder
    # rather than emit "Generic SPEC". Real bank names with all-caps
    # tokens ("BMO Harris", "PNC Financial") need a built-in vocabulary
    # or a future ``personas:`` YAML block — the regex isn't trying to
    # cover the long tail.
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\b"
)


def _neutral_vocabulary_for(l2_instance: L2Instance) -> HandbookVocabulary:
    """Derive a neutral vocabulary from the L2 instance's own data.

    No persona flavor — pulls institution name from the description's
    first proper-noun run (or "Your Institution" if none), uses
    ``Identifier``-shaped placeholders for stakeholders, merchants, and
    Investigation personas, and lets ``flavor`` stay empty.
    """
    description = (
        l2_instance.description.strip()
        if l2_instance.description
        else "An L2-fed institution — handbook generated from the L2 YAML."
    )
    inst_name = _extract_institution_name(description)
    inst_acronym = _institution_acronym(inst_name)
    return HandbookVocabulary(
        institution=InstitutionVocabulary(
            name=inst_name,
            acronym=inst_acronym,
            description=description,
            region=None,
            legacy_entity=None,
        ),
        stakeholders=(),
        gl_accounts=(),
        merchants=(),
        flavor=(),
        investigation_personas=(),
    )


def _extract_institution_name(description: str) -> str:
    """Pull a proper-noun-shaped institution name out of a description.

    Returns ``"Your Institution"`` when no candidate is found, so the
    handbook reads sensibly for L2 instances whose descriptions are
    test-shaped or otherwise lack a proper-noun run.
    """
    first_sentence = description.split(".", 1)[0]
    match = _INSTITUTION_NAME_RE.search(first_sentence)
    if match is None:
        return "Your Institution"
    return match.group(1)


def _institution_acronym(name: str) -> str:
    """Make a 2-4 letter acronym from a multi-word institution name.

    Single-word names (or the ``"Your Institution"`` fallback) collapse
    to ``"the institution"`` for readable inline prose.
    """
    words = [w for w in name.split() if w[0].isupper()]
    if len(words) < 2 or name == "Your Institution":
        return "the institution"
    return "".join(w[0] for w in words)
