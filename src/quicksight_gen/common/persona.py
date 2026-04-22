"""Demo persona — single source of truth for whitelabel-substitutable strings.

The bundled training handbook, demo generators, and dashboards all
embed Sasquatch National Bank (SNB) flavor strings: the institution
name, stakeholder labels (FRB, processor), GL account codes, named
account labels, merchant names, and one-off flavor terms (location
references, the legacy bank that SNB absorbed). These strings are
listed in ``training/mapping.yaml.example`` so a publishing team can
substitute them for real-program names on the wiki side without
touching this repo.

Without a single source of truth the YAML drifts: a merchant rename
in ``payment_recon/demo_data.py`` silently de-syncs the substitution
template. ``DemoPersona`` is that source of truth; the YAML is
auto-derived from it (see ``derive_mapping_yaml_text``) so a parity
test can fail loudly when the two diverge.

K.2a.5 lands the dataclass + derivation + parity test. The follow-up
work — refactoring the demo generators to read every persona-flavored
literal from this module instead of inlining it — is incremental and
must keep the SHA256 seed-hash assertions green; the substitution
layer rewrites a published copy *after* hash check, never before.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GLAccount:
    """One GL account that appears in both the demo seed and the handbook.

    ``code`` is the bare prefix (e.g. ``gl-1010``) used as a
    substitution key in the mapping file. ``name`` is the canonical
    SNB name. ``note`` lets the YAML carry a one-line hint that helps
    the publishing team pick the real-program analogue (e.g.
    "Open Loop Funds Pool" for ``gl-1010``).
    """

    code: str
    name: str
    note: str = ""


@dataclass(frozen=True)
class DemoPersona:
    """Whitelabel-substitutable strings used by the demo + handbook.

    Each field is an ordered tuple so derivation is deterministic.
    Tests can also iterate ``GLAccount`` entries to check that demo
    generators reference every persona-listed code.
    """

    institution: tuple[str, ...]
    stakeholders: tuple[str, ...]
    gl_accounts: tuple[GLAccount, ...]
    account_labels: tuple[str, ...]
    merchants: tuple[str, ...]
    flavor: tuple[str, ...]
    intentional_non_mappings: tuple[str, ...] = field(default_factory=tuple)


# Sasquatch National Bank — the single instance used by demo + handbook.
# Mirrors the contents of ``training/mapping.yaml.example`` exactly;
# the parity test in ``tests/test_persona.py`` fails if they diverge.
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
    account_labels=(
        "Cash & Due From FRB",
        "ACH Origination Settlement",
        "Card Acquiring Settlement",
        "Internal Transfer Suspense",
        "Cash Concentration Master",
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
    intentional_non_mappings=(
        "double-entry", "open loop", "closed loop", "sweep", "net-settle",
        "escrow", "vouchering", "aging bucket", "drift", "suspense",
        "DDA", "ZBA",
    ),
)


_HEADER = """\
# mapping.yaml — SNB source string → real-program string
#
# PRIVATE TEMPLATE. This file is not published.
#
# The authoritative mapping is hand-maintained on the GitLab-wiki side
# (never in this repo) so that real-program names never enter source
# control here. This file is a *template* and *checklist*: it enumerates
# the SNB strings that appear in handbook/ and need substitution. Values
# are intentionally blank.
#
# To use: copy the structure to your wiki-side mapping file, fill in the
# real-program values there, and feed that file (not this one) to the
# publish script.
#
# See translation-notes.md at the repo root for the rationale behind
# each mapping.
#
# AUTO-DERIVED FROM common/persona.py — do not edit by hand. Add new
# strings to ``SNB_PERSONA`` and re-run the parity test (which prints
# the regenerated YAML body when it diverges).
"""


def _yaml_kv(key: str, value: str = "", note: str = "") -> str:
    """One YAML key-value line with optional inline ``# note`` comment."""
    base = f'  "{key}": "{value}"' if value else f'  "{key}": ""'
    if note:
        return f"{base}    # {note}"
    return base


def derive_mapping_yaml_text(persona: DemoPersona = SNB_PERSONA) -> str:
    """Render ``persona`` as the canonical ``mapping.yaml.example`` body.

    Section order and comment phrasing match the hand-written template
    so the parity test can do a byte-equal comparison against the
    shipped file.
    """
    sections: list[str] = [_HEADER]

    sections.append("\n# --- Institution identity ---\ninstitution:")
    sections.extend(_yaml_kv(s) for s in persona.institution)

    sections.append(
        "\n# --- Stakeholders / counterparties mentioned in handbook text ---\n"
        "stakeholders:"
    )
    sections.extend(_yaml_kv(s) for s in persona.stakeholders)

    sections.append(
        "\n# --- GL account codes appearing in concept pages and scenarios ---\n"
        "# Format in source: `gl-XXXX`. Decide on the wiki side whether these\n"
        "# become real account numbers, friendly names, or a mix.\ngl_accounts:"
    )
    sections.extend(_yaml_kv(g.code, note=g.note) for g in persona.gl_accounts)

    sections.append(
        "\n# --- Named account labels used in scenarios ---\naccount_labels:"
    )
    sections.extend(_yaml_kv(s) for s in persona.account_labels)

    sections.append(
        "\n# --- Merchants that appear in scenarios 1 and 2 ---\n"
        "# Replace with real-program merchant names, or with merchant *types*\n"
        '# (e.g., "Type A high-volume merchant") if the real roster rotates.\n'
        "merchants:"
    )
    sections.extend(_yaml_kv(s) for s in persona.merchants)

    sections.append(
        "\n# --- Demo-only flavor to strip (replace with empty string or neutral) ---\n"
        "flavor:"
    )
    sections.extend(_yaml_kv(s) for s in persona.flavor)

    sections.append(
        "\n# --- Intentional non-mappings ---\n"
        "# Industry-standard vocabulary stays as-is. Do not substitute:\n"
        f"#   {', '.join(persona.intentional_non_mappings[:5])},\n"
        f"#   {', '.join(persona.intentional_non_mappings[5:])}.\n"
        "# These terms are the same on both sides and are load-bearing for\n"
        "# the training.\n"
    )

    return "\n".join(sections)
