"""Demo persona — typed skeleton for L2-instance flavor strings.

``DemoPersona`` collects per-institution flavor (institution name +
acronym, upstream stakeholders, GL account labels, merchant names,
free-form flavor strings) into one dataclass loaded from the L2 YAML's
``persona:`` block. Every field defaults to the empty tuple so an L2
without a ``persona:`` block loads cleanly — the handbook templates
treat that as "no persona content" and render neutral prose derived
from the L2 primitives instead (account descriptions, role names).

Phase Q.5.e moved the bundled fixture's flavor into its YAML's
``persona:`` block; this module no longer carries institution-specific
strings. See ``tests/test_persona.py`` for the round-trip from YAML
through ``L2Instance.persona`` to the handbook vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GLAccount:
    """One GL account that appears in both the demo seed and the handbook.

    ``code`` is the bare prefix (e.g. ``gl-1010``) that joins to the
    seed account roster; ``name`` is the canonical display name; ``note``
    is a one-line hint surfaced in handbook prose.
    """

    code: str
    name: str
    note: str = ""


@dataclass(frozen=True)
class DemoPersona:
    """Per-institution flavor strings loaded from an L2 ``persona:`` block.

    Each field defaults to an empty tuple — handbook templates check for
    non-empty before rendering persona-rich prose, falling back to
    neutral L2-primitive-derived prose otherwise.

    - ``institution`` — ``(name, acronym)`` tuple, optional ``region``
      and ``legacy_entity`` follow-ons.
    - ``stakeholders`` — flat list of upstream-counterparty display
      strings (``"Federal Reserve Bank"``, ``"the Fed"`` etc.).
    - ``gl_accounts`` — typed GL display labels for the chart-of-accounts
      narrative.
    - ``merchants`` — display names of merchant DDAs the seed plants.
    - ``flavor`` — free-form persona strings (sample customer name,
      region descriptor, legacy-entity callout).
    """

    institution: tuple[str, ...] = field(default_factory=tuple)
    stakeholders: tuple[str, ...] = field(default_factory=tuple)
    gl_accounts: tuple[GLAccount, ...] = field(default_factory=tuple)
    merchants: tuple[str, ...] = field(default_factory=tuple)
    flavor: tuple[str, ...] = field(default_factory=tuple)
