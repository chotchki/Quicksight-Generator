"""Unit tests for the Account Recon app (Phase 3 skeleton).

Covers:
- Demo data determinism, row counts, referential integrity, scenario coverage
- SQL schema and seed structure
- Full generate pipeline + cross-reference validation
- Visual counts per sheet, Getting Started sheet, subtitles/descriptions
- Analysis name driven by theme preset
- CLI smoke tests
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.account_recon.constants import (
    SHEET_AR_BALANCES,
    SHEET_AR_EXCEPTIONS,
    SHEET_AR_GETTING_STARTED,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TRANSFERS,
)
from quicksight_gen.account_recon.demo_data import (
    LEDGER_ACCOUNTS,
    SUBLEDGER_ACCOUNTS,
    generate_demo_sql,
)
from quicksight_gen.cli import main
from quicksight_gen.common.config import Config


ANCHOR = date(2026, 4, 11)


# ---------------------------------------------------------------------------
# Demo data — determinism + structure
# ---------------------------------------------------------------------------

@pytest.fixture()
def ar_sql() -> str:
    return generate_demo_sql(ANCHOR)


@pytest.fixture()
def ar_parsed(ar_sql: str) -> dict[str, list[str]]:
    """Parse ar_sql into table → list of parenthesised value-row strings."""
    result: dict[str, list[str]] = {}
    for m in re.finditer(
        r"INSERT INTO (ar_\w+) \([^)]+\) VALUES\n(.*?);",
        ar_sql,
        re.DOTALL,
    ):
        table = m.group(1)
        body = m.group(2)
        rows = re.findall(r"\(([^)]+)\)", body)
        result[table] = rows
    return result


@pytest.fixture()
def unified_parsed(ar_sql: str) -> dict[str, list[str]]:
    """Parse unified transfer + posting tables from the AR seed SQL."""
    result: dict[str, list[str]] = {}
    for m in re.finditer(
        r"INSERT INTO (transfer|posting) \([^)]+\) VALUES\n(.*?);",
        ar_sql,
        re.DOTALL,
    ):
        table = m.group(1)
        body = m.group(2)
        rows = re.findall(r"\(([^)]+)\)", body)
        result[table] = rows
    return result


class TestDemoDeterminism:
    def test_same_anchor_identical_output(self):
        assert generate_demo_sql(ANCHOR) == generate_demo_sql(ANCHOR)

    def test_different_anchor_shifts_dates(self):
        a = generate_demo_sql(date(2026, 1, 1))
        b = generate_demo_sql(date(2026, 6, 1))
        assert a != b


class TestDemoRowCounts:
    def test_ledger_accounts(self, ar_parsed):
        assert len(ar_parsed["ar_ledger_accounts"]) == len(LEDGER_ACCOUNTS)

    def test_subledger_accounts(self, ar_parsed):
        assert len(ar_parsed["ar_subledger_accounts"]) == len(SUBLEDGER_ACCOUNTS)

    def test_postings(self, unified_parsed):
        # 66 sub-ledger transfers × 2 legs = 132
        # + 5 funding batches (1 ledger + N sub-ledger legs each)
        # + 3 fee assessments (1 ledger leg each)
        # + 2 clearing sweeps (2 ledger legs each)
        assert len(unified_parsed["posting"]) == 154

    def test_transfers(self, unified_parsed):
        # 66 sub-ledger + 5 funding + 3 fee + 2 sweep = 76
        assert len(unified_parsed["transfer"]) == 76

    def test_ledger_transfer_limits(self, ar_parsed):
        from quicksight_gen.account_recon.demo_data import _LEDGER_LIMITS
        assert (
            len(ar_parsed["ar_ledger_transfer_limits"]) == len(_LEDGER_LIMITS)
        )

    def test_ledger_daily_balances(self, ar_parsed):
        # 3 internal ledgers × 41 days (0..40 inclusive) = 123 rows.
        # External ledgers are not reconciled (SPEC "Reconciliation scope").
        assert len(ar_parsed["ar_ledger_daily_balances"]) == 123

    def test_subledger_daily_balances(self, ar_parsed):
        # 6 internal sub-ledgers × 41 days = 246 rows (the two external
        # ledgers' four sub-ledgers are omitted).
        assert len(ar_parsed["ar_subledger_daily_balances"]) == 246


class TestReferentialIntegrity:
    """FK-safe seeds — every FK value exists in the parent table."""

    def _col(self, rows: list[str], idx: int) -> list[str]:
        return [
            [p.strip().strip("'") for p in row.split(",")][idx]
            for row in rows
        ]

    def test_subledger_ledger_fk(self, ar_parsed):
        ledger_ids = set(self._col(ar_parsed["ar_ledger_accounts"], 0))
        subledger_ledgers = set(self._col(ar_parsed["ar_subledger_accounts"], 3))
        assert subledger_ledgers.issubset(ledger_ids), (
            f"Unknown ledger_account_ids: {subledger_ledgers - ledger_ids}"
        )

    def test_posting_subledger_fk(self, ar_parsed, unified_parsed):
        subledger_ids = set(self._col(ar_parsed["ar_subledger_accounts"], 0))
        posting_subledgers = set(self._col(unified_parsed["posting"], 3))
        posting_subledgers.discard("NULL")  # ledger-level postings have no sub-ledger
        assert posting_subledgers.issubset(subledger_ids)

    def test_ledger_daily_balance_fk(self, ar_parsed):
        ledger_ids = set(self._col(ar_parsed["ar_ledger_accounts"], 0))
        bal_ledgers = set(self._col(ar_parsed["ar_ledger_daily_balances"], 0))
        assert bal_ledgers.issubset(ledger_ids)

    def test_subledger_daily_balance_fk(self, ar_parsed):
        subledger_ids = set(self._col(ar_parsed["ar_subledger_accounts"], 0))
        bal_subledgers = set(self._col(ar_parsed["ar_subledger_daily_balances"], 0))
        assert bal_subledgers.issubset(subledger_ids)


class TestScenarioCoverage:
    """Guarantees every AR visual has non-empty data out-of-the-box."""

    def test_failed_postings_exist(self, unified_parsed):
        """Status=failed must be present so the Transactions bar chart and
        the failed-transaction KPI aren't empty."""
        statuses = [
            [p.strip().strip("'") for p in row.split(",")][6]
            for row in unified_parsed["posting"]
        ]
        failed = sum(1 for s in statuses if s == "failed")
        # 4 failed-leg + 8 all-failed (both legs) = 12
        assert failed >= 8, f"Only {failed} failed postings"

    def test_success_and_failed_statuses_both_present(self, unified_parsed):
        statuses = {
            [p.strip().strip("'") for p in row.split(",")][6]
            for row in unified_parsed["posting"]
        }
        assert {"success", "failed"}.issubset(statuses)

    def test_internal_and_external_ledgers_exist(self, ar_parsed):
        is_internals = {
            [p.strip() for p in row.split(",")][2].strip().lower()
            for row in ar_parsed["ar_ledger_accounts"]
        }
        assert {"true", "false"}.issubset(is_internals), (
            "Need both internal + external ledgers for scope splits"
        )

    def test_ledger_drift_is_planted(self, ar_parsed):
        """Ledger-level drift plants must include both signs and each
        planted (ledger, date) cell must exist in the balances table."""
        from quicksight_gen.account_recon.demo_data import _LEDGER_DRIFT_PLANT

        assert len(_LEDGER_DRIFT_PLANT) >= 3, "Need several ledger drift cells"
        deltas = [Decimal(d) for _, _, d in _LEDGER_DRIFT_PLANT]
        assert any(d > 0 for d in deltas), "Need a positive ledger drift"
        assert any(d < 0 for d in deltas), "Need a negative ledger drift"

        balance_rows = {
            tuple(p.strip().strip("'") for p in row.split(",")[:2])
            for row in ar_parsed["ar_ledger_daily_balances"]
        }
        from datetime import timedelta
        for ledger_id, days_ago, _ in _LEDGER_DRIFT_PLANT:
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            assert (ledger_id, bdate) in balance_rows, (
                f"Missing balance row for planted drift ({ledger_id}, {bdate})"
            )

    def test_subledger_drift_is_planted(self, ar_parsed):
        """Sub-ledger drift plants must include both signs and land on
        internal sub-ledger accounts with rows in
        ar_subledger_daily_balances."""
        from quicksight_gen.account_recon.demo_data import _SUBLEDGER_DRIFT_PLANT

        assert len(_SUBLEDGER_DRIFT_PLANT) >= 3, (
            "Need several sub-ledger drift cells"
        )
        deltas = [Decimal(d) for _, _, d in _SUBLEDGER_DRIFT_PLANT]
        assert any(d > 0 for d in deltas), "Need a positive sub-ledger drift"
        assert any(d < 0 for d in deltas), "Need a negative sub-ledger drift"

        balance_rows = {
            tuple(p.strip().strip("'") for p in row.split(",")[:2])
            for row in ar_parsed["ar_subledger_daily_balances"]
        }
        from datetime import timedelta
        for subledger_id, days_ago, _ in _SUBLEDGER_DRIFT_PLANT:
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            assert (subledger_id, bdate) in balance_rows, (
                f"Missing balance row for planted drift "
                f"({subledger_id}, {bdate})"
            )

    def test_ledger_and_subledger_drift_are_independent(self):
        """Ledger-level and sub-ledger-level drift plants should surface
        different rows on the Exceptions tab — guard against cell overlap
        that would make them look like the same finding in two places."""
        from quicksight_gen.account_recon.demo_data import (
            _LEDGER_DRIFT_PLANT,
            _SUBLEDGER_DRIFT_PLANT,
            SUBLEDGER_ACCOUNTS,
        )

        ledger_cells = {(p, d) for p, d, _ in _LEDGER_DRIFT_PLANT}
        # Map sub-ledger accounts back to their ledgers so we can detect overlap.
        subledger_ledger = {sid: lid for sid, _n, lid in SUBLEDGER_ACCOUNTS}
        subledger_by_ledger_day = {
            (subledger_ledger[sid], d)
            for sid, d, _ in _SUBLEDGER_DRIFT_PLANT
        }
        assert not (ledger_cells & subledger_by_ledger_day), (
            "Ledger and sub-ledger drift plants collide on the same "
            "(ledger, day) — pick disjoint cells"
        )

    def test_memos_present(self, ar_sql):
        """Memos must flow onto transactions so the transfer-summary memo
        column is non-empty."""
        for memo_fragment in ("Feed lot settlement", "Grain silo delivery"):
            assert memo_fragment in ar_sql

    def _transfer_legs_by_scope(
        self, ar_parsed, unified_parsed,
    ) -> dict[str, tuple[int, int]]:
        """Return {transfer_id: (internal_leg_count, external_leg_count)}.

        Parses subledger.is_internal from ar_subledger_accounts, then
        groups posting rows by transfer_id and counts the legs on each
        side. Used by the scenario coverage tests for transfer
        pair-patterns.
        """
        internal_by_subledger: dict[str, bool] = {}
        for row in ar_parsed["ar_subledger_accounts"]:
            parts = [p.strip() for p in row.split(",")]
            sid = parts[0].strip("'")
            is_internal = parts[2].strip().lower() == "true"
            internal_by_subledger[sid] = is_internal

        buckets: dict[str, list[bool]] = {}
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            transfer_id = parts[1]
            subledger_id = parts[3]
            if subledger_id == "NULL":
                continue  # ledger-level posting — no sub-ledger scope
            buckets.setdefault(transfer_id, []).append(
                internal_by_subledger[subledger_id]
            )
        return {
            tid: (sum(flags), sum(1 for f in flags if not f))
            for tid, flags in buckets.items()
        }

    def test_cross_scope_transfers_exist(self, ar_parsed, unified_parsed):
        """Transfers with one internal leg + one external leg must exist
        so the dashboard has examples where the external leg doesn't
        affect any tracked balance."""
        by_scope = self._transfer_legs_by_scope(ar_parsed, unified_parsed)
        cross_scope = [
            tid for tid, (i, e) in by_scope.items() if i >= 1 and e >= 1
        ]
        assert len(cross_scope) >= 20, (
            f"Need ≥20 cross-scope transfers, got {len(cross_scope)}"
        )

    def test_internal_only_transfers_exist(self, ar_parsed, unified_parsed):
        """Transfers where both legs land on internal sub-ledgers must
        exist so drift bugs that only manifest when one transfer touches
        two tracked balances are surfaced by the demo data.

        Without these, a query that sums transfer legs by transfer_id
        instead of by subledger_account_id would silently work on
        cross-scope-only seed data — the bug only shows up when both
        legs are tracked.
        """
        by_scope = self._transfer_legs_by_scope(ar_parsed, unified_parsed)
        internal_only = [
            tid for tid, (i, e) in by_scope.items() if i >= 2 and e == 0
        ]
        assert len(internal_only) >= 15, (
            f"Need ≥15 internal-internal transfers, got {len(internal_only)}"
        )

    def test_failed_transfer_pattern_coverage(self, ar_parsed, unified_parsed):
        """Both failed-leg and fully-failed scenarios must include at
        least one internal-internal instance — otherwise a regression in
        how failed internal legs affect sub-ledger balances would slip
        through the demo."""
        by_scope = self._transfer_legs_by_scope(ar_parsed, unified_parsed)
        statuses_by_transfer: dict[str, list[str]] = {}
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            transfer_id = parts[1]
            status = parts[6]
            statuses_by_transfer.setdefault(transfer_id, []).append(status)

        internal_only_ids = {
            tid for tid, (i, e) in by_scope.items() if i >= 2 and e == 0
        }
        internal_only_with_any_failed = [
            tid for tid in internal_only_ids
            if any(s == "failed" for s in statuses_by_transfer[tid])
        ]
        assert len(internal_only_with_any_failed) >= 1, (
            "Need ≥1 internal-internal transfer with a failed leg"
        )

    def test_all_transfer_types_present(self, unified_parsed):
        """All AR transfer types must have traffic so the
        transfer-type filter has something to filter on."""
        types = {
            [p.strip().strip("'") for p in row.split(",")][2]
            for row in unified_parsed["transfer"]
        }
        expected = {"ach", "wire", "internal", "cash",
                    "funding_batch", "fee", "clearing_sweep"}
        assert types == expected, (
            f"Expected all AR transfer types, got {types}"
        )

    def test_origin_both_values_present(self, unified_parsed):
        """Both origin values must be seeded so the Transaction Detail
        column never reads as a single-value placeholder."""
        origins: list[str] = []
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            origins.append(parts[3])
        counts = {
            "internal_initiated": sum(1 for o in origins
                                      if o == "internal_initiated"),
            "external_force_posted": sum(1 for o in origins
                                         if o == "external_force_posted"),
        }
        assert counts["internal_initiated"] >= 10, (
            f"Need ≥10 internal_initiated transfers, got {counts}"
        )
        assert counts["external_force_posted"] >= 5, (
            f"Need ≥5 external_force_posted transfers, got {counts}"
        )
        assert set(origins) == {
            "internal_initiated", "external_force_posted",
        }, f"Unexpected origin values: {set(origins)}"

    def test_ledger_limits_seeded(self, ar_parsed):
        """Ledger transfer limits must be seeded — otherwise the
        limit-breach view has no thresholds to compare against."""
        from quicksight_gen.account_recon.demo_data import _LEDGER_LIMITS

        assert len(_LEDGER_LIMITS) >= 3, "Need ≥3 ledger limit rows"
        types = {xtype for _lid, xtype, _lim in _LEDGER_LIMITS}
        assert len(types) >= 2, "Limits must cover ≥2 transfer types"
        ledgers = {lid for lid, _x, _l in _LEDGER_LIMITS}
        assert len(ledgers) >= 2, "Limits must span ≥2 ledgers"

    def test_limit_breaches_materialize(self, ar_parsed, unified_parsed):
        """Planted breach cells must emerge from running the view
        logic on the seed data — the query sums outbound |amount| per
        (sub-ledger, day, type), joins ledger-limits, and keeps rows
        where total > limit."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _LIMIT_BREACH_PLANT,
            _LEDGER_LIMITS,
        )

        is_internal: dict[str, bool] = {}
        ledger_by_subledger: dict[str, str] = {}
        for row in ar_parsed["ar_subledger_accounts"]:
            parts = [p.strip() for p in row.split(",")]
            sid = parts[0].strip().strip("'")
            is_internal[sid] = parts[2].strip().lower() == "true"
            ledger_by_subledger[sid] = parts[3].strip().strip("'")

        transfer_type_by_id: dict[str, str] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            transfer_type_by_id[parts[0]] = parts[2]

        totals: dict[tuple[str, str, str], Decimal] = {}
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            subl = parts[3]
            if subl == "NULL":
                continue  # ledger-level posting — no sub-ledger limit
            amount = Decimal(parts[4])
            day = parts[5].split(" ")[0]
            status = parts[6]
            xtype = transfer_type_by_id[parts[1]]
            if status == "failed":
                continue
            if amount >= 0:
                continue
            if not is_internal.get(subl):
                continue
            key = (subl, day, xtype)
            totals[key] = totals.get(key, Decimal("0")) + abs(amount)

        limit_map = {
            (lid, xtype): Decimal(lim) for lid, xtype, lim in _LEDGER_LIMITS
        }
        breaches: set[tuple[str, str, str]] = set()
        for (subl, day, xtype), outbound in totals.items():
            ledger = ledger_by_subledger[subl]
            limit = limit_map.get((ledger, xtype))
            if limit is not None and outbound > limit:
                breaches.add((subl, day, xtype))

        assert len(breaches) >= 3, (
            f"Expected ≥3 limit-breach cells, got {len(breaches)}"
        )
        for subl, days_ago, xtype, _amt, _memo in _LIMIT_BREACH_PLANT:
            day = (ANCHOR - timedelta(days=days_ago)).isoformat()
            assert (subl, day, xtype) in breaches, (
                f"Planted breach ({subl}, {day}, {xtype}) didn't materialize"
            )

    def test_overdrafts_materialize(self, ar_parsed):
        """Planted overdraft cells must show up as balance < 0 in
        ar_subledger_daily_balances — the ar_subledger_overdraft view
        just filters on that condition."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import _OVERDRAFT_PLANT

        balances: dict[tuple[str, str], Decimal] = {}
        for row in ar_parsed["ar_subledger_daily_balances"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            balances[(parts[0], parts[1])] = Decimal(parts[2])

        negative = [k for k, v in balances.items() if v < 0]
        assert len(negative) >= 3, (
            f"Expected ≥3 overdraft rows, got {len(negative)}"
        )
        for subl, days_ago, _amt, _memo in _OVERDRAFT_PLANT:
            day = (ANCHOR - timedelta(days=days_ago)).isoformat()
            bal = balances.get((subl, day))
            assert bal is not None and bal < 0, (
                f"Planted overdraft cell ({subl}, {day}) is not negative "
                f"(got {bal})"
            )

    def test_all_plants_disjoint(self):
        """Each of the four exception tables must surface a different
        set of findings — drift, breach, and overdraft plants must not
        share sub-ledger×day cells. Otherwise the Exceptions tab would
        show the same row across multiple tables and obscure the four
        distinct reconciliation checks."""
        from quicksight_gen.account_recon.demo_data import (
            _SUBLEDGER_DRIFT_PLANT,
            _LIMIT_BREACH_PLANT,
            _OVERDRAFT_PLANT,
            _LEDGER_DRIFT_PLANT,
            SUBLEDGER_ACCOUNTS,
        )

        subledger_cells = {(a, d) for a, d, _ in _SUBLEDGER_DRIFT_PLANT}
        breach_cells = {(a, d) for a, d, _, _, _ in _LIMIT_BREACH_PLANT}
        overdraft_cells = {(a, d) for a, d, _, _ in _OVERDRAFT_PLANT}

        assert not (subledger_cells & breach_cells), (
            "Sub-ledger drift and limit breach plants share "
            "sub-ledger×day cells"
        )
        assert not (subledger_cells & overdraft_cells), (
            "Sub-ledger drift and overdraft plants share "
            "sub-ledger×day cells"
        )
        assert not (breach_cells & overdraft_cells), (
            "Breach and overdraft plants share sub-ledger×day cells"
        )

        subledger_ledger = {sid: lid for sid, _n, lid in SUBLEDGER_ACCOUNTS}
        ledger_cells = {(p, d) for p, d, _ in _LEDGER_DRIFT_PLANT}
        breach_ledger_cells = {
            (subledger_ledger[a], d) for a, d, _, _, _ in _LIMIT_BREACH_PLANT
        }
        overdraft_ledger_cells = {
            (subledger_ledger[a], d) for a, d, _, _ in _OVERDRAFT_PLANT
        }
        assert not (ledger_cells & breach_ledger_cells), (
            "Ledger drift and breach plants share (ledger, day) cells"
        )
        assert not (ledger_cells & overdraft_ledger_cells), (
            "Ledger drift and overdraft plants share (ledger, day) cells"
        )


# ---------------------------------------------------------------------------
# Unified transfer + posting (Phase B dual-write)
# ---------------------------------------------------------------------------

class TestUnifiedTables:
    def _col(self, rows: list[str], idx: int) -> list[str]:
        return [
            [p.strip().strip("'") for p in row.split(",")][idx]
            for row in rows
        ]

    def test_transfer_row_count(self, unified_parsed):
        """76 transfers: 66 sub-ledger + 5 funding + 3 fee + 2 sweep."""
        assert len(unified_parsed["transfer"]) == 76

    def test_posting_row_count(self, unified_parsed):
        """154 postings: 132 sub-ledger + ledger-level postings."""
        assert len(unified_parsed["posting"]) == 154

    def test_posting_transfer_fk(self, unified_parsed):
        """Every posting.transfer_id exists in transfer."""
        transfer_ids = set(self._col(unified_parsed["transfer"], 0))
        posting_tids = set(self._col(unified_parsed["posting"], 1))
        assert posting_tids.issubset(transfer_ids)

    def test_posting_account_fk(self, ar_parsed, unified_parsed):
        """Every posting.subledger_account_id (when set) exists in ar_subledger_accounts."""
        subledger_ids = {
            [p.strip().strip("'") for p in row.split(",")][0]
            for row in ar_parsed["ar_subledger_accounts"]
        }
        posting_accounts = set(self._col(unified_parsed["posting"], 3))
        posting_accounts.discard("NULL")  # ledger-level postings
        assert posting_accounts.issubset(subledger_ids)

    def test_ar_transfer_parent_is_null(self, unified_parsed):
        """AR transfers have no chain — parent_transfer_id should be NULL."""
        parents = self._col(unified_parsed["transfer"], 1)
        assert all(p == "NULL" for p in parents)

    def test_posting_fields_populated(self, unified_parsed):
        """Every posting has non-empty transfer_id, account, and amount."""
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            assert parts[1], "posting.transfer_id empty"
            assert parts[2], "posting.ledger_account_id empty"
            assert Decimal(parts[4]), "posting.signed_amount is zero"


# ---------------------------------------------------------------------------
# Ledger-level posting scenario coverage
# ---------------------------------------------------------------------------

class TestLedgerPostingScenarios:
    """Assert ledger-level posting scenarios exist and are well-formed."""

    def _parse_postings(self, unified_parsed):
        """Return list of parsed posting dicts."""
        results = []
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            results.append({
                "posting_id": parts[0],
                "transfer_id": parts[1],
                "ledger_account_id": parts[2],
                "subledger_account_id": parts[3] if parts[3] != "NULL" else None,
                "signed_amount": Decimal(parts[4]),
                "posted_at": parts[5],
                "status": parts[6],
            })
        return results

    def _parse_transfers(self, unified_parsed):
        """Return {transfer_id: transfer_type}."""
        result = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            result[parts[0]] = parts[2]
        return result

    def test_funding_batch_count(self, unified_parsed):
        xfer_types = self._parse_transfers(unified_parsed)
        funding = [tid for tid, t in xfer_types.items() if t == "funding_batch"]
        assert len(funding) >= 5, f"Expected >=5 funding batches, got {len(funding)}"

    def test_fee_assessment_count(self, unified_parsed):
        xfer_types = self._parse_transfers(unified_parsed)
        fees = [tid for tid, t in xfer_types.items() if t == "fee"]
        assert len(fees) >= 3, f"Expected >=3 fee assessments, got {len(fees)}"

    def test_clearing_sweep_count(self, unified_parsed):
        xfer_types = self._parse_transfers(unified_parsed)
        sweeps = [tid for tid, t in xfer_types.items() if t == "clearing_sweep"]
        assert len(sweeps) >= 2, f"Expected >=2 clearing sweeps, got {len(sweeps)}"

    def test_ledger_postings_have_no_subledger(self, unified_parsed):
        """Ledger-level postings (funding/fee/sweep) have subledger_account_id = NULL."""
        postings = self._parse_postings(unified_parsed)
        xfer_types = self._parse_transfers(unified_parsed)
        for p in postings:
            if p["subledger_account_id"] is None:
                assert xfer_types[p["transfer_id"]] in (
                    "funding_batch", "fee", "clearing_sweep",
                ), f"Non-ledger transfer {p['transfer_id']} has NULL subledger"

    def test_ledger_postings_have_valid_ledger_fk(self, ar_parsed, unified_parsed):
        """All ledger-level postings FK to valid ar_ledger_accounts."""
        ledger_ids = set()
        for row in ar_parsed["ar_ledger_accounts"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            ledger_ids.add(parts[0])
        postings = self._parse_postings(unified_parsed)
        for p in postings:
            if p["subledger_account_id"] is None:
                assert p["ledger_account_id"] in ledger_ids, (
                    f"Ledger posting {p['posting_id']} references unknown "
                    f"ledger {p['ledger_account_id']}"
                )

    def test_funding_batch_net_zero(self, unified_parsed):
        """Each funding batch nets to zero across all legs."""
        postings = self._parse_postings(unified_parsed)
        xfer_types = self._parse_transfers(unified_parsed)
        by_xfer: dict[str, Decimal] = {}
        for p in postings:
            if xfer_types.get(p["transfer_id"]) == "funding_batch":
                by_xfer[p["transfer_id"]] = (
                    by_xfer.get(p["transfer_id"], Decimal("0"))
                    + p["signed_amount"]
                )
        for tid, net in by_xfer.items():
            assert net == 0, f"Funding batch {tid} net={net}, expected 0"

    def test_fee_assessment_non_zero(self, unified_parsed):
        """Each fee assessment is single-leg and non-zero."""
        postings = self._parse_postings(unified_parsed)
        xfer_types = self._parse_transfers(unified_parsed)
        by_xfer: dict[str, list] = {}
        for p in postings:
            if xfer_types.get(p["transfer_id"]) == "fee":
                by_xfer.setdefault(p["transfer_id"], []).append(p)
        for tid, legs in by_xfer.items():
            assert len(legs) == 1, f"Fee {tid} has {len(legs)} legs, expected 1"
            assert legs[0]["signed_amount"] != 0, f"Fee {tid} has zero amount"

    def test_clearing_sweep_net_zero(self, unified_parsed):
        """Each clearing sweep has 2 ledger legs that net to zero."""
        postings = self._parse_postings(unified_parsed)
        xfer_types = self._parse_transfers(unified_parsed)
        by_xfer: dict[str, list] = {}
        for p in postings:
            if xfer_types.get(p["transfer_id"]) == "clearing_sweep":
                by_xfer.setdefault(p["transfer_id"], []).append(p)
        for tid, legs in by_xfer.items():
            assert len(legs) == 2, f"Sweep {tid} has {len(legs)} legs, expected 2"
            net = sum(leg["signed_amount"] for leg in legs)
            assert net == 0, f"Sweep {tid} net={net}, expected 0"
            for leg in legs:
                assert leg["subledger_account_id"] is None, (
                    f"Sweep {tid} leg has subledger — expected ledger-only"
                )

    def test_funding_batch_has_mixed_levels(self, unified_parsed):
        """Each funding batch has both ledger-level and sub-ledger-level legs."""
        postings = self._parse_postings(unified_parsed)
        xfer_types = self._parse_transfers(unified_parsed)
        by_xfer: dict[str, dict[str, int]] = {}
        for p in postings:
            if xfer_types.get(p["transfer_id"]) == "funding_batch":
                tid = p["transfer_id"]
                by_xfer.setdefault(tid, {"ledger": 0, "subledger": 0})
                if p["subledger_account_id"] is None:
                    by_xfer[tid]["ledger"] += 1
                else:
                    by_xfer[tid]["subledger"] += 1
        for tid, counts in by_xfer.items():
            assert counts["ledger"] >= 1, f"Funding {tid} has no ledger-level legs"
            assert counts["subledger"] >= 1, f"Funding {tid} has no sub-ledger legs"


# ---------------------------------------------------------------------------
# Seed SQL structure
# ---------------------------------------------------------------------------

class TestSeedSqlStructure:
    def test_no_unclosed_quotes(self, ar_sql):
        collapsed = ar_sql.replace("''", "")
        for i, line in enumerate(collapsed.split("\n"), 1):
            assert line.count("'") % 2 == 0, (
                f"Line {i} has unbalanced quotes: {line[:80]}"
            )

    def test_insert_tables_match_schema(self, ar_sql):
        tables = set(re.findall(r"INSERT INTO (\w+)", ar_sql))
        assert tables == {
            "ar_ledger_accounts",
            "ar_subledger_accounts",
            "ar_ledger_transfer_limits",
            "ar_ledger_daily_balances",
            "ar_subledger_daily_balances",
            "transfer",
            "posting",
        }

    def test_fk_safe_order(self, ar_sql):
        positions = {}
        for m in re.finditer(r"INSERT INTO (\w+)", ar_sql):
            positions.setdefault(m.group(1), m.start())
        assert positions["ar_ledger_accounts"] < positions["ar_subledger_accounts"]
        assert (
            positions["ar_ledger_accounts"]
            < positions["ar_ledger_daily_balances"]
        )
        assert (
            positions["ar_subledger_accounts"]
            < positions["ar_subledger_daily_balances"]
        )
        assert (
            positions["ar_ledger_accounts"]
            < positions["ar_ledger_transfer_limits"]
        )
        # Unified tables: transfer before posting, both after ar_subledger_accounts
        assert positions["ar_subledger_accounts"] < positions["transfer"]
        assert positions["transfer"] < positions["posting"]


# ---------------------------------------------------------------------------
# Schema SQL (checks the shared demo/schema.sql file)
# ---------------------------------------------------------------------------

class TestSchemaSql:
    @pytest.fixture()
    def schema_sql(self) -> str:
        return (
            Path(__file__).resolve().parent.parent / "demo" / "schema.sql"
        ).read_text()

    def test_creates_ar_tables(self, schema_sql):
        for table in (
            "ar_ledger_accounts",
            "ar_subledger_accounts",
            "ar_ledger_daily_balances",
            "ar_subledger_daily_balances",
            "ar_ledger_transfer_limits",
            "transfer",
            "posting",
        ):
            assert f"CREATE TABLE {table}" in schema_sql

    def test_creates_ar_views(self, schema_sql):
        for view in (
            "ar_computed_subledger_daily_balance",
            "ar_computed_ledger_daily_balance",
            "ar_subledger_balance_drift",
            "ar_ledger_balance_drift",
            "ar_transfer_net_zero",
            "ar_transfer_summary",
            "ar_subledger_daily_outbound_by_type",
            "ar_subledger_limit_breach",
            "ar_subledger_overdraft",
        ):
            assert f"CREATE VIEW {view}" in schema_sql

    def test_transfer_type_column(self, schema_sql):
        """transfer table must carry the transfer_type column."""
        m = re.search(
            r"CREATE TABLE transfer \((.*?)\);",
            schema_sql,
            re.DOTALL,
        )
        assert m, "transfer CREATE TABLE missing"
        assert "transfer_type" in m.group(1), (
            "transfer.transfer_type column missing"
        )


# ---------------------------------------------------------------------------
# Generate pipeline
# ---------------------------------------------------------------------------

@pytest.fixture()
def ar_output_dir(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(
        "aws_account_id: '111122223333'\n"
        "aws_region: us-west-2\n"
        "datasource_arn: arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds\n"
        "principal_arns:\n"
        "  - arn:aws:quicksight:us-west-2:111122223333:user/default/admin\n"
    )
    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        main, ["generate", "-c", str(config), "-o", str(out), "account-recon"],
    )
    assert result.exit_code == 0, result.output
    return out


def _load(out_dir: Path, name: str) -> dict:
    return json.loads((out_dir / name).read_text())


def _collect_dataset_refs(obj: object, refs: set[str]) -> None:
    if isinstance(obj, dict):
        if "DataSetIdentifier" in obj:
            refs.add(obj["DataSetIdentifier"])
        for v in obj.values():
            _collect_dataset_refs(v, refs)
    elif isinstance(obj, list):
        for item in obj:
            _collect_dataset_refs(item, refs)


class TestGenerateOutput:
    def test_theme_file_exists(self, ar_output_dir):
        assert (ar_output_dir / "theme.json").exists()

    def test_analysis_file_exists(self, ar_output_dir):
        assert (ar_output_dir / "account-recon-analysis.json").exists()

    def test_dashboard_file_exists(self, ar_output_dir):
        assert (ar_output_dir / "account-recon-dashboard.json").exists()

    def test_nine_dataset_files(self, ar_output_dir):
        datasets = list((ar_output_dir / "datasets").glob("qs-gen-ar-*.json"))
        assert len(datasets) == 9

    def test_all_files_valid_json(self, ar_output_dir):
        for path in ar_output_dir.rglob("*.json"):
            data = json.loads(path.read_text())
            assert isinstance(data, dict), f"{path} is not a JSON object"

    def test_resources_tagged_managed_by(self, ar_output_dir):
        for path in ar_output_dir.rglob("*.json"):
            data = json.loads(path.read_text())
            keys = {t["Key"] for t in data.get("Tags", [])}
            assert "ManagedBy" in keys, f"{path.name} missing ManagedBy tag"


class TestCrossReferences:
    """Visuals, filters, and dataset declarations must all tie together."""

    def test_dataset_refs_declared(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        defn = analysis["Definition"]
        declared = {d["Identifier"] for d in defn["DataSetIdentifierDeclarations"]}
        refs: set[str] = set()
        _collect_dataset_refs(analysis, refs)
        for ref in refs:
            assert ref in declared, f"Undeclared dataset ref: {ref}"

    def test_dataset_arns_match_generated(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        decls = analysis["Definition"]["DataSetIdentifierDeclarations"]
        declared_ids = {d["DataSetArn"].split("/")[-1] for d in decls}
        on_disk = {
            json.loads(p.read_text())["DataSetId"]
            for p in (ar_output_dir / "datasets").glob("qs-gen-ar-*.json")
        }
        assert declared_ids.issubset(on_disk), (
            f"Missing datasets on disk: {declared_ids - on_disk}"
        )

    def test_visual_ids_unique(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        ids = []
        for sheet in analysis["Definition"]["Sheets"]:
            for v in sheet.get("Visuals", []):
                for vtype in v.values():
                    if isinstance(vtype, dict) and "VisualId" in vtype:
                        ids.append(vtype["VisualId"])
        assert len(ids) == len(set(ids)), (
            f"Duplicate visual IDs: "
            f"{sorted([vid for vid in ids if ids.count(vid) > 1])}"
        )

    def test_filter_scope_sheet_ids_exist(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        defn = analysis["Definition"]
        real_sheet_ids = {s["SheetId"] for s in defn["Sheets"]}
        for fg in defn.get("FilterGroups", []):
            scope = fg["ScopeConfiguration"]
            if "SelectedSheets" in scope:
                for svc in scope["SelectedSheets"]["SheetVisualScopingConfigurations"]:
                    assert svc["SheetId"] in real_sheet_ids, (
                        f"Filter group {fg['FilterGroupId']} scopes to "
                        f"unknown sheet {svc['SheetId']}"
                    )

    def test_filter_controls_reference_real_filter_ids(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        defn = analysis["Definition"]
        all_filter_ids: set[str] = set()
        for fg in defn.get("FilterGroups", []):
            for f in fg["Filters"]:
                for filter_obj in f.values():
                    if isinstance(filter_obj, dict) and "FilterId" in filter_obj:
                        all_filter_ids.add(filter_obj["FilterId"])
        for sheet in defn["Sheets"]:
            for ctrl in sheet.get("FilterControls", []):
                for ctrl_obj in ctrl.values():
                    if isinstance(ctrl_obj, dict) and "SourceFilterId" in ctrl_obj:
                        src = ctrl_obj["SourceFilterId"]
                        assert src in all_filter_ids, (
                            f"Control references unknown filter '{src}'"
                        )


class TestSheetLayout:
    """Phase 3: five sheets, Getting Started at index 0, expected visual counts."""

    def test_five_sheets(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        assert len(analysis["Definition"]["Sheets"]) == 5

    def test_sheet_order(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        ids = [s["SheetId"] for s in analysis["Definition"]["Sheets"]]
        assert ids == [
            SHEET_AR_GETTING_STARTED,
            SHEET_AR_BALANCES,
            SHEET_AR_TRANSFERS,
            SHEET_AR_TRANSACTIONS,
            SHEET_AR_EXCEPTIONS,
        ]

    def test_balances_visual_count(self, ar_output_dir):
        self._assert_visual_count(ar_output_dir, SHEET_AR_BALANCES, 4)

    def test_transfers_visual_count(self, ar_output_dir):
        # Phase 4: added Transfer Status bar chart -> 4
        self._assert_visual_count(ar_output_dir, SHEET_AR_TRANSFERS, 4)

    def test_transactions_visual_count(self, ar_output_dir):
        # Phase 4: added Transactions-by-day bar chart -> 5
        self._assert_visual_count(ar_output_dir, SHEET_AR_TRANSACTIONS, 5)

    def test_exceptions_visual_count(self, ar_output_dir):
        # Phase 5: five independent checks (three drift KPIs + breach +
        # overdraft) → 5 KPIs + 5 tables + 2 timelines = 12.
        self._assert_visual_count(ar_output_dir, SHEET_AR_EXCEPTIONS, 12)

    def _assert_visual_count(self, out_dir: Path, sheet_id: str, expected: int) -> None:
        analysis = _load(out_dir, "account-recon-analysis.json")
        sheet = next(
            s for s in analysis["Definition"]["Sheets"]
            if s["SheetId"] == sheet_id
        )
        assert len(sheet["Visuals"]) == expected


class TestGettingStartedSheet:
    def test_at_index_zero(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        gs = analysis["Definition"]["Sheets"][0]
        assert gs["SheetId"] == SHEET_AR_GETTING_STARTED
        assert gs["Name"] == "Getting Started"

    def test_has_tab_text_blocks(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        gs = analysis["Definition"]["Sheets"][0]
        ids = {tb["SheetTextBoxId"] for tb in gs.get("TextBoxes", [])}
        for expected in (
            "ar-gs-welcome",
            "ar-gs-balances",
            "ar-gs-transfers",
            "ar-gs-transactions",
            "ar-gs-exceptions",
        ):
            assert expected in ids, f"Missing text block {expected}"

    def test_no_visuals_or_filters(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        gs = analysis["Definition"]["Sheets"][0]
        assert not gs.get("Visuals")
        assert not gs.get("FilterControls")

    def test_non_demo_omits_demo_flavor(self, ar_output_dir):
        """The default-config fixture has no demo_database_url, so no flavor."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        gs = analysis["Definition"]["Sheets"][0]
        ids = {tb["SheetTextBoxId"] for tb in gs.get("TextBoxes", [])}
        assert "ar-gs-demo-flavor" not in ids


class TestExplanations:
    def test_every_sheet_has_description(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        for sheet in analysis["Definition"]["Sheets"]:
            desc = sheet.get("Description", "")
            assert len(desc) > 20, f"Sheet {sheet['SheetId']} missing description"

    def test_every_visual_has_subtitle(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        for sheet in analysis["Definition"]["Sheets"]:
            for v in sheet.get("Visuals", []):
                for vtype in v.values():
                    if isinstance(vtype, dict) and "VisualId" in vtype:
                        text = (
                            vtype.get("Subtitle", {})
                                 .get("FormatText", {})
                                 .get("PlainText", "")
                        )
                        assert len(text) > 10, (
                            f"Visual {vtype['VisualId']} on sheet "
                            f"{sheet['SheetId']} missing subtitle"
                        )


def _find_visual(analysis: dict, visual_id: str) -> dict:
    for sheet in analysis["Definition"]["Sheets"]:
        for v in sheet.get("Visuals", []):
            for vtype in v.values():
                if isinstance(vtype, dict) and vtype.get("VisualId") == visual_id:
                    return vtype
    raise AssertionError(f"Visual {visual_id} not found")


def _find_fg(analysis: dict, fg_id: str) -> dict:
    for fg in analysis["Definition"]["FilterGroups"]:
        if fg["FilterGroupId"] == fg_id:
            return fg
    raise AssertionError(f"Filter group {fg_id} not found")


def _find_sheet(analysis: dict, sheet_id: str) -> dict:
    for s in analysis["Definition"]["Sheets"]:
        if s["SheetId"] == sheet_id:
            return s
    raise AssertionError(f"Sheet {sheet_id} not found")


class TestFilterGroups:
    """Shared date-range + 6 multi-selects + 4 Show-Only toggles +
    5 drill-down parameter filters = 16 filter groups."""

    _EXPECTED_IDS = {
        "fg-ar-date-range",
        "fg-ar-ledger-account",
        "fg-ar-subledger-account",
        "fg-ar-transfer-status",
        "fg-ar-transaction-status",
        "fg-ar-transfer-type",
        "fg-ar-posting-level",
        "fg-ar-balances-ledger-drift",
        "fg-ar-balances-subledger-drift",
        "fg-ar-balances-overdraft",
        "fg-ar-transactions-failed",
        "fg-ar-drill-subledger-on-txn",
        "fg-ar-drill-transfer-on-txn",
        "fg-ar-drill-ledger-on-balances-subledger",
        "fg-ar-drill-activity-date-on-txn",
        "fg-ar-drill-transfer-type-on-txn",
    }

    def test_filter_group_ids(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        ids = {fg["FilterGroupId"] for fg in analysis["Definition"]["FilterGroups"]}
        assert ids == self._EXPECTED_IDS

    def test_date_range_scopes_four_tabs(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, "fg-ar-date-range")
        scopes = fg["ScopeConfiguration"]["SelectedSheets"][
            "SheetVisualScopingConfigurations"
        ]
        sheet_ids = {s["SheetId"] for s in scopes}
        assert sheet_ids == {
            SHEET_AR_BALANCES,
            SHEET_AR_TRANSFERS,
            SHEET_AR_TRANSACTIONS,
            SHEET_AR_EXCEPTIONS,
        }

    @pytest.mark.parametrize(
        "fg_id",
        [
            "fg-ar-ledger-account",
            "fg-ar-subledger-account",
            "fg-ar-transfer-type",
        ],
    )
    def test_cross_tab_multi_select_has_default_dropdown(
        self, ar_output_dir, fg_id: str,
    ):
        """Cross-tab (ALL_DATASETS) multi-selects declare a MULTI_SELECT
        default dropdown so the CrossSheet controls on each tab inherit it."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, fg_id)
        cf = fg["Filters"][0]["CategoryFilter"]
        ctrl = (
            cf["DefaultFilterControlConfiguration"]["ControlOptions"]
            ["DefaultDropdownOptions"]
        )
        assert ctrl["Type"] == "MULTI_SELECT"

    @pytest.mark.parametrize(
        "fg_id",
        ["fg-ar-transfer-status", "fg-ar-transaction-status"],
    )
    def test_single_dataset_multi_select_omits_default_control(
        self, ar_output_dir, fg_id: str,
    ):
        """SINGLE_DATASET CategoryFilters with a direct (non-CrossSheet)
        Dropdown on the same sheet must NOT declare
        DefaultFilterControlConfiguration — AWS rejects CreateAnalysis
        otherwise (same rule documented in payment_recon/filters.py)."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, fg_id)
        cf = fg["Filters"][0]["CategoryFilter"]
        assert "DefaultFilterControlConfiguration" not in cf

    @pytest.mark.parametrize(
        "fg_id, sheet_id",
        [
            ("fg-ar-balances-ledger-drift", SHEET_AR_BALANCES),
            ("fg-ar-balances-subledger-drift", SHEET_AR_BALANCES),
            ("fg-ar-balances-overdraft", SHEET_AR_BALANCES),
            ("fg-ar-transactions-failed", SHEET_AR_TRANSACTIONS),
        ],
    )
    def test_show_only_toggle_scoped_to_single_sheet(
        self, ar_output_dir, fg_id: str, sheet_id: str,
    ):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, fg_id)
        scopes = fg["ScopeConfiguration"]["SelectedSheets"][
            "SheetVisualScopingConfigurations"
        ]
        assert [s["SheetId"] for s in scopes] == [sheet_id]
        assert fg["CrossDataset"] == "SINGLE_DATASET"


class TestParameterDeclarations:
    """Phase 5 drill-downs rely on five single-valued string parameters."""

    def test_five_parameters(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        params = analysis["Definition"]["ParameterDeclarations"]
        names = {p["StringParameterDeclaration"]["Name"] for p in params}
        assert names == {
            "pArSubledgerAccountId",
            "pArLedgerAccountId",
            "pArTransferId",
            "pArActivityDate",
            "pArTransferType",
        }

    def test_parameters_single_valued(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        for p in analysis["Definition"]["ParameterDeclarations"]:
            decl = p["StringParameterDeclaration"]
            assert decl["ParameterValueType"] == "SINGLE_VALUED"


class TestDrillDownFilterGroups:
    """The five drill-down filter groups bind parameters to target columns."""

    def _cfg(self, fg: dict) -> dict:
        return fg["Filters"][0]["CategoryFilter"]["Configuration"][
            "CustomFilterConfiguration"
        ]

    @pytest.mark.parametrize(
        "fg_id, parameter_name, column_name, sheet_id",
        [
            (
                "fg-ar-drill-subledger-on-txn",
                "pArSubledgerAccountId",
                "subledger_account_id",
                SHEET_AR_TRANSACTIONS,
            ),
            (
                "fg-ar-drill-transfer-on-txn",
                "pArTransferId",
                "transfer_id",
                SHEET_AR_TRANSACTIONS,
            ),
            (
                "fg-ar-drill-activity-date-on-txn",
                "pArActivityDate",
                "posted_date",
                SHEET_AR_TRANSACTIONS,
            ),
            (
                "fg-ar-drill-transfer-type-on-txn",
                "pArTransferType",
                "transfer_type",
                SHEET_AR_TRANSACTIONS,
            ),
            (
                "fg-ar-drill-ledger-on-balances-subledger",
                "pArLedgerAccountId",
                "ledger_account_id",
                SHEET_AR_BALANCES,
            ),
        ],
    )
    def test_drill_filter_binding(
        self,
        ar_output_dir,
        fg_id: str,
        parameter_name: str,
        column_name: str,
        sheet_id: str,
    ):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, fg_id)
        cfg = self._cfg(fg)
        assert cfg["MatchOperator"] == "EQUALS"
        assert cfg["ParameterName"] == parameter_name
        col = fg["Filters"][0]["CategoryFilter"]["Column"]
        assert col["ColumnName"] == column_name
        scopes = fg["ScopeConfiguration"]["SelectedSheets"][
            "SheetVisualScopingConfigurations"
        ]
        assert [s["SheetId"] for s in scopes] == [sheet_id]

    def test_ledger_drill_targets_subledger_table_only(self, ar_output_dir):
        """The Balances ledger-to-subledger drill must not wipe the ledger
        table; it's scoped to the sub-ledger table visual only via
        SELECTED_VISUALS."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, "fg-ar-drill-ledger-on-balances-subledger")
        scope = fg["ScopeConfiguration"]["SelectedSheets"][
            "SheetVisualScopingConfigurations"
        ][0]
        assert scope["Scope"] == "SELECTED_VISUALS"
        assert scope["VisualIds"] == ["ar-balances-subledger-table"]


def _drill_nav_target(visual: dict) -> str:
    for op in visual["Actions"][0]["ActionOperations"]:
        if "NavigationOperation" in op:
            return op["NavigationOperation"]["LocalNavigationConfiguration"][
                "TargetSheetId"
            ]
    raise AssertionError("No navigation operation found")


def _set_param(visual: dict) -> tuple[str, str]:
    for op in visual["Actions"][0]["ActionOperations"]:
        if "SetParametersOperation" in op:
            pvc = op["SetParametersOperation"][
                "ParameterValueConfigurations"
            ][0]
            return pvc["DestinationParameterName"], pvc["Value"]["SourceField"]
    raise AssertionError("No set-parameter operation found")


def _set_params_all(visual: dict) -> list[tuple[str, str]]:
    """Return every (destination_parameter, source_field) emitted by the
    action's SetParametersOperation, preserving declaration order."""
    for op in visual["Actions"][0]["ActionOperations"]:
        if "SetParametersOperation" in op:
            return [
                (pvc["DestinationParameterName"], pvc["Value"]["SourceField"])
                for pvc in op["SetParametersOperation"][
                    "ParameterValueConfigurations"
                ]
            ]
    raise AssertionError("No set-parameter operation found")


def _same_sheet_targets(visual: dict) -> list[str]:
    filt = visual["Actions"][0]["ActionOperations"][0]["FilterOperation"]
    return filt["TargetVisualsConfiguration"][
        "SameSheetTargetVisualConfiguration"
    ]["TargetVisuals"]


class TestVisualActions:
    """Drill-downs and same-sheet chart filters attach to the right visuals."""

    def test_balances_ledger_right_click_sets_ledger_parameter(self, ar_output_dir):
        """Right-click filters the sub-ledger table on the same sheet via
        the pArLedgerAccountId parameter. AWS rejects a
        SetParametersOperation that isn't preceded by a
        NavigationOperation, so the action includes a no-op navigation
        back to the Balances sheet."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-balances-ledger-table")
        action = v["Actions"][0]
        assert action["Trigger"] == "DATA_POINT_MENU"
        assert _drill_nav_target(v) == SHEET_AR_BALANCES
        assert _set_param(v) == ("pArLedgerAccountId", "ar-bal-ledger-id")

    def test_balances_subledger_drills_to_transactions(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-balances-subledger-table")
        assert v["Actions"][0]["Trigger"] == "DATA_POINT_CLICK"
        assert _drill_nav_target(v) == SHEET_AR_TRANSACTIONS
        assert _set_param(v) == ("pArSubledgerAccountId", "ar-bal-subledger-id")

    def test_transfers_summary_drills_to_transactions(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-transfers-summary-table")
        assert _drill_nav_target(v) == SHEET_AR_TRANSACTIONS
        assert _set_param(v) == ("pArTransferId", "ar-xfr-id")

    @pytest.mark.parametrize(
        "source_visual, target_visual",
        [
            ("ar-transfers-bar-status", "ar-transfers-summary-table"),
            ("ar-txn-bar-by-status", "ar-txn-detail-table"),
            ("ar-txn-bar-by-day", "ar-txn-detail-table"),
        ],
    )
    def test_chart_filters_same_sheet_table(
        self, ar_output_dir, source_visual: str, target_visual: str,
    ):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, source_visual)
        assert _same_sheet_targets(v) == [target_visual]

    @pytest.mark.parametrize(
        "visual_id, target_sheet, parameter_name, source_field",
        [
            (
                "ar-exc-ledger-drift-table",
                SHEET_AR_BALANCES,
                "pArLedgerAccountId",
                "ar-exc-ldrift-ledger-id",
            ),
            (
                "ar-exc-subledger-drift-table",
                SHEET_AR_TRANSACTIONS,
                "pArSubledgerAccountId",
                "ar-exc-sdrift-subledger-id",
            ),
            (
                "ar-exc-nonzero-table",
                SHEET_AR_TRANSACTIONS,
                "pArTransferId",
                "ar-exc-nz-id",
            ),
        ],
    )
    def test_exceptions_tables_drill_to_correct_tab(
        self,
        ar_output_dir,
        visual_id: str,
        target_sheet: str,
        parameter_name: str,
        source_field: str,
    ):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, visual_id)
        assert _drill_nav_target(v) == target_sheet
        assert _set_param(v) == (parameter_name, source_field)

    def test_breach_drill_sets_subledger_date_and_type(self, ar_output_dir):
        """Limit-breach row → Transactions (sub-ledger, day, type) slice.

        The breach table's three-parameter drill narrows Transactions to
        the exact (sub-ledger, activity_date, transfer_type) that
        breached the limit — a two-param drill would leave type open and
        bury the signal in unrelated same-sub-ledger rows."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-exc-breach-table")
        assert _drill_nav_target(v) == SHEET_AR_TRANSACTIONS
        assert _set_params_all(v) == [
            ("pArSubledgerAccountId", "ar-exc-br-subledger-id"),
            ("pArActivityDate", "ar-exc-br-date-str"),
            ("pArTransferType", "ar-exc-br-type"),
        ]

    def test_overdraft_drill_sets_subledger_and_date(self, ar_output_dir):
        """Overdraft row → Transactions (sub-ledger, day). Transfer-type
        isn't relevant — overdraft is the sum of legs regardless of
        type."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-exc-overdraft-table")
        assert _drill_nav_target(v) == SHEET_AR_TRANSACTIONS
        assert _set_params_all(v) == [
            ("pArSubledgerAccountId", "ar-exc-od-subledger-id"),
            ("pArActivityDate", "ar-exc-od-date-str"),
        ]


def _cf_cells(visual: dict) -> list[dict]:
    opts = visual.get("ConditionalFormatting", {}).get(
        "ConditionalFormattingOptions", []
    )
    return [o["Cell"] for o in opts if "Cell" in o]


class TestConditionalFormatting:
    """Drill-source cells are styled so the click affordance is visible."""

    @pytest.mark.parametrize(
        "visual_id, field_id",
        [
            ("ar-balances-subledger-table", "ar-bal-subledger-id"),
            ("ar-transfers-summary-table", "ar-xfr-id"),
            ("ar-exc-ledger-drift-table", "ar-exc-ldrift-ledger-id"),
            ("ar-exc-subledger-drift-table", "ar-exc-sdrift-subledger-id"),
            ("ar-exc-nonzero-table", "ar-exc-nz-id"),
            ("ar-exc-breach-table", "ar-exc-br-subledger-id"),
            ("ar-exc-overdraft-table", "ar-exc-od-subledger-id"),
        ],
    )
    def test_left_click_drill_sources_have_link_format(
        self, ar_output_dir, visual_id: str, field_id: str,
    ):
        """Left-click drill-source cells get plain-accent TextColor (no
        background tint — that's reserved for right-click menu cells)."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, visual_id)
        cells = [c for c in _cf_cells(v) if c["FieldId"] == field_id]
        assert cells, (
            f"{visual_id} missing conditional formatting for {field_id}"
        )
        tf = cells[0]["TextFormat"]
        assert "TextColor" in tf
        assert "BackgroundColor" not in tf

    def test_balances_ledger_right_click_uses_menu_format(self, ar_output_dir):
        """Right-click (DATA_POINT_MENU) cells get an accent+tint style —
        distinguishing them from the plain-accent left-click cells."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-balances-ledger-table")
        cells = [
            c for c in _cf_cells(v) if c["FieldId"] == "ar-bal-ledger-id"
        ]
        assert cells
        tf = cells[0]["TextFormat"]
        assert "TextColor" in tf
        assert "BackgroundColor" in tf


class TestShowOnlyToggleControls:
    """Each Show-Only-X toggle renders as a SINGLE_SELECT dropdown on the
    right sheet with an explicit 'Show Only …' title."""

    def _single_select_titles(self, sheet: dict) -> dict[str, str]:
        titles: dict[str, str] = {}
        for ctrl in sheet.get("FilterControls", []):
            for ctrl_obj in ctrl.values():
                if (
                    isinstance(ctrl_obj, dict)
                    and ctrl_obj.get("Type") == "SINGLE_SELECT"
                ):
                    titles[ctrl_obj["FilterControlId"]] = ctrl_obj["Title"]
        return titles

    def test_balances_has_drift_and_overdraft_toggles(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        sheet = _find_sheet(analysis, SHEET_AR_BALANCES)
        titles = self._single_select_titles(sheet)
        assert titles.get("ctrl-ar-balances-ledger-drift") == (
            "Show Only Ledger Drift"
        )
        assert titles.get("ctrl-ar-balances-subledger-drift") == (
            "Show Only Sub-Ledger Drift"
        )
        assert titles.get("ctrl-ar-balances-overdraft") == (
            "Show Only Overdraft"
        )

    def test_transfers_has_no_toggle(self, ar_output_dir):
        """Transfer Status multi-select already covers net-zero filtering;
        no separate Show-Only-Unhealthy toggle."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        sheet = _find_sheet(analysis, SHEET_AR_TRANSFERS)
        assert self._single_select_titles(sheet) == {}

    def test_transactions_has_failed_toggle(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        sheet = _find_sheet(analysis, SHEET_AR_TRANSACTIONS)
        titles = self._single_select_titles(sheet)
        assert titles.get("ctrl-ar-transactions-failed") == (
            "Show Only Failed"
        )

    def test_exceptions_has_no_toggle(self, ar_output_dir):
        """Exceptions sheet is already the "problems only" sheet — no need
        for another 'Show Only …' layer."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        sheet = _find_sheet(analysis, SHEET_AR_EXCEPTIONS)
        assert self._single_select_titles(sheet) == {}


class TestTransferTypeControl:
    """Phase 5.5 transfer-type filter surfaces as a CrossSheet control on
    Transfers / Transactions / Exceptions; Balances has no transfer_type
    column in scope so the control would dangle there."""

    def _cross_sheet_sources(self, sheet: dict) -> set[str]:
        sources: set[str] = set()
        for ctrl in sheet.get("FilterControls", []):
            cs = ctrl.get("CrossSheet")
            if cs:
                sources.add(cs["SourceFilterId"])
        return sources

    @pytest.mark.parametrize(
        "sheet_id",
        [SHEET_AR_TRANSFERS, SHEET_AR_TRANSACTIONS, SHEET_AR_EXCEPTIONS],
    )
    def test_transfer_type_control_present(self, ar_output_dir, sheet_id: str):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        sheet = _find_sheet(analysis, sheet_id)
        assert "filter-ar-transfer-type" in self._cross_sheet_sources(sheet)

    def test_transfer_type_absent_from_balances(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        sheet = _find_sheet(analysis, SHEET_AR_BALANCES)
        assert "filter-ar-transfer-type" not in self._cross_sheet_sources(sheet)


class TestPhase5DatasetDeclarations:
    """The two Phase 5 reconciliation datasets must be declared and backed
    by generated JSON on disk."""

    @pytest.mark.parametrize(
        "identifier, id_suffix",
        [
            ("ar-limit-breach-ds", "qs-gen-ar-limit-breach-dataset"),
            ("ar-overdraft-ds", "qs-gen-ar-overdraft-dataset"),
        ],
    )
    def test_declared_and_on_disk(
        self, ar_output_dir, identifier: str, id_suffix: str,
    ):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        decls = analysis["Definition"]["DataSetIdentifierDeclarations"]
        ids = {d["Identifier"] for d in decls}
        assert identifier in ids
        assert (ar_output_dir / "datasets" / f"{id_suffix}.json").exists()

    def test_subledger_drift_dataset_has_overdraft_status(self, ar_output_dir):
        """The Show-Only-Overdraft toggle binds to
        subledger_balance_drift.overdraft_status — verify the derived
        column is emitted in the dataset's InputColumns and SELECT."""
        path = ar_output_dir / "datasets" / (
            "qs-gen-ar-subledger-balance-drift-dataset.json"
        )
        data = json.loads(path.read_text())
        table = next(iter(data["PhysicalTableMap"].values()))
        cols = {c["Name"] for c in table["CustomSql"]["Columns"]}
        assert "overdraft_status" in cols
        assert "overdraft_status" in table["CustomSql"]["SqlQuery"]

    def test_transactions_dataset_projects_origin(self, ar_output_dir):
        """The Transactions dataset must expose origin from the transfer table."""
        path = ar_output_dir / "datasets" / "qs-gen-ar-transactions-dataset.json"
        data = json.loads(path.read_text())
        table = next(iter(data["PhysicalTableMap"].values()))
        cols = {c["Name"] for c in table["CustomSql"]["Columns"]}
        assert "origin" in cols
        assert "xfer.origin" in table["CustomSql"]["SqlQuery"]


# ---------------------------------------------------------------------------
# Analysis name driven by theme preset
# ---------------------------------------------------------------------------

class TestAnalysisName:
    def _cfg(self, preset: str) -> Config:
        return Config(
            aws_account_id="111122223333",
            aws_region="us-west-2",
            datasource_arn="arn:aws:quicksight:us-west-2:111122223333:datasource/ds",
            theme_preset=preset,
        )

    def test_default_name(self):
        from quicksight_gen.account_recon.analysis import build_analysis

        name = build_analysis(self._cfg("default")).Name
        assert name == "Account Reconciliation"

    def test_farmers_exchange_name(self):
        from quicksight_gen.account_recon.analysis import build_analysis

        name = build_analysis(self._cfg("farmers-exchange-bank")).Name
        assert name == "Demo — Account Reconciliation"


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------

class TestCli:
    def _base_config(self, tmp_path: Path) -> Path:
        p = tmp_path / "config.yaml"
        p.write_text(
            "aws_account_id: '111122223333'\n"
            "aws_region: us-west-2\n"
            "datasource_arn: arn:aws:quicksight:us-west-2:111122223333:datasource/ds\n"
        )
        return p

    def test_generate_account_recon(self, tmp_path: Path):
        config = self._base_config(tmp_path)
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            main, ["generate", "-c", str(config), "-o", str(out), "account-recon"],
        )
        assert result.exit_code == 0, result.output
        assert (out / "account-recon-analysis.json").exists()

    def test_generate_all_produces_both(self, tmp_path: Path):
        config = self._base_config(tmp_path)
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            main, ["generate", "-c", str(config), "-o", str(out), "--all"],
        )
        assert result.exit_code == 0, result.output
        assert (out / "payment-recon-analysis.json").exists()
        assert (out / "account-recon-analysis.json").exists()

    def test_generate_single_app_preserves_sibling_datasets(self, tmp_path: Path):
        """Running generate for only one app must not delete the other's
        dataset files that already exist in ``out/datasets``."""
        config = self._base_config(tmp_path)
        out = tmp_path / "out"
        runner = CliRunner()
        # First: --all to populate both sets.
        r1 = runner.invoke(
            main, ["generate", "-c", str(config), "-o", str(out), "--all"],
        )
        assert r1.exit_code == 0, r1.output
        before_pr = list((out / "datasets").glob("qs-gen-merchants*.json"))
        assert before_pr, "payment-recon datasets missing after --all"

        # Then: regenerate only account-recon.
        r2 = runner.invoke(
            main, ["generate", "-c", str(config), "-o", str(out), "account-recon"],
        )
        assert r2.exit_code == 0, r2.output
        after_pr = list((out / "datasets").glob("qs-gen-merchants*.json"))
        assert after_pr, "payment-recon datasets wiped by account-recon generate"

    def test_demo_seed_account_recon(self, tmp_path: Path):
        out = tmp_path / "seed.sql"
        runner = CliRunner()
        result = runner.invoke(
            main, ["demo", "seed", "account-recon", "-o", str(out)],
        )
        assert result.exit_code == 0, result.output
        assert "INSERT INTO ar_ledger_accounts" in out.read_text()

    def test_demo_seed_all_includes_both(self, tmp_path: Path):
        out = tmp_path / "seed.sql"
        runner = CliRunner()
        result = runner.invoke(
            main, ["demo", "seed", "--all", "-o", str(out)],
        )
        assert result.exit_code == 0, result.output
        content = out.read_text()
        assert "INSERT INTO pr_merchants" in content
        assert "INSERT INTO ar_ledger_accounts" in content
