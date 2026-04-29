"""Unit tests for ``tests/e2e/_harness_l1_assertions.py``'s pure-data
dispatch logic (M.4.1.d).

The Playwright assertion bodies need a live browser + deployed
dashboard, so they integration-test only via the harness smoke test
(test_harness_end_to_end.py). This file covers what's testable
without a browser:

1. ``L1_SHEET_FOR_PLANT_KIND`` — dispatch table from plant kind →
   L1 dashboard sheet name. Adding a new plant kind to ScenarioPlant
   that surfaces on L1 needs a corresponding entry here; this test
   catches the drift if someone forgets.

2. ``expected_todays_exceptions_kpi_count(manifest)`` — sum of the
   manifest's L1 SHOULD-violation entries. Walks fake manifests
   with various plant counts to confirm the math.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add tests/e2e to import path so the test can pull in the helper
# module directly without adding it to the package install.
sys.path.insert(0, str(Path(__file__).parent / "e2e"))
from _harness_l1_assertions import (  # noqa: E402
    L1_SHEET_FOR_PLANT_KIND,
    L1_SHOULD_VIOLATION_PLANT_KINDS,
    expected_todays_exceptions_kpi_count,
)


# ---------------------------------------------------------------------------
# Dispatch table sanity
# ---------------------------------------------------------------------------


def test_l1_sheet_dispatch_covers_every_l1_plant_kind() -> None:
    """The dispatch table covers every L1 SHOULD-violation kind plus
    Supersession (which is diagnostic, surfaces on Supersession Audit).
    Doesn't include L2-only kinds (transfer_template_plants,
    rail_firing_plants) — those are M.4.1.e's responsibility."""
    expected_l1_kinds = {
        "drift_plants",
        "overdraft_plants",
        "limit_breach_plants",
        "stuck_pending_plants",
        "stuck_unbundled_plants",
        "supersession_plants",
    }
    assert set(L1_SHEET_FOR_PLANT_KIND.keys()) == expected_l1_kinds


def test_l1_sheet_names_are_unique() -> None:
    """Two plant kinds shouldn't dispatch to the same sheet (would
    indicate a copy-paste in the table)."""
    sheet_names = list(L1_SHEET_FOR_PLANT_KIND.values())
    assert len(sheet_names) == len(set(sheet_names))


def test_should_violation_kinds_subset_of_l1_dispatch() -> None:
    """Every kind in L1_SHOULD_VIOLATION_PLANT_KINDS must also be in
    the L1 sheet dispatch table — both are derived from the same
    L1-side source of truth."""
    assert L1_SHOULD_VIOLATION_PLANT_KINDS <= set(L1_SHEET_FOR_PLANT_KIND.keys())


def test_supersession_excluded_from_kpi_count() -> None:
    """SupersessionPlant is diagnostic, not a SHOULD-violation. It
    surfaces on the Supersession Audit sheet but doesn't contribute
    to Today's Exceptions KPI."""
    assert "supersession_plants" not in L1_SHOULD_VIOLATION_PLANT_KINDS


# ---------------------------------------------------------------------------
# expected_todays_exceptions_kpi_count
# ---------------------------------------------------------------------------


def test_kpi_count_empty_manifest_is_zero() -> None:
    assert expected_todays_exceptions_kpi_count({}) == 0


def test_kpi_count_sums_should_violation_kinds() -> None:
    """Sum across drift + overdraft + breach + pending + unbundled."""
    manifest = {
        "drift_plants": [{}, {}],         # 2
        "overdraft_plants": [{}],          # 1
        "limit_breach_plants": [{}],       # 1
        "stuck_pending_plants": [{}, {}],  # 2
        "stuck_unbundled_plants": [{}],    # 1
    }
    assert expected_todays_exceptions_kpi_count(manifest) == 7


def test_kpi_count_excludes_supersession_and_l2_kinds() -> None:
    """Supersession + transfer_template + rail_firing all NOT counted."""
    manifest = {
        "drift_plants": [{}],          # +1
        "supersession_plants": [{}, {}, {}, {}],  # excluded
        "transfer_template_plants": [{}, {}],     # excluded (L2)
        "rail_firing_plants": [{}, {}, {}, {}],   # excluded (L2)
    }
    assert expected_todays_exceptions_kpi_count(manifest) == 1


def test_kpi_count_handles_missing_keys() -> None:
    """A partial manifest missing entire kinds doesn't KeyError —
    the function uses .get(kind, []) so a YAML with no L2 instance
    or no LimitSchedule (etc.) gracefully contributes 0."""
    partial = {"drift_plants": [{}, {}, {}]}  # 3
    assert expected_todays_exceptions_kpi_count(partial) == 3
