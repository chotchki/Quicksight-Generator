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
sys.path.insert(0, str(Path(__file__).parent))
from _harness_l1_assertions import (  # noqa: E402
    L1_MATVIEW_FOR_PLANT_KIND,
    L1_SHEET_FOR_PLANT_KIND,
    L1_SHOULD_VIOLATION_PLANT_KINDS,
    assert_l1_matview_rows_present,
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
# Layer 1 — assert_l1_matview_rows_present (M.4.1.k)
# ---------------------------------------------------------------------------


def test_l1_matview_dispatch_covers_all_should_violation_kinds() -> None:
    """Every kind in L1_SHOULD_VIOLATION_PLANT_KINDS must have a
    corresponding matview entry — otherwise Layer 1 silently skips
    the kind and the regression hides until Layer 2 (browser) hits it.
    Supersession is intentionally absent (no dedicated matview)."""
    assert (
        set(L1_MATVIEW_FOR_PLANT_KIND.keys())
        == set(L1_SHOULD_VIOLATION_PLANT_KINDS)
    )


def test_l1_matview_names_are_unique() -> None:
    """Two plant kinds shouldn't map to the same matview (would
    indicate a copy-paste in the dispatch table)."""
    names = list(L1_MATVIEW_FOR_PLANT_KIND.values())
    assert len(names) == len(set(names))


class _FakeCursor:
    """psycopg2-cursor-shaped: yields preset row sets per SQL keyed
    by SUBSTR match (each test sets a `responses` dict). Records
    every executed (sql, params) pair for assertion."""

    def __init__(self, responses: dict[str, int]) -> None:
        self.responses = responses
        self.executed: list[tuple[str, tuple]] = []
        self._last_sql: str = ""

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))
        self._last_sql = sql

    def fetchone(self) -> tuple[int]:
        # The helper does two queries per plant: COUNT(*) WHERE
        # account_id=, then COUNT(*) total. Match by `WHERE` substring
        # for the per-account count; everything else returns total.
        if "WHERE" in self._last_sql:
            # Look up by full SQL match for the per-account-id query.
            return (self.responses.get(self._last_sql, 0),)
        return (self.responses.get(self._last_sql, 0),)


class _FakeConn:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor


def test_matview_check_passes_when_all_planted_rows_present() -> None:
    """Every planted account_id has a matching row in its matview →
    no AssertionError. Single happy-path with one plant per kind."""
    prefix = "e2e_test"
    manifest = {
        "drift_plants": [{"account_id": "cust-001"}],
        "overdraft_plants": [{"account_id": "cust-002"}],
        "limit_breach_plants": [{"account_id": "cust-001"}],
        "stuck_pending_plants": [],  # empty kinds skipped
        "stuck_unbundled_plants": [{"account_id": "cust-002"}],
    }
    # All per-account counts > 0 → no failure.
    responses = {
        f"SELECT COUNT(*) FROM {prefix}_drift WHERE account_id = %s": 1,
        f"SELECT COUNT(*) FROM {prefix}_overdraft WHERE account_id = %s": 1,
        f"SELECT COUNT(*) FROM {prefix}_limit_breach WHERE account_id = %s": 1,
        f"SELECT COUNT(*) FROM {prefix}_stuck_unbundled WHERE account_id = %s": 1,
        # Total-count queries return whatever; failure path doesn't fire.
        f"SELECT COUNT(*) FROM {prefix}_drift": 5,
        f"SELECT COUNT(*) FROM {prefix}_overdraft": 5,
        f"SELECT COUNT(*) FROM {prefix}_limit_breach": 5,
        f"SELECT COUNT(*) FROM {prefix}_stuck_unbundled": 5,
    }
    cur = _FakeCursor(responses)
    conn = _FakeConn(cur)
    assert_l1_matview_rows_present(conn, prefix, manifest)


def test_matview_check_raises_when_planted_account_missing() -> None:
    """Planted account_id NOT found in matview → AssertionError that
    names the matview, account_id, plant, AND total row count."""
    import pytest as _pytest

    prefix = "e2e_test"
    manifest = {
        "overdraft_plants": [
            {"account_id": "cust-002", "days_ago": 6},
        ],
    }
    responses = {
        f"SELECT COUNT(*) FROM {prefix}_overdraft WHERE account_id = %s": 0,
        f"SELECT COUNT(*) FROM {prefix}_overdraft": 3,
    }
    cur = _FakeCursor(responses)
    conn = _FakeConn(cur)
    with _pytest.raises(AssertionError) as exc:
        assert_l1_matview_rows_present(conn, prefix, manifest)
    msg = str(exc.value)
    assert f"{prefix}_overdraft" in msg
    assert "cust-002" in msg
    assert "Total rows in the matview: 3" in msg


def test_matview_check_skips_empty_plant_kinds() -> None:
    """A kind with no planted rows skips the query entirely — no
    matview lookup, no failure on missing data."""
    prefix = "e2e_test"
    manifest = {
        "drift_plants": [],
        "overdraft_plants": [],
        "limit_breach_plants": [],
        "stuck_pending_plants": [],
        "stuck_unbundled_plants": [],
    }
    cur = _FakeCursor({})
    conn = _FakeConn(cur)
    assert_l1_matview_rows_present(conn, prefix, manifest)
    # Zero queries executed because every kind was empty.
    assert cur.executed == []


def test_matview_check_skips_kinds_not_in_dispatch() -> None:
    """Plant kinds not in L1_MATVIEW_FOR_PLANT_KIND (e.g.
    supersession_plants, rail_firing_plants) are skipped silently —
    those kinds either have no dedicated matview or are L2 surfaces."""
    prefix = "e2e_test"
    manifest = {
        "supersession_plants": [{"account_id": "cust-x"}],
        "rail_firing_plants": [{"rail_name": "R1"}],
        # No L1 SHOULD-violation plants → no matview queries.
    }
    cur = _FakeCursor({})
    conn = _FakeConn(cur)
    assert_l1_matview_rows_present(conn, prefix, manifest)
    assert cur.executed == []
