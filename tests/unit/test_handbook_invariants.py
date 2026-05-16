"""AA.C.2 — L1 invariants parser unit tests.

Two layers:

- ``test_parse_l1_invariants_*`` — synthetic markdown snippets exercise
  every parser branch (numbered SHOULD heading, ``(M.2b.X)`` tag
  trimming, Supersession Audit ``##`` shape, Jinja stripping, columns
  extraction, multi-section walk).
- ``test_bundled_invariants_*`` — pin the parse against the real
  bundled doc so a future doc edit doesn't silently break the
  dashboard panel feed.
"""

from __future__ import annotations

from quicksight_gen.common.handbook.invariants import (
    INVARIANT_KIND_TO_SHEET,
    InvariantSection,
    load_bundled_invariants,
    parse_l1_invariants,
)


# -- Synthetic-markdown parser tests ----------------------------------------


def test_parse_l1_invariants_single_numbered_section() -> None:
    md = """\
## The seven L1 SHOULD-constraints

### 1. `{{ l2_instance_name }}_drift` — Sub-ledger drift

> For every CurrentStoredBalance where `Account.Scope = Internal`
> and `¬IsParent(Account)`,
> `Drift(Account, BusinessDay)` SHOULD equal 0.

Each leaf-account day where the stored balance disagrees.

**Columns:** `account_id`, `account_name`, `drift`.
"""
    sections = parse_l1_invariants(md)
    assert set(sections.keys()) == {"drift"}
    drift = sections["drift"]
    assert isinstance(drift, InvariantSection)
    assert drift.kind == "drift"
    assert drift.title == "Sub-ledger drift"
    assert "SHOULD equal 0" in drift.short_statement
    assert "stored balance disagrees" in drift.body
    assert drift.columns == ("account_id", "account_name", "drift")


def test_parse_l1_invariants_trims_phase_tag_from_title() -> None:
    md = """\
### 6. `{{ l2_instance_name }}_stuck_pending` — Per-rail pending aging (M.2b.8)

> For every Rail with `max_pending_age` set, every Transaction
> on that rail SHOULD transition.
"""
    sections = parse_l1_invariants(md)
    # The trailing ``(M.2b.8)`` is a phase reference — strip it so the
    # panel title doesn't bleed implementation history into operator UI.
    assert sections["stuck_pending"].title == "Per-rail pending aging"


def test_parse_l1_invariants_strips_jinja_by_default() -> None:
    md = """\
### 3. `{{ l2_instance_name }}_overdraft` — Non-negative balance

> For every CurrentStoredBalance, `money` SHOULD be ≥ 0.

External counterparties are excluded.

{% if vocab.fixture_name == "sasquatch_pr" %}
**the matview should surface:** `sasquatch-sips -$1500` planted.
{% endif %}
"""
    sections = parse_l1_invariants(md)
    body = sections["overdraft"].body
    assert "External counterparties are excluded." in body
    assert "sasquatch-sips" not in body
    assert "{% if" not in body
    assert "{% endif" not in body


def test_parse_l1_invariants_preserves_jinja_when_disabled() -> None:
    md = """\
### 3. `{{ l2_instance_name }}_overdraft` — Non-negative balance

> For every CurrentStoredBalance, `money` SHOULD be ≥ 0.

{% if vocab.fixture_name == "sasquatch_pr" %}
**should surface:** planted.
{% endif %}
"""
    sections = parse_l1_invariants(md, strip_jinja=False)
    # ``strip_jinja=False`` is the escape hatch for re-running through
    # the mkdocs pipeline — the worked-example block stays intact.
    assert "{% if" in sections["overdraft"].body
    assert "planted" in sections["overdraft"].body


def test_parse_l1_invariants_supersession_audit_section() -> None:
    md = """\
## Diagnostic surface — Supersession Audit

`{{ l2_instance_name }}_supersession_*` is **not** a SHOULD-constraint.
Reads from BASE tables.
"""
    sections = parse_l1_invariants(md)
    assert "supersession_audit" in sections
    sup = sections["supersession_audit"]
    assert sup.title == "Supersession Audit"
    assert sup.short_statement == ""  # Descriptive section, no blockquote.
    assert "not** a SHOULD-constraint" in sup.body
    assert sup.columns == ()


def test_parse_l1_invariants_walks_multiple_sections() -> None:
    md = """\
### 1. `{{ l2_instance_name }}_drift` — Sub-ledger drift

> Drift SHOULD equal 0.

Drift body.

### 5. `{{ l2_instance_name }}_limit_breach` — Outbound flow cap

> Cap SHOULD hold.

Limit breach body.

## Diagnostic surface — Supersession Audit

Diagnostic body.
"""
    sections = parse_l1_invariants(md)
    assert set(sections.keys()) == {"drift", "limit_breach", "supersession_audit"}
    assert sections["drift"].body.startswith("Drift body.")
    assert sections["limit_breach"].body.startswith("Limit breach body.")
    assert sections["supersession_audit"].body.startswith("Diagnostic body.")


def test_parse_l1_invariants_ignores_non_invariant_headings() -> None:
    # Other H2 headings (e.g., "## Refresh + extend contracts") must
    # NOT show up as parsed sections.
    md = """\
## How the views are layered

Prose about layering.

### 1. `{{ l2_instance_name }}_drift` — Sub-ledger drift

> Drift SHOULD equal 0.

Drift body.

## Refresh + extend contracts

Refresh prose.
"""
    sections = parse_l1_invariants(md)
    assert set(sections.keys()) == {"drift"}


def test_parse_l1_invariants_columns_block_wraps_across_lines() -> None:
    # The real doc wraps the **Columns:** line across 3-4 physical
    # lines — the regex must keep reading until the next blank line.
    md = """\
### 1. `{{ l2_instance_name }}_drift` — Sub-ledger drift

> Drift SHOULD equal 0.

**Columns:** `account_id`, `account_name`, `account_role`,
`account_parent_role`, `business_day_start`, `business_day_end`,
`stored_balance`, `computed_balance`, `drift`.
"""
    columns = parse_l1_invariants(md)["drift"].columns
    assert columns == (
        "account_id", "account_name", "account_role",
        "account_parent_role", "business_day_start", "business_day_end",
        "stored_balance", "computed_balance", "drift",
    )


# -- Bundled-doc pin tests --------------------------------------------------


def test_bundled_invariants_yields_expected_kinds() -> None:
    # The doc evolves, but these eight kinds are the contract the
    # dashboard panels (AA.C.3) + trainer pane (AA.C.5) wire against.
    # Adding a new kind here is fine; *losing* one would orphan a panel.
    sections = load_bundled_invariants()
    assert set(sections.keys()) == {
        "drift", "ledger_drift", "overdraft",
        "expected_eod_balance_breach", "limit_breach",
        "stuck_pending", "stuck_unbundled", "supersession_audit",
    }


def test_bundled_invariants_every_kind_has_a_title_and_body() -> None:
    sections = load_bundled_invariants()
    for kind, section in sections.items():
        assert section.title, f"{kind!r}: title is empty"
        assert section.body, f"{kind!r}: body is empty"


def test_bundled_invariants_every_should_kind_has_a_blockquote() -> None:
    # Every numbered SHOULD-constraint MUST carry the formal statement
    # as a leading blockquote. ``supersession_audit`` is the lone
    # descriptive exception — it has no blockquote by design.
    sections = load_bundled_invariants()
    for kind, section in sections.items():
        if kind == "supersession_audit":
            assert section.short_statement == ""
        else:
            assert section.short_statement, (
                f"{kind!r}: SHOULD-constraint must declare the formal "
                f"statement as a leading blockquote"
            )
            assert "SHOULD" in section.short_statement, (
                f"{kind!r}: blockquote must contain SHOULD"
            )


def test_bundled_invariants_no_jinja_leakage_under_default_strip() -> None:
    # The dashboard panel reads the parsed body as-is. If a Jinja
    # fragment leaks through the stripper, an operator sees literal
    # ``{% if ... %}`` in the QS sheet bottom.
    sections = load_bundled_invariants()
    for kind, section in sections.items():
        for field_name, value in (
            ("title", section.title),
            ("short_statement", section.short_statement),
            ("body", section.body),
        ):
            assert "{%" not in value, f"{kind!r}.{field_name}: Jinja block leak"
            assert "{{" not in value, (
                f"{kind!r}.{field_name}: Jinja token leak"
            )


def test_bundled_invariants_every_parsed_kind_maps_to_a_sheet() -> None:
    # The kind-to-sheet pin is the AA.C.3 wiring contract. If the doc
    # gains a new kind without a corresponding sheet entry,
    # AA.C.3 has nowhere to land it — fail loudly here.
    sections = load_bundled_invariants()
    for kind in sections:
        assert kind in INVARIANT_KIND_TO_SHEET, (
            f"{kind!r}: no sheet mapping declared in "
            f"INVARIANT_KIND_TO_SHEET — add an entry or rename the kind"
        )


def test_bundled_invariants_drift_carries_the_expected_columns() -> None:
    # Spot-check one section: the columns parse is structural for
    # AA.C.3 (which may build a "this panel describes these columns"
    # sentence). Pinning ``drift`` keeps the parser honest against the
    # real doc's specific Columns wrapping.
    drift = load_bundled_invariants()["drift"]
    assert "account_id" in drift.columns
    assert "drift" in drift.columns
    assert "business_day_start" in drift.columns
