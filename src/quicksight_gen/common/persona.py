"""Demo persona — single source of truth for Sasquatch flavor strings.

The bundled demo data, dashboards, and (until O.1.l) the training
handbook all embed Sasquatch National Bank flavor: institution name,
stakeholder labels (FRB, processor), GL account codes, named account
labels, merchant names. ``DemoPersona`` collects them so the demo
generators have one place to read each persona-flavored literal.

Phase O.1.b layered ``HandbookVocabulary`` on top of this dataclass —
the docs render now substitutes via Jinja templates rather than the
post-render string-replace machinery the original ``training/`` kit
shipped. ``SNB_PERSONA`` stays around because the demo seed plants
SNB-flavored row values that show up in screenshots / scenario
walks; the handbook templates pull the same strings via
``vocabulary_for(l2_instance)`` for the sasquatch_pr cut.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GLAccount:
    """One GL account that appears in both the demo seed and the handbook.

    ``code`` is the bare prefix (e.g. ``gl-1010``) that joins to the
    seed account roster; ``name`` is the canonical SNB display name;
    ``note`` is a one-line hint surfaced in handbook prose.
    """

    code: str
    name: str
    note: str = ""


@dataclass(frozen=True)
class DemoPersona:
    """Sasquatch flavor strings used by the demo + handbook vocabulary."""

    institution: tuple[str, ...]
    stakeholders: tuple[str, ...]
    gl_accounts: tuple[GLAccount, ...]
    merchants: tuple[str, ...]
    flavor: tuple[str, ...]


SNB_PERSONA = DemoPersona(
    institution=(
        "Sasquatch National Bank",
        "SNB",
    ),
    stakeholders=(
        "Federal Reserve Bank",
        "Fed",
        "Payment Gateway Processor",
    ),
    gl_accounts=(
        GLAccount("gl-1010", "Cash & Due From FRB",
                  "Cash & Due From FRB → (e.g., Open Loop Funds Pool)"),
        GLAccount("gl-1810", "ACH Origination Settlement",
                  "ACH Origination Settlement → (e.g., Sweep Account for ACH)"),
        GLAccount("gl-1815", "Card Acquiring Settlement",
                  "Card Acquiring Settlement"),
        GLAccount("gl-1830", "Internal Transfer Suspense",
                  "Internal Transfer Suspense → (e.g., Open Loop Escrow)"),
        GLAccount("gl-1850", "Cash Concentration Master",
                  "Cash Concentration Master (no real analogue)"),
    ),
    merchants=(
        "Big Meadow Dairy",
        "Bigfoot Brews",
        "Cascade Timber Mill",
        "Pinecrest Vineyards LLC",
        "Harvest Moon Bakery",
    ),
    flavor=(
        "Margaret Hollowcreek",
        "Pacific Northwest",
        "Farmers Exchange Bank",
    ),
)
