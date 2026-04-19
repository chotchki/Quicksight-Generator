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
        # + 5 funding batches (1 ledger + N sub-ledger legs each;
        #   N is 6 or 7 in the SNB structure depending on which
        #   eligible ledger the batch picks)
        # + 3 fee assessments (1 ledger leg each)
        # + 2 inter-ledger clearing sweeps (2 ledger legs each)
        # + 20 ZBA EOD sweeps × 2 legs each (1 sub-ledger + 1 ledger-direct)
        # + 2 ZBA fail-plant deposits × 2 legs each
        # + 2 ZBA mismatch-plant deposits × 2 legs each
        # + 132 ACH cycle postings (14 days × 3 originations × 2 legs each
        #   = 84; 13 EOD sweeps × 2 = 26; 11 Fed confirmations × 2 = 22)
        # + 36 card settlement postings (10 Fed observations × 2 = 20;
        #   8 internal catch-ups × 2 legs each = 16)
        # + 16 on-us internal transfer postings (5 originate × 2 = 10;
        #   2 success step-2 × 2 = 4; 1 reversal-not-credited × 2 = 2)
        # Total observed under seed=42: 410.
        assert len(unified_parsed["posting"]) == 410

    def test_transfers(self, unified_parsed):
        # 66 sub-ledger + 5 funding + 3 fee + 2 inter-ledger sweep
        # + 20 ZBA EOD sweep + 2 ZBA fail-plant deposit
        # + 2 ZBA mismatch-plant deposit
        # + 66 ACH cycle (14×3 originations + 13 EOD sweeps + 11 Fed
        #   confirmations)
        # + 18 card settlement (10 Fed observations + 8 internal catch-ups)
        # + 8 on-us internal transfers (5 originate + 2 success step-2
        #   + 1 reversal-not-credited step-2)
        # = 192
        assert len(unified_parsed["transfer"]) == 192

    def test_ledger_transfer_limits(self, ar_parsed):
        from quicksight_gen.account_recon.demo_data import _LEDGER_LIMITS
        assert (
            len(ar_parsed["ar_ledger_transfer_limits"]) == len(_LEDGER_LIMITS)
        )

    def test_ledger_daily_balances(self, ar_parsed):
        # 8 internal GL control ledgers × 41 days (0..40 inclusive) = 328 rows.
        # External counterparty ledgers are not reconciled
        # (SPEC "Reconciliation scope").
        assert len(ar_parsed["ar_ledger_daily_balances"]) == 328

    def test_subledger_daily_balances(self, ar_parsed):
        # 13 internal sub-ledgers (7 customer DDAs + 6 ZBA operating
        # sub-accounts) × 41 days = 533 rows. External counterparty
        # sub-pools are omitted.
        assert len(ar_parsed["ar_subledger_daily_balances"]) == 533


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
        limit-breach view has no thresholds to compare against.

        In the SNB structure only DDA Control carries enforced limits
        (other internal GLs are pure-control accounts; ZBA sweeps are
        uncapped) so the "≥2 ledgers" requirement from the legacy
        product-category model no longer applies.
        """
        from quicksight_gen.account_recon.demo_data import _LEDGER_LIMITS

        assert len(_LEDGER_LIMITS) >= 3, "Need ≥3 ledger limit rows"
        types = {xtype for _lid, xtype, _lim in _LEDGER_LIMITS}
        assert len(types) >= 2, "Limits must cover ≥2 transfer types"
        ledgers = {lid for lid, _x, _l in _LEDGER_LIMITS}
        assert len(ledgers) >= 1, "Need ≥1 ledger carrying limits"

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

    def test_zba_sweep_cycle_present(self, unified_parsed):
        """F.4.1: ZBA / Cash Concentration sweep transfers must exist
        with mixed-level legs (sub-ledger leg zeroes operating account,
        ledger-direct leg offsets at master). Drives the F.5.1 / F.5.2
        rollup checks."""
        from quicksight_gen.account_recon.demo_data import (
            _ZBA_SWEEP_CUSTOMERS,
        )

        # Find clearing_sweep transfers with at least one posting
        # targeting a ZBA operating sub-account.
        zba_set = set(_ZBA_SWEEP_CUSTOMERS)
        sweep_xfers: dict[str, set[str | None]] = {}
        xfer_types: dict[str, str] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            xfer_types[parts[0]] = parts[2]
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid, sub_id = parts[1], parts[3]
            if xfer_types.get(tid) == "clearing_sweep":
                sweep_xfers.setdefault(tid, set()).add(
                    None if sub_id == "NULL" else sub_id,
                )
        zba_sweeps = [
            tid for tid, subs in sweep_xfers.items()
            if subs & zba_set and None in subs
        ]
        assert len(zba_sweeps) >= 10, (
            f"Expected ≥10 ZBA sweep transfers (mixed-level), got "
            f"{len(zba_sweeps)}"
        )

    def test_zba_sweep_leg_mismatches_surface(self, unified_parsed):
        """F.5.2: leg-mismatch plants must produce ``clearing_sweep``
        transfers whose master ledger-direct leg amount differs from the
        sub-leg by exactly ``master_delta``. This is what surfaces in
        ar_concentration_master_sweep_drift as non-zero daily drift."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _ZBA_SWEEP_LEG_MISMATCH_PLANT,
        )

        xfer_types: dict[str, str] = {}
        xfer_dates: dict[str, str] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            xfer_types[parts[0]] = parts[2]
            # transfer.first_posted_at column index 6
            xfer_dates[parts[0]] = parts[6][:10]

        legs_by_xfer: dict[str, list[tuple[str | None, str | None, Decimal]]] = {}
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            # posting columns: posting_id, transfer_id, ledger_account_id,
            # subledger_account_id, signed_amount, posted_at, status
            tid = parts[1]
            ledger_id = None if parts[2] == "NULL" else parts[2]
            sub_id = None if parts[3] == "NULL" else parts[3]
            amt = Decimal(parts[4])
            legs_by_xfer.setdefault(tid, []).append((sub_id, ledger_id, amt))

        plant_dates = {
            (sub_id, (ANCHOR - timedelta(days=da)).isoformat()): Decimal(d)
            for sub_id, da, d in _ZBA_SWEEP_LEG_MISMATCH_PLANT
        }
        matched: list[tuple[str, str, Decimal]] = []
        for tid, legs in legs_by_xfer.items():
            if xfer_types.get(tid) != "clearing_sweep":
                continue
            sub_legs = [l for l in legs if l[0] is not None]
            master_legs = [
                l for l in legs
                if l[0] is None
                and l[1] == "gl-1850-cash-concentration-master"
            ]
            if len(sub_legs) != 1 or len(master_legs) != 1:
                continue
            sub_id, _, sub_amt = sub_legs[0]
            _, _, master_amt = master_legs[0]
            net = sub_amt + master_amt
            if net == 0:
                continue
            xfer_date = xfer_dates.get(tid, "")
            matched.append((sub_id, xfer_date, net))

        for (sub_id, bdate), expected_delta in plant_dates.items():
            hit = [
                (sid, bd, n) for sid, bd, n in matched
                if sid == sub_id and bd == bdate
            ]
            assert hit, (
                f"No mismatched sweep transfer found for plant "
                f"({sub_id}, {bdate})"
            )
            assert any(abs(n - expected_delta) < Decimal("0.01") for *_, n in hit), (
                f"Sweep leg mismatch for ({sub_id}, {bdate}) does not "
                f"match expected delta {expected_delta} (got {hit})"
            )

    def test_fed_card_no_internal_catchup_surfaces(self, unified_parsed):
        """F.5.5: ``_CARD_INTERNAL_MISSING_PLANT`` cells must produce
        Fed-side card settlement transfers (parent IS NULL, hitting the
        payment-gateway clearing sub-ledger) with NO SNB internal
        catch-up child. Without these, the F.5.5 view returns empty."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _CARD_INTERNAL_MISSING_PLANT,
        )

        xfer_types: dict[str, str] = {}
        xfer_origins: dict[str, str] = {}
        xfer_dates: dict[str, str] = {}
        xfer_parents: dict[str, str | None] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[0]
            xfer_parents[tid] = None if parts[1] == "NULL" else parts[1]
            xfer_types[tid] = parts[2]
            xfer_origins[tid] = parts[3]
            xfer_dates[tid] = parts[6][:10]

        fed_card_tids: set[str] = set()
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[1]
            sub_id = None if parts[3] == "NULL" else parts[3]
            if (
                xfer_types.get(tid) == "ach"
                and xfer_origins.get(tid) == "external_force_posted"
                and xfer_parents.get(tid) is None
                and sub_id == "ext-payment-gateway-sub-clearing"
            ):
                fed_card_tids.add(tid)

        feds_with_child = {
            parent for parent in xfer_parents.values()
            if parent in fed_card_tids
        }
        feds_no_child = fed_card_tids - feds_with_child
        assert feds_no_child, (
            "Expected ≥1 Fed card observation with no internal catch-up "
            "child — F.5.5 view will be empty otherwise"
        )

        fed_dates = {xfer_dates[t] for t in feds_no_child}
        for days_ago in _CARD_INTERNAL_MISSING_PLANT:
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            assert bdate in fed_dates, (
                f"Card internal-missing plant day {bdate} "
                f"(days_ago={days_ago}) must produce a Fed observation "
                f"without internal catch-up (got {fed_dates})"
            )

    def test_internal_transfer_stuck_surfaces(self, unified_parsed):
        """F.5.7: ``_INTERNAL_TRANSFER_PLANT`` rows with kind="stuck"
        must produce internal Step-1 originate transfers that hit the
        Internal Transfer Suspense ledger (gl-1830) but have NO Step-2
        child. Without these, the F.5.7 view returns empty."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _INTERNAL_TRANSFER_PLANT,
        )

        xfer_types: dict[str, str] = {}
        xfer_origins: dict[str, str] = {}
        xfer_dates: dict[str, str] = {}
        xfer_parents: dict[str, str | None] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[0]
            xfer_parents[tid] = None if parts[1] == "NULL" else parts[1]
            xfer_types[tid] = parts[2]
            xfer_origins[tid] = parts[3]
            xfer_dates[tid] = parts[6][:10]

        suspense_originate_tids: set[str] = set()
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[1]
            ledger_id = None if parts[2] == "NULL" else parts[2]
            if (
                xfer_types.get(tid) == "internal"
                and xfer_origins.get(tid) == "internal_initiated"
                and xfer_parents.get(tid) is None
                and ledger_id == "gl-1830-internal-transfer-suspense"
            ):
                suspense_originate_tids.add(tid)

        originates_with_step2 = {
            parent for parent in xfer_parents.values()
            if parent in suspense_originate_tids
        }
        stuck = suspense_originate_tids - originates_with_step2
        assert stuck, (
            "Expected ≥1 internal originate with no Step-2 child — "
            "F.5.7 view will be empty otherwise"
        )

        stuck_dates = {xfer_dates[t] for t in stuck}
        for _, _, days_ago, kind, _ in _INTERNAL_TRANSFER_PLANT:
            if kind != "stuck":
                continue
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            assert bdate in stuck_dates, (
                f"Internal stuck plant day {bdate} (days_ago={days_ago}) "
                f"must produce a Step-1 originate without Step-2 child "
                f"(got {stuck_dates})"
            )

    def test_internal_reversal_uncredited_surfaces(self, unified_parsed):
        """F.5.9: ``_INTERNAL_TRANSFER_PLANT`` rows with kind=
        "reversed_not_credited" must produce a Step 1 originate hitting
        gl-1830 plus a Step 2 child where (a) the originator-DDA leg
        failed and (b) the suspense leg posted successfully. Without
        these, the F.5.9 view returns empty."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _INTERNAL_TRANSFER_PLANT,
        )

        xfer_types: dict[str, str] = {}
        xfer_origins: dict[str, str] = {}
        xfer_dates: dict[str, str] = {}
        xfer_parents: dict[str, str | None] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[0]
            xfer_parents[tid] = None if parts[1] == "NULL" else parts[1]
            xfer_types[tid] = parts[2]
            xfer_origins[tid] = parts[3]
            xfer_dates[tid] = parts[6][:10]

        suspense_originate_tids: set[str] = set()
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[1]
            ledger_id = None if parts[2] == "NULL" else parts[2]
            if (
                xfer_types.get(tid) == "internal"
                and xfer_origins.get(tid) == "internal_initiated"
                and xfer_parents.get(tid) is None
                and ledger_id == "gl-1830-internal-transfer-suspense"
            ):
                suspense_originate_tids.add(tid)

        step2_legs: dict[str, list[tuple[str | None, str | None, str]]] = {}
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[1]
            parent = xfer_parents.get(tid)
            if parent not in suspense_originate_tids:
                continue
            ledger_id = None if parts[2] == "NULL" else parts[2]
            sub_id = None if parts[3] == "NULL" else parts[3]
            status = parts[6]
            step2_legs.setdefault(tid, []).append((ledger_id, sub_id, status))

        uncredited_originates: set[str] = set()
        for step2_tid, legs in step2_legs.items():
            has_failed_dda = any(
                sub_id is not None and status == "failed"
                for _, sub_id, status in legs
            )
            has_success_suspense = any(
                ledger_id == "gl-1830-internal-transfer-suspense"
                and sub_id is None
                and status == "success"
                for ledger_id, sub_id, status in legs
            )
            if has_failed_dda and has_success_suspense:
                uncredited_originates.add(xfer_parents[step2_tid])

        assert uncredited_originates, (
            "Expected ≥1 reversed-but-not-credited cycle — F.5.9 view "
            "will be empty otherwise"
        )

        uncredited_dates = {xfer_dates[t] for t in uncredited_originates}
        for _, _, days_ago, kind, _ in _INTERNAL_TRANSFER_PLANT:
            if kind != "reversed_not_credited":
                continue
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            assert bdate in uncredited_dates, (
                f"Reversed-not-credited plant day {bdate} "
                f"(days_ago={days_ago}) must produce an uncredited "
                f"reversal cycle (got {uncredited_dates})"
            )

    def test_internal_suspense_nonzero_eod_surfaces(self, ar_parsed):
        """F.5.8: ``_INTERNAL_TRANSFER_PLANT`` rows with kind="stuck"
        leave the gl-1830 ledger stored EOD balance non-zero from the
        plant date forward (each stuck originate accumulates). Without
        at least one non-zero day, the F.5.8 view returns empty."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _INTERNAL_TRANSFER_PLANT,
        )

        balances: dict[str, Decimal] = {}
        for row in ar_parsed["ar_ledger_daily_balances"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            if parts[0] != "gl-1830-internal-transfer-suspense":
                continue
            balances[parts[1]] = Decimal(parts[2])

        nonzero = [(d, b) for d, b in balances.items() if b != 0]
        assert nonzero, (
            "Expected ≥1 non-zero EOD on gl-1830 from "
            "_INTERNAL_TRANSFER_PLANT stuck rows — F.5.8 view will be "
            "empty otherwise"
        )

        for _, _, days_ago, kind, _ in _INTERNAL_TRANSFER_PLANT:
            if kind != "stuck":
                continue
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            bal = balances.get(bdate)
            assert bal is not None and bal != 0, (
                f"Stuck plant day {bdate} (days_ago={days_ago}) should "
                f"be non-zero EOD on gl-1830 (got {bal})"
            )

    def test_ach_sweep_no_fed_confirmation_surfaces(self, unified_parsed):
        """F.5.4: ``_ACH_FED_CONFIRMATION_MISSING`` cells must produce
        clearing_sweep transfers on gl-1810 with NO Fed confirmation
        child transfer. Without these, the F.5.4 view returns empty."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _ACH_FED_CONFIRMATION_MISSING,
        )

        xfer_types: dict[str, str] = {}
        xfer_dates: dict[str, str] = {}
        parents: dict[str, str | None] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[0]
            parent = None if parts[1] == "NULL" else parts[1]
            xfer_types[tid] = parts[2]
            xfer_dates[tid] = parts[6][:10]
            parents[tid] = parent

        ach_sweep_tids: set[str] = set()
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[1]
            ledger_id = None if parts[2] == "NULL" else parts[2]
            if (
                xfer_types.get(tid) == "clearing_sweep"
                and ledger_id == "gl-1810-ach-orig-settlement"
            ):
                ach_sweep_tids.add(tid)

        sweeps_with_fed_child = {
            parent for parent in parents.values()
            if parent in ach_sweep_tids
        }
        sweeps_no_fed = ach_sweep_tids - sweeps_with_fed_child
        assert sweeps_no_fed, (
            "Expected ≥1 ACH sweep without Fed confirmation child — "
            "F.5.4 view will be empty otherwise"
        )

        sweep_dates_no_fed = {xfer_dates[t] for t in sweeps_no_fed}
        for days_ago in _ACH_FED_CONFIRMATION_MISSING:
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            assert bdate in sweep_dates_no_fed, (
                f"ACH Fed-confirmation-missing plant day {bdate} "
                f"(days_ago={days_ago}) must produce a sweep without "
                f"a Fed confirmation child (got dates {sweep_dates_no_fed})"
            )

    def test_ach_orig_settlement_skip_surfaces(self, ar_parsed):
        """F.5.3: ``_ACH_SWEEP_SKIP_PLANT`` cells must drive the
        gl-1810 ledger stored EOD balance non-zero from the plant date
        forward (the missed sweep accumulates). Without at least one
        non-zero day, the F.5.3 view returns empty."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _ACH_SWEEP_SKIP_PLANT,
        )

        balances: dict[str, Decimal] = {}
        for row in ar_parsed["ar_ledger_daily_balances"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            if parts[0] != "gl-1810-ach-orig-settlement":
                continue
            balances[parts[1]] = Decimal(parts[2])

        nonzero = [(d, b) for d, b in balances.items() if b != 0]
        assert nonzero, (
            "Expected ≥1 non-zero EOD on gl-1810 from "
            "_ACH_SWEEP_SKIP_PLANT — F.5.3 view will be empty otherwise"
        )

        for days_ago in _ACH_SWEEP_SKIP_PLANT:
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            bal = balances.get(bdate)
            assert bal is not None and bal != 0, (
                f"ACH sweep-skip plant day {bdate} (days_ago={days_ago}) "
                f"should be non-zero EOD on gl-1810 (got {bal})"
            )

    def test_zba_sweep_failures_surface(self, ar_parsed):
        """F.4.1 fail-plant cells must drive the operating sub-account's
        stored EOD balance non-zero — that's what F.5.1 surfaces. Cells
        with sweep skipped + a planted deposit will end day at the plant
        amount (or larger if random activity also hit)."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _ZBA_SWEEP_FAIL_PLANT,
        )

        balances: dict[tuple[str, str], Decimal] = {}
        for row in ar_parsed["ar_subledger_daily_balances"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            balances[(parts[0], parts[1])] = Decimal(parts[2])

        for sub_id, days_ago in _ZBA_SWEEP_FAIL_PLANT:
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            bal = balances.get((sub_id, bdate))
            assert bal is not None and bal != 0, (
                f"ZBA sweep fail plant ({sub_id}, {bdate}) should be "
                f"non-zero EOD (got {bal})"
            )

    def test_zba_swept_accounts_zero_on_normal_days(self, ar_parsed):
        """ZBA-customer operating sub-accounts must be at zero EOD on
        days that are NOT fail-plant days — confirms the sweep is
        actually zeroing them out, otherwise F.5.1 would surface
        false-positive 'all days are non-zero' findings.

        Allows two known exceptions: the fail-plant cells and any
        sub-ledger drift plant cells that intentionally inject a delta
        into the stored balance.
        """
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _ZBA_SWEEP_CUSTOMERS,
            _ZBA_SWEEP_FAIL_PLANT,
            _SUBLEDGER_DRIFT_PLANT,
        )

        skip_cells = {
            (sub_id, (ANCHOR - timedelta(days=da)).isoformat())
            for sub_id, da in _ZBA_SWEEP_FAIL_PLANT
        }
        skip_cells |= {
            (sub_id, (ANCHOR - timedelta(days=da)).isoformat())
            for sub_id, da, _ in _SUBLEDGER_DRIFT_PLANT
        }

        non_zero_unexpected: list[tuple[str, str, Decimal]] = []
        for row in ar_parsed["ar_subledger_daily_balances"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            sid, bdate, bal = parts[0], parts[1], Decimal(parts[2])
            if sid not in _ZBA_SWEEP_CUSTOMERS:
                continue
            if (sid, bdate) in skip_cells:
                continue
            if bal != 0:
                non_zero_unexpected.append((sid, bdate, bal))
        assert not non_zero_unexpected, (
            f"ZBA accounts unexpectedly non-zero EOD on normal days: "
            f"{non_zero_unexpected[:5]}"
        )

    def test_ach_origination_pattern_present(self, unified_parsed):
        """F.4.2: ACH originations must exist as mixed-level transfers
        (one customer DDA sub-ledger leg + one gl-1810 ledger-direct leg).
        Drives the F.5.X ACH-cycle exception checks."""
        from quicksight_gen.account_recon.demo_data import (
            _ACH_ORIG_LEDGER,
        )

        xfer_types: dict[str, str] = {}
        xfer_origins: dict[str, str] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            xfer_types[parts[0]] = parts[2]
            xfer_origins[parts[0]] = parts[3]

        legs_by_xfer: dict[str, list[tuple[str, str | None]]] = {}
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid, lid, sub_id = parts[1], parts[2], parts[3]
            legs_by_xfer.setdefault(tid, []).append(
                (lid, None if sub_id == "NULL" else sub_id),
            )

        ach_originations = [
            tid for tid, t in xfer_types.items()
            if t == "ach" and xfer_origins[tid] == "internal_initiated"
        ]
        mixed_level = []
        for tid in ach_originations:
            legs = legs_by_xfer.get(tid, [])
            has_sub = any(sub_id is not None for _l, sub_id in legs)
            has_ledger_direct = any(
                sub_id is None and lid == _ACH_ORIG_LEDGER
                for lid, sub_id in legs
            )
            if has_sub and has_ledger_direct:
                mixed_level.append(tid)
        assert len(mixed_level) >= 30, (
            f"Expected ≥30 ACH origination transfers (mixed-level w/ "
            f"gl-1810 leg), got {len(mixed_level)}"
        )

    def test_ach_sweep_skip_surfaces(self, ar_parsed):
        """F.4.2 sweep-skip plants must drive gl-1810 stored balance
        non-zero on plant days — that's what F.5.3 surfaces."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _ACH_ORIG_LEDGER,
            _ACH_SWEEP_SKIP_PLANT,
        )

        balances: dict[tuple[str, str], Decimal] = {}
        for row in ar_parsed["ar_ledger_daily_balances"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            balances[(parts[0], parts[1])] = Decimal(parts[2])

        for days_ago in _ACH_SWEEP_SKIP_PLANT:
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            bal = balances.get((_ACH_ORIG_LEDGER, bdate))
            assert bal is not None and bal != 0, (
                f"ACH sweep-skip plant ({_ACH_ORIG_LEDGER}, {bdate}) "
                f"should leave gl-1810 non-zero EOD (got {bal})"
            )

    def test_ach_fed_confirmation_missing_surfaces(self, unified_parsed):
        """F.4.2 missing-Fed-confirmation plants must produce an EOD
        sweep transfer with no child external_force_posted ach transfer
        — F.5.4 surfaces these by parent_transfer_id absence."""
        from quicksight_gen.account_recon.demo_data import (
            _ACH_FED_CONFIRMATION_MISSING,
        )

        xfer_by_id: dict[str, dict[str, str]] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            xfer_by_id[parts[0]] = {
                "parent": parts[1],
                "type": parts[2],
                "origin": parts[3],
            }

        children_of: dict[str, list[str]] = {}
        for tid, fields in xfer_by_id.items():
            parent = fields["parent"]
            if parent != "NULL":
                children_of.setdefault(parent, []).append(tid)

        for days_ago in _ACH_FED_CONFIRMATION_MISSING:
            sweep_tid = f"ar-ach-sweep-{days_ago:02d}"
            assert sweep_tid in xfer_by_id, (
                f"Missing-Fed-confirmation plant: expected sweep "
                f"transfer {sweep_tid} to exist"
            )
            child_fed = [
                cid for cid in children_of.get(sweep_tid, [])
                if xfer_by_id[cid]["origin"] == "external_force_posted"
            ]
            assert not child_fed, (
                f"Missing-Fed-confirmation plant ({sweep_tid}, days_ago="
                f"{days_ago}) unexpectedly has Fed children: {child_fed}"
            )

    def test_ach_fed_confirmation_normal_days_present(self, unified_parsed):
        """F.4.2 normal days (not in skip or miss-fed plants) must have
        a Fed confirmation linked back to the EOD sweep — confirms the
        happy path is actually emitted, otherwise F.5.4 would surface
        false-positive findings on every sweep."""
        from quicksight_gen.account_recon.demo_data import (
            _ACH_ORIG_DAYS,
            _ACH_SWEEP_SKIP_PLANT,
            _ACH_FED_CONFIRMATION_MISSING,
        )

        skipped = set(_ACH_SWEEP_SKIP_PLANT) | set(_ACH_FED_CONFIRMATION_MISSING)
        xfer_by_id: dict[str, dict[str, str]] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            xfer_by_id[parts[0]] = {
                "parent": parts[1],
                "type": parts[2],
                "origin": parts[3],
            }

        children_of: dict[str, list[str]] = {}
        for tid, fields in xfer_by_id.items():
            parent = fields["parent"]
            if parent != "NULL":
                children_of.setdefault(parent, []).append(tid)

        normal_days = [d for d in range(1, _ACH_ORIG_DAYS + 1) if d not in skipped]
        for days_ago in normal_days:
            sweep_tid = f"ar-ach-sweep-{days_ago:02d}"
            assert sweep_tid in xfer_by_id, (
                f"Expected ACH EOD sweep {sweep_tid} on normal day"
            )
            child_fed = [
                cid for cid in children_of.get(sweep_tid, [])
                if xfer_by_id[cid]["origin"] == "external_force_posted"
            ]
            assert child_fed, (
                f"Normal ACH day (days_ago={days_ago}) missing its Fed "
                f"confirmation child for sweep {sweep_tid}"
            )

    def test_card_settlement_pattern_present(self, unified_parsed):
        """F.4.3: Fed-side card settlement observations and SNB internal
        catch-ups must exist with the correct parent → child linkage.
        Drives the F.5.X card-settlement reconciliation checks."""
        from quicksight_gen.account_recon.demo_data import (
            _CARD_SETTLEMENT_DAYS,
            _CARD_INTERNAL_MISSING_PLANT,
        )

        xfer_by_id: dict[str, dict[str, str]] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            xfer_by_id[parts[0]] = {
                "parent": parts[1],
                "type": parts[2],
                "origin": parts[3],
            }

        fed_observations = [
            tid for tid in xfer_by_id
            if tid.startswith("ar-card-fed-")
        ]
        catchups = [
            tid for tid in xfer_by_id
            if tid.startswith("ar-card-internal-")
        ]

        assert len(fed_observations) == _CARD_SETTLEMENT_DAYS, (
            f"Expected {_CARD_SETTLEMENT_DAYS} Fed observation transfers, "
            f"got {len(fed_observations)}"
        )
        expected_catchups = (
            _CARD_SETTLEMENT_DAYS - len(_CARD_INTERNAL_MISSING_PLANT)
        )
        assert len(catchups) == expected_catchups, (
            f"Expected {expected_catchups} catch-up transfers, "
            f"got {len(catchups)}"
        )

        for catchup_tid in catchups:
            day_part = catchup_tid.split("-")[-1]
            expected_parent = f"ar-card-fed-{day_part}"
            assert xfer_by_id[catchup_tid]["parent"] == expected_parent, (
                f"Catch-up {catchup_tid} parent="
                f"{xfer_by_id[catchup_tid]['parent']}, expected "
                f"{expected_parent}"
            )
            assert (
                xfer_by_id[catchup_tid]["origin"] == "external_force_posted"
            ), f"Catch-up {catchup_tid} origin should be external_force_posted"

    def test_card_internal_missing_surfaces(self, unified_parsed):
        """F.4.3 missing-internal plants must produce a Fed observation
        transfer with no child catch-up — F.5.X surfaces these by parent
        absence."""
        from quicksight_gen.account_recon.demo_data import (
            _CARD_INTERNAL_MISSING_PLANT,
        )

        xfer_by_id: dict[str, str] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            xfer_by_id[parts[0]] = parts[1]

        children_of: dict[str, list[str]] = {}
        for tid, parent in xfer_by_id.items():
            if parent != "NULL":
                children_of.setdefault(parent, []).append(tid)

        for days_ago in _CARD_INTERNAL_MISSING_PLANT:
            fed_tid = f"ar-card-fed-{days_ago:02d}"
            assert fed_tid in xfer_by_id, (
                f"Missing-internal plant: expected Fed observation "
                f"{fed_tid} to exist"
            )
            assert not children_of.get(fed_tid), (
                f"Missing-internal plant ({fed_tid}, days_ago={days_ago}) "
                f"unexpectedly has children: {children_of.get(fed_tid)}"
            )

    def test_on_us_transfer_pattern_present(self, unified_parsed):
        """F.4.4: every plant row in _INTERNAL_TRANSFER_PLANT must produce
        a Step-1 originate transfer; success / reversal_not_credited
        plants additionally produce a Step-2 transfer chained back via
        parent_transfer_id."""
        from quicksight_gen.account_recon.demo_data import (
            _INTERNAL_TRANSFER_PLANT,
        )

        xfer_by_id: dict[str, dict[str, str]] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            xfer_by_id[parts[0]] = {
                "parent": parts[1],
                "type": parts[2],
                "origin": parts[3],
            }

        for plant_idx, (_orig, _recip, _da, kind, _amt) in enumerate(
            _INTERNAL_TRANSFER_PLANT, 1,
        ):
            orig_tid = f"ar-on-us-orig-{plant_idx:02d}"
            assert orig_tid in xfer_by_id, (
                f"Missing Step-1 originate transfer {orig_tid}"
            )
            assert xfer_by_id[orig_tid]["parent"] == "NULL", (
                f"Step-1 originate {orig_tid} should have NULL parent"
            )

            step2_tid = f"ar-on-us-step2-{plant_idx:02d}"
            if kind == "stuck":
                assert step2_tid not in xfer_by_id, (
                    f"Stuck plant {orig_tid} should have no Step-2; got "
                    f"{step2_tid}"
                )
            else:
                assert step2_tid in xfer_by_id, (
                    f"Missing Step-2 transfer {step2_tid} for kind={kind}"
                )
                assert xfer_by_id[step2_tid]["parent"] == orig_tid, (
                    f"Step-2 {step2_tid} parent="
                    f"{xfer_by_id[step2_tid]['parent']}, expected {orig_tid}"
                )

    def test_on_us_stuck_in_suspense_surfaces(self, unified_parsed):
        """F.4.4 stuck plants must produce Step-1 originate transfers
        whose suspense leg posted but with no Step-2 child — that's the
        precise SQL signature F.5.X uses for "stuck in suspense".
        (Stored gl-1830 balance reflects stuck plants, but random fee
        assessments can also touch gl-1830 so we don't pin an exact
        balance — we check the structural pattern instead.)"""
        from quicksight_gen.account_recon.demo_data import (
            _INTERNAL_TRANSFER_PLANT,
        )

        xfer_by_id: dict[str, str] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            xfer_by_id[parts[0]] = parts[1]
        children_of: dict[str, list[str]] = {}
        for tid, parent in xfer_by_id.items():
            if parent != "NULL":
                children_of.setdefault(parent, []).append(tid)

        for plant_idx, (_o, _r, _da, kind, _amt) in enumerate(
            _INTERNAL_TRANSFER_PLANT, 1,
        ):
            if kind != "stuck":
                continue
            orig_tid = f"ar-on-us-orig-{plant_idx:02d}"
            assert orig_tid in xfer_by_id, (
                f"Stuck plant {orig_tid} missing"
            )
            assert not children_of.get(orig_tid), (
                f"Stuck plant {orig_tid} unexpectedly has children "
                f"{children_of.get(orig_tid)}"
            )

    def test_on_us_reversed_not_credited_pattern(self, unified_parsed):
        """F.4.4 reversed-not-credited plants: the Step-2 transfer's
        sub-ledger leg has status='failed' (originator never recovered)
        while its suspense ledger leg has status='success' — suspense
        clears but money stays gone. F.5.X "double spend" surfaces."""
        from quicksight_gen.account_recon.demo_data import (
            _INTERNAL_TRANSFER_PLANT,
            _INTERNAL_TRANSFER_SUSPENSE_LEDGER,
        )

        legs_by_xfer: dict[str, list[tuple]] = {}
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            legs_by_xfer.setdefault(parts[1], []).append(
                (parts[2], parts[3], parts[6]),  # ledger, sub_id, status
            )

        rnc_indexes = [
            i + 1 for i, plant in enumerate(_INTERNAL_TRANSFER_PLANT)
            if plant[3] == "reversed_not_credited"
        ]
        assert rnc_indexes, "Expected at least one reversed_not_credited plant"

        for idx in rnc_indexes:
            step2_tid = f"ar-on-us-step2-{idx:02d}"
            legs = legs_by_xfer.get(step2_tid, [])
            assert len(legs) == 2, (
                f"Step-2 {step2_tid} expected 2 legs, got {len(legs)}"
            )
            sub_legs = [l for l in legs if l[1] != "NULL"]
            ledger_legs = [
                l for l in legs
                if l[1] == "NULL" and l[0] == _INTERNAL_TRANSFER_SUSPENSE_LEDGER
            ]
            assert len(sub_legs) == 1, (
                f"Step-2 {step2_tid} expected 1 sub-ledger leg"
            )
            assert sub_legs[0][2] == "failed", (
                f"Step-2 {step2_tid} sub-ledger leg should be failed, got "
                f"{sub_legs[0][2]}"
            )
            assert len(ledger_legs) == 1 and ledger_legs[0][2] == "success", (
                f"Step-2 {step2_tid} suspense leg should be success, got "
                f"{ledger_legs}"
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
        """192 transfers: 66 sub-ledger + 5 funding + 3 fee + 2 inter-ledger
        sweep + 20 ZBA EOD sweep + 2 ZBA fail-plant deposit
        + 2 ZBA mismatch-plant deposit + 66 ACH cycle
        + 18 card settlement (10 Fed observations + 8 internal catch-ups)
        + 8 on-us internal (5 originate + 3 step-2)."""
        assert len(unified_parsed["transfer"]) == 192

    def test_posting_row_count(self, unified_parsed):
        """410 postings: 132 sub-ledger pair legs + 46 ledger-level postings
        (5 funding batches with 6-7 sub-ledger legs each, 3 fee assessments,
        2 inter-ledger clearing sweeps) + 40 ZBA sweep legs (20 sub-ledger
        + 20 ledger-direct) + 4 ZBA fail-plant deposit legs
        + 4 ZBA mismatch-plant deposit legs + 132 ACH cycle
        legs (84 origination + 26 sweep + 22 Fed confirmation) + 36 card
        settlement legs (20 Fed observation + 16 internal catch-up)
        + 16 on-us internal transfer legs."""
        assert len(unified_parsed["posting"]) == 410

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

    def test_ar_transfer_parent_chain_well_formed(self, unified_parsed):
        """AR transfers may carry parent_transfer_id only for the
        Fed confirmation pattern (external_force_posted attestations link
        back to their parent EOD internal sweep, supporting the F.5.4
        / F.5.5 sweep-vs-confirmation matching). Every non-null parent
        must reference a known transfer."""
        parents = self._col(unified_parsed["transfer"], 1)
        transfer_ids = set(self._col(unified_parsed["transfer"], 0))
        non_null = [p for p in parents if p != "NULL"]
        for p in non_null:
            assert p in transfer_ids, (
                f"parent_transfer_id {p} references unknown transfer"
            )

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
        """NULL-subledger postings (ledger-direct legs) are emitted by
        legitimate ledger-level shapes: funding_batch (ledger credit +
        sub-ledger debits), fee (single ledger debit), clearing_sweep
        (inter-ledger or sub-to-master mixed-level). F.4.2 ach scenarios
        emit ledger-direct legs at gl-1810 (ACH Origination Settlement)
        and gl-1010 (Cash Due From FRB). F.4.3 ach catch-ups emit
        ledger-direct at gl-1815 (Card Acquiring Settlement). F.4.4
        internal transfers emit ledger-direct at gl-1830 (Internal
        Transfer Suspense) for both originate and step-2 legs. Reject
        any unexpected transfer_type."""
        postings = self._parse_postings(unified_parsed)
        xfer_types = self._parse_transfers(unified_parsed)
        allowed = {
            "funding_batch", "fee", "clearing_sweep",
            "ach", "internal",
        }
        for p in postings:
            if p["subledger_account_id"] is None:
                assert xfer_types[p["transfer_id"]] in allowed, (
                    f"Transfer {p['transfer_id']} (type="
                    f"{xfer_types[p['transfer_id']]}) has NULL subledger "
                    f"posting — not in allowed list"
                )

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
        """Each clearing sweep has 2 legs that net to zero. Inter-ledger
        sweeps are ledger-only on both legs; ZBA sweeps are mixed-level
        (one sub-ledger leg zeroes out an operating sub-account, one
        ledger-direct leg offsets at the master ledger).

        F.5.2 mismatch plants intentionally break this invariant on a
        small fixed set of sweep transfers — the offset surfaces as
        Concentration Master sweep drift. Those are exempted here.
        """
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _ZBA_SWEEP_LEG_MISMATCH_PLANT,
        )
        plant_dates = {
            (sub_id, (ANCHOR - timedelta(days=da)).isoformat())
            for sub_id, da, _ in _ZBA_SWEEP_LEG_MISMATCH_PLANT
        }

        postings = self._parse_postings(unified_parsed)
        xfer_types = self._parse_transfers(unified_parsed)
        by_xfer: dict[str, list] = {}
        for p in postings:
            if xfer_types.get(p["transfer_id"]) == "clearing_sweep":
                by_xfer.setdefault(p["transfer_id"], []).append(p)
        for tid, legs in by_xfer.items():
            assert len(legs) == 2, f"Sweep {tid} has {len(legs)} legs, expected 2"
            sub_legs = [l for l in legs if l["subledger_account_id"]]
            sub_id = sub_legs[0]["subledger_account_id"] if sub_legs else None
            day = legs[0]["posted_at"][:10]
            if sub_id and (sub_id, day) in plant_dates:
                continue  # planted mismatch — drift surfaces in F.5.2
            net = sum(leg["signed_amount"] for leg in legs)
            assert net == 0, f"Sweep {tid} net={net}, expected 0"

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

    def test_eighteen_dataset_files(self, ar_output_dir):
        datasets = list((ar_output_dir / "datasets").glob("qs-gen-ar-*.json"))
        assert len(datasets) == 18

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
        # Phase 5: five baseline checks (three drift KPIs + breach +
        # overdraft) → 5 KPIs + 5 tables + 2 timelines + 5 aging bars
        # = 17. Phase F.5.1 adds Sweep target non-zero EOD
        # (KPI + table + aging bar) → 20. Phase F.5.2 adds
        # Concentration Master sweep drift (KPI + timeline) → 22.
        # Phase F.5.3 adds ACH Origination Settlement non-zero EOD
        # (KPI + table + aging bar) → 25. Phase F.5.4 adds ACH internal
        # sweep without Fed confirmation (KPI + table + aging bar) → 28.
        # Phase F.5.5 adds Fed activity without internal catch-up
        # (KPI + table + aging bar) → 31. Phase F.5.6 adds GL-vs-Fed
        # Master drift (KPI + timeline) → 33. Phase F.5.7 adds Stuck in
        # Internal Transfer Suspense (KPI + table + aging bar) → 36.
        # Phase F.5.8 adds Internal Transfer Suspense non-zero EOD
        # (KPI + table + aging bar) → 39. Phase F.5.9 adds Reversed-but-
        # not-credited / double spend (KPI + table + aging bar) → 42.
        self._assert_visual_count(ar_output_dir, SHEET_AR_EXCEPTIONS, 42)

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
        "fg-ar-origin",
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
