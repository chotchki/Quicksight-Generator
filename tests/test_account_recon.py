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
    ALL_FG_AR_IDS,
    ALL_P_AR,
    FG_AR_BALANCES_LEDGER_DRIFT,
    FG_AR_BALANCES_OVERDRAFT,
    FG_AR_BALANCES_SUBLEDGER_DRIFT,
    FG_AR_DATE_RANGE,
    FG_AR_DRILL_ACCOUNT_ON_TXN,
    FG_AR_DRILL_ACTIVITY_DATE_ON_TXN,
    FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER,
    FG_AR_DRILL_SUBLEDGER_ON_TXN,
    FG_AR_DRILL_TRANSFER_ON_TXN,
    FG_AR_DRILL_TRANSFER_TYPE_ON_TXN,
    FG_AR_DS_ACCOUNT,
    FG_AR_DS_BALANCE_DATE,
    FG_AR_LEDGER_ACCOUNT,
    FG_AR_SUBLEDGER_ACCOUNT,
    FG_AR_TRANSACTION_STATUS,
    FG_AR_TRANSACTIONS_FAILED,
    FG_AR_TRANSFER_STATUS,
    FG_AR_TRANSFER_TYPE,
    P_AR_ACCOUNT,
    P_AR_ACTIVITY_DATE,
    P_AR_DS_ACCOUNT,
    P_AR_DS_BALANCE_DATE,
    P_AR_LEDGER,
    P_AR_SUBLEDGER,
    P_AR_TRANSFER,
    P_AR_TRANSFER_TYPE,
    SHEET_AR_BALANCES,
    SHEET_AR_DAILY_STATEMENT,
    SHEET_AR_EXCEPTIONS_TRENDS,
    SHEET_AR_GETTING_STARTED,
    SHEET_AR_TODAYS_EXCEPTIONS,
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


def _parse_balanced_rows(body: str) -> list[str]:
    """Split a VALUES body into rows respecting nested parens (metadata
    JSON may contain commas; the row tokenizer must walk parens depth)."""
    rows: list[str] = []
    depth = 0
    start = None
    for i, ch in enumerate(body):
        if ch == "(" and depth == 0:
            start = i
            depth = 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                rows.append(body[start + 1:i])
    return rows


@pytest.fixture()
def ar_parsed(ar_sql: str) -> dict[str, list[str]]:
    """Parse ar_sql into table → list of parenthesised value-row strings.

    After v3.0.0 the per-scope daily-balance tables are gone; ledger and
    sub-ledger snapshots both live in the unified ``daily_balances`` table.
    For backward-compat with v2-era index-based assertions this fixture
    projects ``ar_ledger_daily_balances`` and ``ar_subledger_daily_balances``
    from ``daily_balances`` rows (control_account_id NULL = ledger row).
    """
    result: dict[str, list[str]] = {}
    for m in re.finditer(
        r"INSERT INTO (ar_\w+|daily_balances) \([^)]+\) VALUES\n(.*?);",
        ar_sql,
        re.DOTALL,
    ):
        table = m.group(1)
        body = m.group(2)
        result[table] = re.findall(r"\(([^)]+)\)", body)

    # Project legacy daily-balance projections: account_id, balance_date, balance.
    # daily_balances cols: account_id 0, account_name 1, control_account_id 2,
    # account_type 3, is_internal 4, balance_date 5, balance 6, metadata 7.
    ledger: list[str] = []
    subledger: list[str] = []
    for row in result.get("daily_balances", []):
        parts = [p.strip() for p in row.split(",")]
        proj = f"{parts[0]}, {parts[5]}, {parts[6]}"
        if parts[2] == "NULL":
            ledger.append(proj)
        else:
            subledger.append(proj)
    result["ar_ledger_daily_balances"] = ledger
    result["ar_subledger_daily_balances"] = subledger
    return result


@pytest.fixture()
def unified_parsed(ar_sql: str) -> dict[str, list[str]]:
    """Project legacy ``transfer`` + ``posting`` shapes from the unified
    ``transactions`` table (dropped in v3.0.0).

    Posting projection (cols 0..6): posting_id, transfer_id,
    ledger_account_id, subledger_account_id, signed_amount, posted_at,
    status — same indices the v2-era tests reach into.

    Transfer projection (cols 0..6): transfer_id, parent_transfer_id,
    transfer_type, origin, amount, NULL, first_posted_at — one row per
    distinct transfer_id, derived from the first posting encountered.
    """
    m = re.search(
        r"INSERT INTO transactions \([^)]+\) VALUES\n(.*?);",
        ar_sql, re.DOTALL,
    )
    if not m:
        return {"posting": [], "transfer": []}
    txns = _parse_balanced_rows(m.group(1))

    postings: list[str] = []
    transfers: list[str] = []
    seen: set[str] = set()
    for row in txns:
        parts = [p.strip() for p in row.split(",")]
        # transactions cols (index): 0 transaction_id, 1 transfer_id,
        # 2 parent_transfer_id, 3 transfer_type, 4 origin, 5 account_id,
        # 6 account_name, 7 control_account_id, 8 account_type, 9 is_internal,
        # 10 signed_amount, 11 amount, 12 status, 13 posted_at.
        txn_id = parts[0]
        xfer_id = parts[1]
        parent = parts[2]
        ttype = parts[3]
        origin = parts[4]
        account_id = parts[5]
        control = parts[7]
        signed = parts[10]
        amount = parts[11]
        status = parts[12]
        posted = parts[13]

        # Direct ledger postings have control_account_id NULL on the row's
        # account; sub-ledger postings carry control = parent ledger.
        if control == "NULL":
            ledger_id = account_id
            sub_id = "NULL"
        else:
            ledger_id = control
            sub_id = account_id
        postings.append(
            f"{txn_id}, {xfer_id}, {ledger_id}, {sub_id}, {signed}, {posted}, {status}"
        )

        if xfer_id not in seen:
            seen.add(xfer_id)
            transfers.append(
                f"{xfer_id}, {parent}, {ttype}, {origin}, {amount}, NULL, {posted}"
            )

    return {"posting": postings, "transfer": transfers}


class TestDemoDeterminism:
    def test_same_anchor_identical_output(self):
        assert generate_demo_sql(ANCHOR) == generate_demo_sql(ANCHOR)

    def test_different_anchor_shifts_dates(self):
        a = generate_demo_sql(date(2026, 1, 1))
        b = generate_demo_sql(date(2026, 6, 1))
        assert a != b

    def test_seed_output_hash_is_locked(self, ar_sql):
        """Pinned hash so any silent drift in the AR generator is caught.

        When intentionally regenerating (e.g. new metadata key, additional
        scenario rows), update the hash here in the same commit.
        """
        import hashlib
        digest = hashlib.sha256(ar_sql.encode()).hexdigest()
        assert digest == (
            "525554ccfa578914b1fb7b577c82a42691244b39c2747b605640348fc7593cc5"
        ), f"AR seed drifted; new hash: {digest}"


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

    def test_expected_zero_rollup_surfaces_each_source(self, ar_parsed):
        """F.5.10.a rollup unions F.5.1 (ZBA sweep target), F.5.3
        (ACH Origination Settlement), and F.5.8 (Internal Transfer
        Suspense) — the rollup is empty unless at least one row from
        each source check exists. Confirms the same-SHAPE pattern
        teaches across all three control accounts."""
        ledger_balances: dict[tuple[str, str], Decimal] = {}
        for row in ar_parsed["ar_ledger_daily_balances"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            ledger_balances[(parts[0], parts[1])] = Decimal(parts[2])

        sub_balances: dict[tuple[str, str], Decimal] = {}
        for row in ar_parsed["ar_subledger_daily_balances"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            sub_balances[(parts[0], parts[1])] = Decimal(parts[2])

        ach_orig_nonzero = any(
            bal != 0 for (acct, _), bal in ledger_balances.items()
            if acct == "gl-1810-ach-orig-settlement"
        )
        suspense_nonzero = any(
            bal != 0 for (acct, _), bal in ledger_balances.items()
            if acct == "gl-1830-internal-transfer-suspense"
        )
        sweep_target_nonzero = any(
            bal != 0 for _, bal in sub_balances.items()
        )

        assert ach_orig_nonzero, (
            "F.5.10.a rollup needs at least one non-zero gl-1810 EOD "
            "(F.5.3 source) — rollup will be missing that source check"
        )
        assert suspense_nonzero, (
            "F.5.10.a rollup needs at least one non-zero gl-1830 EOD "
            "(F.5.8 source) — rollup will be missing that source check"
        )
        assert sweep_target_nonzero, (
            "F.5.10.a rollup needs at least one non-zero ZBA-target "
            "sub-ledger EOD (F.5.1 source) — rollup will be missing "
            "that source check"
        )

    def test_two_sided_post_mismatch_rollup_surfaces_each_source(
        self, unified_parsed,
    ):
        """F.5.10.b rollup unions F.5.4 (SNB sweep posted, Fed leg
        missing) and F.5.5 (Fed leg posted, SNB internal catch-up
        missing) — the rollup is empty unless at least one row from
        each source check exists. Confirms the same-SHAPE pattern
        teaches across both flows."""
        xfer_types: dict[str, str] = {}
        xfer_origins: dict[str, str] = {}
        xfer_parents: dict[str, str | None] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[0]
            xfer_parents[tid] = None if parts[1] == "NULL" else parts[1]
            xfer_types[tid] = parts[2]
            xfer_origins[tid] = parts[3]

        ach_sweep_tids: set[str] = set()
        fed_card_tids: set[str] = set()
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[1]
            ledger_id = None if parts[2] == "NULL" else parts[2]
            sub_id = None if parts[3] == "NULL" else parts[3]
            if (
                xfer_types.get(tid) == "clearing_sweep"
                and ledger_id == "gl-1810-ach-orig-settlement"
            ):
                ach_sweep_tids.add(tid)
            if (
                xfer_types.get(tid) == "ach"
                and xfer_origins.get(tid) == "external_force_posted"
                and xfer_parents.get(tid) is None
                and sub_id == "ext-payment-gateway-sub-clearing"
            ):
                fed_card_tids.add(tid)

        children_of = {
            parent for parent in xfer_parents.values() if parent is not None
        }
        sweeps_no_fed = ach_sweep_tids - children_of
        feds_no_internal = fed_card_tids - children_of

        assert sweeps_no_fed, (
            "F.5.10.b rollup needs at least one ACH sweep with no Fed "
            "confirmation (F.5.4 source) — rollup will be missing that "
            "source check"
        )
        assert feds_no_internal, (
            "F.5.10.b rollup needs at least one Fed observation with no "
            "internal catch-up (F.5.5 source) — rollup will be missing "
            "that source check"
        )

    def test_balance_drift_timelines_rollup_surfaces_each_source(
        self, unified_parsed,
    ):
        """F.5.10.c overlays per-day drift from F.5.2 (Concentration
        Master sweep — clearing_sweep transfer leg imbalance) and F.5.6
        (GL vs Fed Master — Fed-side card observations vs SNB internal
        catch-up totals). The overlay is empty unless at least one
        non-zero drift day exists from each source."""
        xfer_types: dict[str, str] = {}
        xfer_origins: dict[str, str] = {}
        xfer_parents: dict[str, str | None] = {}
        xfer_amounts: dict[str, Decimal] = {}
        xfer_dates: dict[str, str] = {}
        for row in unified_parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[0]
            xfer_parents[tid] = None if parts[1] == "NULL" else parts[1]
            xfer_types[tid] = parts[2]
            xfer_origins[tid] = parts[3]
            xfer_amounts[tid] = Decimal(parts[4])
            xfer_dates[tid] = parts[6][:10]

        sweep_legs: dict[str, list[tuple[str | None, str | None, Decimal]]] = {}
        fed_card_tids: set[str] = set()
        for row in unified_parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[1]
            ledger_id = None if parts[2] == "NULL" else parts[2]
            sub_id = None if parts[3] == "NULL" else parts[3]
            signed_amount = Decimal(parts[4])
            if xfer_types.get(tid) == "clearing_sweep":
                sweep_legs.setdefault(tid, []).append(
                    (ledger_id, sub_id, signed_amount),
                )
            if (
                xfer_types.get(tid) == "ach"
                and xfer_origins.get(tid) == "external_force_posted"
                and xfer_parents.get(tid) is None
                and sub_id == "ext-payment-gateway-sub-clearing"
            ):
                fed_card_tids.add(tid)

        sweep_drift_days: set[str] = set()
        for tid, legs in sweep_legs.items():
            net = sum((amt for _, _, amt in legs), Decimal(0))
            if net != 0:
                sweep_drift_days.add(xfer_dates[tid])

        fed_per_day: dict[str, Decimal] = {}
        internal_per_day: dict[str, Decimal] = {}
        for tid in fed_card_tids:
            d = xfer_dates[tid]
            fed_per_day[d] = fed_per_day.get(d, Decimal(0)) + xfer_amounts[tid]
        for tid, parent in xfer_parents.items():
            if parent in fed_card_tids:
                d = xfer_dates[tid]
                internal_per_day[d] = (
                    internal_per_day.get(d, Decimal(0)) + xfer_amounts[tid]
                )
        gl_fed_drift_days = {
            d for d in fed_per_day
            if fed_per_day[d] - internal_per_day.get(d, Decimal(0)) != 0
        }

        assert sweep_drift_days, (
            "F.5.10.c rollup needs at least one non-zero Concentration "
            "Master sweep drift day (F.5.2 source) — rollup overlay will "
            "be missing that series"
        )
        assert gl_fed_drift_days, (
            "F.5.10.c rollup needs at least one non-zero GL vs Fed "
            "Master drift day (F.5.6 source) — rollup overlay will be "
            "missing that series"
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
            "transactions",
            "daily_balances",
        }

    def test_fk_safe_order(self, ar_sql):
        positions = {}
        for m in re.finditer(r"INSERT INTO (\w+)", ar_sql):
            positions.setdefault(m.group(1), m.start())
        assert positions["ar_ledger_accounts"] < positions["ar_subledger_accounts"]
        assert positions["ar_ledger_accounts"] < positions["daily_balances"]
        assert positions["ar_subledger_accounts"] < positions["daily_balances"]
        assert (
            positions["ar_ledger_accounts"]
            < positions["ar_ledger_transfer_limits"]
        )
        assert positions["ar_subledger_accounts"] < positions["transactions"]
        # transactions reference ar_subledger_accounts; daily_balances does too.
        assert positions["transactions"] < positions["daily_balances"]


# ---------------------------------------------------------------------------
# Schema SQL (checks the shared schema shipped with the package)
# ---------------------------------------------------------------------------

class TestSchemaSql:
    @pytest.fixture()
    def schema_sql(self) -> str:
        from quicksight_gen.schema import generate_schema_sql

        return generate_schema_sql()

    def test_creates_ar_tables(self, schema_sql):
        for table in (
            "ar_ledger_accounts",
            "ar_subledger_accounts",
            "ar_ledger_transfer_limits",
            "transactions",
            "daily_balances",
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
        """transactions table must carry the transfer_type column."""
        m = re.search(
            r"CREATE TABLE transactions \((.*?)\);",
            schema_sql,
            re.DOTALL,
        )
        assert m, "transactions CREATE TABLE missing"
        assert "transfer_type" in m.group(1), (
            "transactions.transfer_type column missing"
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

    def test_thirteen_dataset_files(self, ar_output_dir):
        datasets = list((ar_output_dir / "datasets").glob("qs-gen-ar-*.json"))
        assert len(datasets) == 13

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
    """Phase K.1.3: Today's Exceptions + Exceptions Trends slot between
    Transactions and the legacy Exceptions sheet (legacy stays until
    K.1.4 drops the per-check blocks)."""

    def test_eight_sheets(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        assert len(analysis["Definition"]["Sheets"]) == 7

    def test_sheet_order(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        ids = [s["SheetId"] for s in analysis["Definition"]["Sheets"]]
        assert ids == [
            SHEET_AR_GETTING_STARTED,
            SHEET_AR_BALANCES,
            SHEET_AR_TRANSFERS,
            SHEET_AR_TRANSACTIONS,
            SHEET_AR_TODAYS_EXCEPTIONS,
            SHEET_AR_EXCEPTIONS_TRENDS,
            SHEET_AR_DAILY_STATEMENT,
        ]

    def test_balances_visual_count(self, ar_output_dir):
        self._assert_visual_count(ar_output_dir, SHEET_AR_BALANCES, 4)

    def test_transfers_visual_count(self, ar_output_dir):
        # Phase 4: added Transfer Status bar chart -> 4
        self._assert_visual_count(ar_output_dir, SHEET_AR_TRANSFERS, 4)

    def test_transactions_visual_count(self, ar_output_dir):
        # Phase 4: added Transactions-by-day bar chart -> 5
        self._assert_visual_count(ar_output_dir, SHEET_AR_TRANSACTIONS, 5)

    def test_todays_exceptions_visual_count(self, ar_output_dir):
        # Phase K.1.2: total KPI + breakdown bar + unified table = 3.
        self._assert_visual_count(ar_output_dir, SHEET_AR_TODAYS_EXCEPTIONS, 3)

    def test_exceptions_trends_visual_count(self, ar_output_dir):
        # Phase K.1.3: 3 rollups moved off legacy Exceptions (drift
        # timelines + 2 KPI/table pairs = 5) + 2 new unified-dataset
        # trend visuals (aging matrix, per-check trend) = 7.
        self._assert_visual_count(ar_output_dir, SHEET_AR_EXCEPTIONS_TRENDS, 7)

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
            "ar-gs-todays-exceptions",
            "ar-gs-exceptions-trends",
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
    """Shared date-range + 6 multi-selects + 3 Show-Only toggles +
    5 drill-down parameter filters + Daily Statement (account/date) +
    Today's Exceptions (check-type/account/aging) filter groups."""

    def test_filter_group_ids(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        ids = {fg["FilterGroupId"] for fg in analysis["Definition"]["FilterGroups"]}
        assert ids == ALL_FG_AR_IDS

    def test_date_range_scopes_five_tabs(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, FG_AR_DATE_RANGE)
        scopes = fg["ScopeConfiguration"]["SelectedSheets"][
            "SheetVisualScopingConfigurations"
        ]
        sheet_ids = {s["SheetId"] for s in scopes}
        assert sheet_ids == {
            SHEET_AR_BALANCES,
            SHEET_AR_TRANSFERS,
            SHEET_AR_TRANSACTIONS,
            SHEET_AR_TODAYS_EXCEPTIONS,
            SHEET_AR_EXCEPTIONS_TRENDS,
        }

    @pytest.mark.parametrize(
        "fg_id",
        [
            FG_AR_LEDGER_ACCOUNT,
            FG_AR_SUBLEDGER_ACCOUNT,
            FG_AR_TRANSFER_TYPE,
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
        [FG_AR_TRANSFER_STATUS, FG_AR_TRANSACTION_STATUS],
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
            (FG_AR_BALANCES_LEDGER_DRIFT, SHEET_AR_BALANCES),
            (FG_AR_BALANCES_SUBLEDGER_DRIFT, SHEET_AR_BALANCES),
            (FG_AR_BALANCES_OVERDRAFT, SHEET_AR_BALANCES),
            (FG_AR_TRANSACTIONS_FAILED, SHEET_AR_TRANSACTIONS),
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


_FILTER_TYPE_KEYS = (
    "CategoryFilter",
    "TimeRangeFilter",
    "TimeEqualityFilter",
    "NumericRangeFilter",
)
_DIRECT_CONTROL_KEYS = ("Dropdown", "DateTimePicker", "Slider", "List", "TextField",
                        "RelativeDateTime")


def _filter_inner(f: dict) -> tuple[str, dict]:
    for k in _FILTER_TYPE_KEYS:
        if k in f:
            return k, f[k]
    raise AssertionError(f"Unknown filter shape: {list(f.keys())}")


def _sheet_count(fg: dict) -> int:
    scope = fg["ScopeConfiguration"].get("SelectedSheets")
    if scope is None:
        return 0
    return len({s["SheetId"] for s in scope["SheetVisualScopingConfigurations"]})


class TestFilterControlRule:
    """Guard the AWS rule that broke three K.1 deploy attempts:

    * Multi-sheet filter (>1 sheet in scope) MUST carry
      ``DefaultFilterControlConfiguration``; every bound FilterControl
      MUST be ``CrossSheet`` (inherits the default).
    * Single-sheet filter MUST NOT carry
      ``DefaultFilterControlConfiguration``; every bound FilterControl
      MUST be a direct widget (Dropdown / DateTimePicker / Slider /...)
      that specifies its own spec.

    Walks every FilterGroup + every sheet's FilterControls in the
    generated analysis and asserts the rule by inspection.
    """

    def test_filter_default_control_matches_sheet_count(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        for fg in analysis["Definition"]["FilterGroups"]:
            n = _sheet_count(fg)
            for f in fg["Filters"]:
                key, body = _filter_inner(f)
                has_default = "DefaultFilterControlConfiguration" in body
                fid = body["FilterId"]
                if n > 1:
                    assert has_default, (
                        f"Multi-sheet filter '{fid}' ({key}, {n} sheets) "
                        f"missing DefaultFilterControlConfiguration"
                    )
                else:
                    assert not has_default, (
                        f"Single-sheet filter '{fid}' ({key}) must not "
                        f"carry DefaultFilterControlConfiguration"
                    )

    def test_control_kind_matches_source_filter_sheet_count(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        sheet_count_by_filter: dict[str, int] = {}
        for fg in analysis["Definition"]["FilterGroups"]:
            n = _sheet_count(fg)
            for f in fg["Filters"]:
                _, body = _filter_inner(f)
                sheet_count_by_filter[body["FilterId"]] = n

        for sheet in analysis["Definition"]["Sheets"]:
            for ctrl in sheet.get("FilterControls", []):
                kind, body = next(iter(ctrl.items()))
                src = body["SourceFilterId"]
                n = sheet_count_by_filter.get(src)
                assert n is not None, (
                    f"Control '{body.get('FilterControlId')}' references "
                    f"unknown filter '{src}'"
                )
                if n > 1:
                    assert kind == "CrossSheet", (
                        f"Control '{body.get('FilterControlId')}' bound to "
                        f"multi-sheet filter '{src}' must be CrossSheet, "
                        f"got {kind}"
                    )
                else:
                    assert kind in _DIRECT_CONTROL_KEYS, (
                        f"Control '{body.get('FilterControlId')}' bound to "
                        f"single-sheet filter '{src}' must be a direct "
                        f"widget, got {kind}"
                    )


class TestParameterDeclarations:
    """Phase 5 drill-downs use single-valued string parameters; the
    Daily Statement balance-date drill uses one date-time parameter."""

    _STRING_PARAMS = {p.name for p in ALL_P_AR if p is not P_AR_DS_BALANCE_DATE}
    _DATETIME_PARAMS = {P_AR_DS_BALANCE_DATE.name}

    def _split(self, params: list[dict]) -> tuple[list[dict], list[dict]]:
        return (
            [p["StringParameterDeclaration"] for p in params if "StringParameterDeclaration" in p],
            [p["DateTimeParameterDeclaration"] for p in params if "DateTimeParameterDeclaration" in p],
        )

    def test_string_parameters(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        params = analysis["Definition"]["ParameterDeclarations"]
        string_params, _ = self._split(params)
        assert {p["Name"] for p in string_params} == self._STRING_PARAMS

    def test_datetime_parameters(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        params = analysis["Definition"]["ParameterDeclarations"]
        _, datetime_params = self._split(params)
        assert {p["Name"] for p in datetime_params} == self._DATETIME_PARAMS

    def test_string_parameters_single_valued(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        params = analysis["Definition"]["ParameterDeclarations"]
        string_params, _ = self._split(params)
        for decl in string_params:
            assert decl["ParameterValueType"] == "SINGLE_VALUED"

    def test_balance_date_param_defaults_to_today(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        params = analysis["Definition"]["ParameterDeclarations"]
        _, datetime_params = self._split(params)
        bal_date = next(p for p in datetime_params if p["Name"] == P_AR_DS_BALANCE_DATE.name)
        assert bal_date["TimeGranularity"] == "DAY"
        assert bal_date["DefaultValues"]["RollingDate"]["Expression"] == (
            "truncDate('DD', now())"
        )


class TestDrillDownFilterGroups:
    """Six drill filter groups, all using the calc-field PASS shape.

    Each spec produces (a) a calc field that returns 'PASS' when the
    bound parameter equals the K.2 sentinel ``__ALL__`` or matches the
    target column, and (b) a static-literal CategoryValue=PASS filter
    over that calc field. Parameter-bound filter shapes were retired
    in K.2 because they silently match the literal empty string when
    the param is empty, suppressing every row.
    """

    @pytest.mark.parametrize(
        "fg_id, parameter_name, column_name, sheet_id, calc_field_name",
        [
            (
                FG_AR_DRILL_SUBLEDGER_ON_TXN,
                P_AR_SUBLEDGER.name,
                "subledger_account_id",
                SHEET_AR_TRANSACTIONS,
                f"_drill_pass_{P_AR_SUBLEDGER.name}_on_txn",
            ),
            (
                FG_AR_DRILL_TRANSFER_ON_TXN,
                P_AR_TRANSFER.name,
                "transfer_id",
                SHEET_AR_TRANSACTIONS,
                f"_drill_pass_{P_AR_TRANSFER.name}_on_txn",
            ),
            (
                FG_AR_DRILL_ACTIVITY_DATE_ON_TXN,
                P_AR_ACTIVITY_DATE.name,
                "posted_date",
                SHEET_AR_TRANSACTIONS,
                f"_drill_pass_{P_AR_ACTIVITY_DATE.name}_on_txn",
            ),
            (
                FG_AR_DRILL_TRANSFER_TYPE_ON_TXN,
                P_AR_TRANSFER_TYPE.name,
                "transfer_type",
                SHEET_AR_TRANSACTIONS,
                f"_drill_pass_{P_AR_TRANSFER_TYPE.name}_on_txn",
            ),
            (
                FG_AR_DRILL_ACCOUNT_ON_TXN,
                P_AR_ACCOUNT.name,
                "account_id",
                SHEET_AR_TRANSACTIONS,
                f"_drill_pass_{P_AR_ACCOUNT.name}_on_txn",
            ),
            (
                FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER,
                P_AR_LEDGER.name,
                "ledger_account_id",
                SHEET_AR_BALANCES,
                f"_drill_pass_{P_AR_LEDGER.name}_on_balances_subledger",
            ),
        ],
    )
    def test_drill_uses_calc_field_pass_shape(
        self,
        ar_output_dir,
        fg_id: str,
        parameter_name: str,
        column_name: str,
        sheet_id: str,
        calc_field_name: str,
    ):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")

        # Calc field must exist and reference both the param and the
        # target column. Sentinel must appear so the no-narrowing
        # branch is wired.
        calc_fields = analysis["Definition"].get("CalculatedFields", [])
        calc = next(
            (c for c in calc_fields if c["Name"] == calc_field_name),
            None,
        )
        assert calc is not None, (
            f"Expected calc field {calc_field_name} in the analysis definition"
        )
        expr = calc["Expression"]
        assert f"${{{parameter_name}}}" in expr
        assert f"{{{column_name}}}" in expr
        assert "'PASS'" in expr
        assert "'__ALL__'" in expr

        # Filter group must reference the calc field with a literal
        # CategoryValue=PASS — never a ParameterName binding.
        fg = _find_fg(analysis, fg_id)
        filt = fg["Filters"][0]["CategoryFilter"]
        assert filt["Column"]["ColumnName"] == calc_field_name
        cfg = filt["Configuration"]["CustomFilterConfiguration"]
        assert cfg["MatchOperator"] == "EQUALS"
        assert cfg["CategoryValue"] == "PASS"
        assert "ParameterName" not in cfg

        # Sheet scope must match the spec's intended target.
        scopes = fg["ScopeConfiguration"]["SelectedSheets"][
            "SheetVisualScopingConfigurations"
        ]
        assert [s["SheetId"] for s in scopes] == [sheet_id]

        # Parameter must declare the sentinel as its default so the
        # never-touched state passes through the calc field as ALL.
        params = analysis["Definition"]["ParameterDeclarations"]
        param = next(
            p["StringParameterDeclaration"]
            for p in params
            if p.get("StringParameterDeclaration", {}).get("Name") == parameter_name
        )
        assert param["DefaultValues"]["StaticValues"] == ["__ALL__"]

    def test_ledger_drill_targets_subledger_table_only(self, ar_output_dir):
        """The Balances ledger-to-subledger drill must not wipe the ledger
        table; it's scoped to the sub-ledger table visual only via
        SELECTED_VISUALS."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER)
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
        assert _set_param(v) == (P_AR_LEDGER.name, "ar-bal-ledger-id")

    def test_balances_subledger_drills_to_transactions(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-balances-subledger-table")
        assert v["Actions"][0]["Trigger"] == "DATA_POINT_CLICK"
        assert _drill_nav_target(v) == SHEET_AR_TRANSACTIONS
        assert _set_param(v) == (P_AR_SUBLEDGER.name, "ar-bal-subledger-id")

    def test_transfers_summary_drills_to_transactions(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-transfers-summary-table")
        assert _drill_nav_target(v) == SHEET_AR_TRANSACTIONS
        assert _set_param(v) == (P_AR_TRANSFER.name, "ar-xfr-id")

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

    def test_balances_subledger_right_click_drills_to_daily_statement(
        self, ar_output_dir,
    ):
        """Right-click on a sub-ledger row sets BOTH pArDsAccountId AND
        pArDsBalanceDate before navigating to Daily Statement — so the
        destination renders the right account-day with no further
        clicks. Convention: right-click goes RIGHT (toward more
        detail); the same cell's left-click still drills to
        Transactions, asserted separately."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-balances-subledger-table")
        actions_by_id = {a["CustomActionId"]: a for a in v["Actions"]}
        action = actions_by_id["action-ar-balances-subledger-to-daily-statement"]
        assert action["Trigger"] == "DATA_POINT_MENU"
        nav = next(
            op["NavigationOperation"]
            for op in action["ActionOperations"]
            if "NavigationOperation" in op
        )
        assert nav["LocalNavigationConfiguration"]["TargetSheetId"] == (
            SHEET_AR_DAILY_STATEMENT
        )
        set_op = next(
            op["SetParametersOperation"]
            for op in action["ActionOperations"]
            if "SetParametersOperation" in op
        )
        pvcs = [
            (p["DestinationParameterName"], p["Value"]["SourceField"])
            for p in set_op["ParameterValueConfigurations"]
        ]
        assert pvcs == [
            (P_AR_DS_ACCOUNT.name, "ar-bal-subledger-id"),
            (P_AR_DS_BALANCE_DATE.name, "ar-bal-subledger-date"),
        ]


class TestTransactionsDrillStaleParamHygiene:
    """Every drill that targets SHEET_AR_TRANSACTIONS must write all five
    PASS-filtered params — explicit SourceField for the parameters the
    drill narrows on, sentinel reset for the rest. K.2 bug class: an
    omitted param inherits its prior-drill value and silently narrows
    the destination to zero rows. The ``_ar_drill_to_transactions``
    helper enforces this, but these tests pin the contract at the
    output level so a regression that bypasses the helper is caught
    here, not in the live dashboard."""

    EXPECTED_PARAMS = {
        P_AR_SUBLEDGER.name,
        P_AR_TRANSFER.name,
        P_AR_ACTIVITY_DATE.name,
        P_AR_TRANSFER_TYPE.name,
        P_AR_ACCOUNT.name,
    }

    @pytest.mark.parametrize(
        "visual_id, action_id, source_writes",
        [
            (
                "ar-balances-subledger-table",
                "action-ar-balances-subledger-to-txn",
                {P_AR_SUBLEDGER.name: "ar-bal-subledger-id"},
            ),
            (
                "ar-transfers-summary-table",
                "action-ar-transfers-to-txn",
                {P_AR_TRANSFER.name: "ar-xfr-id"},
            ),
            (
                "ar-todays-exc-table",
                "action-ar-todays-exc-to-txn",
                {P_AR_TRANSFER.name: "ar-todays-exc-transfer-id"},
            ),
            (
                "ar-todays-exc-table",
                "action-ar-todays-exc-to-txn-by-account",
                {
                    P_AR_ACCOUNT.name: "ar-todays-exc-account",
                    P_AR_ACTIVITY_DATE.name: "ar-todays-exc-date",
                },
            ),
        ],
    )
    def test_drill_writes_every_pass_filtered_param(
        self,
        ar_output_dir,
        visual_id: str,
        action_id: str,
        source_writes: dict[str, str],
    ):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, visual_id)
        actions_by_id = {a["CustomActionId"]: a for a in v["Actions"]}
        action = actions_by_id[action_id]

        set_op = next(
            op["SetParametersOperation"]
            for op in action["ActionOperations"]
            if "SetParametersOperation" in op
        )
        pvcs = set_op["ParameterValueConfigurations"]

        # Every PASS-filtered Transactions param must appear exactly once.
        written = [pvc["DestinationParameterName"] for pvc in pvcs]
        assert set(written) == self.EXPECTED_PARAMS, (
            f"{action_id}: expected to write {self.EXPECTED_PARAMS}, "
            f"got {set(written)}"
        )
        assert len(written) == len(set(written)), (
            f"{action_id}: duplicate destination parameter writes: {written}"
        )

        # Each named source param resolves to its explicit field id;
        # every other param resolves to the sentinel reset shape.
        by_param = {pvc["DestinationParameterName"]: pvc for pvc in pvcs}
        for param, expected_field in source_writes.items():
            assert by_param[param]["Value"]["SourceField"] == expected_field
        for param in self.EXPECTED_PARAMS - source_writes.keys():
            value = by_param[param]["Value"]
            assert "CustomValuesConfiguration" in value, (
                f"{action_id}: param {param!r} should be sentinel-reset "
                f"but is {value!r}"
            )
            assert value["CustomValuesConfiguration"]["CustomValues"][
                "StringValues"
            ] == ["__ALL__"]

    def test_helper_param_set_matches_analysis_drill_specs(self):
        """``_AR_TXN_PASS_FILTERED_PARAMS`` (the helper's auto-reset set)
        must mirror the SHEET_AR_TRANSACTIONS specs in
        ``analysis._DRILL_SPECS``. If a new drill spec is added there,
        the helper has to know about it — otherwise drills that don't
        explicitly write the new param leave it stale on the destination
        sheet (the K.2 bug class) and silently ship that way."""
        from quicksight_gen.account_recon import analysis as ar_analysis
        from quicksight_gen.account_recon.visuals import (
            _AR_TXN_PASS_FILTERED_PARAMS,
        )

        spec_param_names = {
            spec.parameter.name
            for spec in ar_analysis._DRILL_SPECS
            if spec.sheet_id == SHEET_AR_TRANSACTIONS
        }
        helper_param_names = {p.name for p in _AR_TXN_PASS_FILTERED_PARAMS}
        assert helper_param_names == spec_param_names, (
            "Helper auto-reset set drifted from analysis._DRILL_SPECS — "
            f"helper has {helper_param_names}, specs have {spec_param_names}"
        )


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
            ("ar-transfers-summary-table", "ar-xfr-id"),
        ],
    )
    def test_left_click_drill_sources_have_link_format(
        self, ar_output_dir, visual_id: str, field_id: str,
    ):
        """Left-click-only drill-source cells get plain-accent TextColor
        (no background tint — that's reserved for cells that also carry
        a right-click menu drill)."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, visual_id)
        cells = [c for c in _cf_cells(v) if c["FieldId"] == field_id]
        assert cells, (
            f"{visual_id} missing conditional formatting for {field_id}"
        )
        tf = cells[0]["TextFormat"]
        assert "TextColor" in tf
        assert "BackgroundColor" not in tf

    @pytest.mark.parametrize(
        "visual_id, field_id",
        [
            # Right-click-only — left-click reserved for same-sheet filter.
            ("ar-balances-ledger-table", "ar-bal-ledger-id"),
            # Both clicks — left to Transactions, right to Daily Statement.
            ("ar-balances-subledger-table", "ar-bal-subledger-id"),
        ],
    )
    def test_right_click_drill_sources_use_menu_format(
        self, ar_output_dir, visual_id: str, field_id: str,
    ):
        """Cells with a right-click (DATA_POINT_MENU) action get accent
        text + tint background — distinguishes them from plain-accent
        cells whose only action is a left-click drill."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, visual_id)
        cells = [c for c in _cf_cells(v) if c["FieldId"] == field_id]
        assert cells
        tf = cells[0]["TextFormat"]
        assert "TextColor" in tf
        assert "BackgroundColor" in tf


class TestDailyStatementFilters:
    """The Daily Statement sheet's two pickers (account + day) drive the
    KPIs and detail table via parameters — both are also written by the
    right-click drill from the Balances sub-ledger table. These tests
    pin the exact wiring (parameter name, filter type, NullOption,
    scope, control type) so a future regeneration that breaks any of
    them fails loudly here, not silently in the live dashboard."""

    def test_account_filter_parameter_bound_with_no_all_default(
        self, ar_output_dir,
    ):
        """Account picker is a CategoryFilter parameter-bound to
        pArDsAccountId, with NullOption=NON_NULLS_ONLY so the sheet
        renders empty until an account is picked. NullOption=ALL_VALUES
        would aggregate KPIs across every account on first load — a
        single unified statement that doesn't make business sense."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, FG_AR_DS_ACCOUNT)
        cf = fg["Filters"][0]["CategoryFilter"]
        custom = cf["Configuration"]["CustomFilterConfiguration"]
        assert custom["MatchOperator"] == "EQUALS"
        assert custom["ParameterName"] == P_AR_DS_ACCOUNT.name
        assert custom["NullOption"] == "NON_NULLS_ONLY"
        assert cf["Column"]["ColumnName"] == "account_id"

    def test_balance_date_filter_uses_time_equality_not_range(
        self, ar_output_dir,
    ):
        """The picker is SINGLE_VALUED; a TimeRangeFilter would render
        the picker broken in the QuickSight UI (silently — no error at
        deploy time). Lock the filter type so a future swap to
        TimeRangeFilter is caught here."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, FG_AR_DS_BALANCE_DATE)
        f = fg["Filters"][0]
        assert "TimeEqualityFilter" in f
        assert "TimeRangeFilter" not in f
        teq = f["TimeEqualityFilter"]
        assert teq["ParameterName"] == P_AR_DS_BALANCE_DATE.name
        assert teq["TimeGranularity"] == "DAY"
        assert teq["Column"]["ColumnName"] == "balance_date"

    @pytest.mark.parametrize(
        "fg_id",
        [FG_AR_DS_ACCOUNT, FG_AR_DS_BALANCE_DATE],
    )
    def test_filter_scoped_to_daily_statement_only(
        self, ar_output_dir, fg_id: str,
    ):
        """Both filters are sheet-scoped to Daily Statement — wider
        scope would leak the per-day picker onto Balances/Transactions
        and surprise users on those tabs."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, fg_id)
        scopes = fg["ScopeConfiguration"]["SelectedSheets"][
            "SheetVisualScopingConfigurations"
        ]
        assert [s["SheetId"] for s in scopes] == [SHEET_AR_DAILY_STATEMENT]
        assert all(s["Scope"] == "ALL_VISUALS" for s in scopes)

    @pytest.mark.parametrize(
        "fg_id",
        [FG_AR_DS_ACCOUNT, FG_AR_DS_BALANCE_DATE],
    )
    def test_filter_uses_all_datasets_so_summary_and_detail_both_filter(
        self, ar_output_dir, fg_id: str,
    ):
        """CrossDataset=ALL_DATASETS so the picker filters BOTH the
        summary (KPIs) and transactions (detail table) datasets — both
        expose account_id / balance_date, but a SINGLE_DATASET scope
        would only filter the dataset whose ColumnIdentifier names it."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, fg_id)
        assert fg["CrossDataset"] == "ALL_DATASETS"

    def _ds_parameter_controls(self, analysis: dict) -> dict[str, dict]:
        sheet = _find_sheet(analysis, SHEET_AR_DAILY_STATEMENT)
        controls: dict[str, dict] = {}
        for ctrl in sheet.get("ParameterControls", []):
            for body in ctrl.values():
                if isinstance(body, dict) and "ParameterControlId" in body:
                    controls[body["ParameterControlId"]] = body
        return controls

    def test_sheet_uses_parameter_controls_not_filter_controls(
        self, ar_output_dir,
    ):
        """A FilterControl whose backing filter is parameter-bound shows
        up disabled in the UI ("this control was disabled because the
        filter is using parameters"). The widgets must be ParameterControls
        so the user can drive the parameter directly."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        sheet = _find_sheet(analysis, SHEET_AR_DAILY_STATEMENT)
        assert sheet.get("FilterControls") in (None, []), (
            "Daily Statement must not declare FilterControls — the "
            "parameter-bound filters disable them in the UI"
        )
        assert len(sheet.get("ParameterControls", [])) == 2

    def test_account_control_is_dropdown_bound_to_account_parameter(
        self, ar_output_dir,
    ):
        """SINGLE_SELECT dropdown that writes pArDsAccountId. Values are
        sourced via LinkToDataSetColumn from the daily-statement-summary
        dataset's account_id column — the link query bypasses the
        sheet's own parameter-bound filter, so users see every account
        rather than the empty NON_NULLS_ONLY slice."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        ctrl = self._ds_parameter_controls(analysis)["ctrl-ar-ds-account"]
        assert ctrl["Type"] == "SINGLE_SELECT"
        assert ctrl["SourceParameterName"] == P_AR_DS_ACCOUNT.name
        link = ctrl["SelectableValues"]["LinkToDataSetColumn"]
        assert link["ColumnName"] == "account_id"

    def test_balance_date_control_is_picker_bound_to_date_parameter(
        self, ar_output_dir,
    ):
        """ParameterDateTimePickerControl (no Type field — the parameter
        decides single vs. multi). The parameter is single-valued and
        defaults to today's date."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        ctrl = self._ds_parameter_controls(analysis)[
            "ctrl-ar-ds-balance-date"
        ]
        assert ctrl["SourceParameterName"] == P_AR_DS_BALANCE_DATE.name


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


class TestTransferTypeControl:
    """Phase 5.5 transfer-type filter surfaces as a CrossSheet control on
    Transfers / Transactions; Balances has no transfer_type column in
    scope so the control would dangle there."""

    def _cross_sheet_sources(self, sheet: dict) -> set[str]:
        sources: set[str] = set()
        for ctrl in sheet.get("FilterControls", []):
            cs = ctrl.get("CrossSheet")
            if cs:
                sources.add(cs["SourceFilterId"])
        return sources

    @pytest.mark.parametrize(
        "sheet_id",
        [SHEET_AR_TRANSFERS, SHEET_AR_TRANSACTIONS],
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
        """The Transactions dataset must expose origin (Phase G: from
        the shared `transactions` table where origin is denormalized
        per-row)."""
        path = ar_output_dir / "datasets" / "qs-gen-ar-transactions-dataset.json"
        data = json.loads(path.read_text())
        table = next(iter(data["PhysicalTableMap"].values()))
        cols = {c["Name"] for c in table["CustomSql"]["Columns"]}
        assert "origin" in cols
        assert "t.origin" in table["CustomSql"]["SqlQuery"]

    def test_transactions_dataset_has_no_transfer_type_filter(
        self, ar_output_dir,
    ):
        """The AR Transactions dataset SQL no longer carries the
        artificial AR-only transfer_type WHERE clause (I.4.B Commit 2).

        Pre-I.4 the dataset filtered
        ``WHERE t.transfer_type IN ('ach', 'wire', 'internal', 'cash',
        'funding_batch', 'fee', 'clearing_sweep')`` which hid PR-side
        legs (sale / settlement / payment / external_txn) from the
        Transactions tab. Under the unified-AR framing the dataset is
        unscoped at the SQL level; the Transfer Type multi-select
        control on the tab is the analyst-side filter affordance.

        Regression guard: if a future commit re-adds the WHERE filter
        this assertion breaks loudly.
        """
        path = ar_output_dir / "datasets" / "qs-gen-ar-transactions-dataset.json"
        data = json.loads(path.read_text())
        table = next(iter(data["PhysicalTableMap"].values()))
        sql = table["CustomSql"]["SqlQuery"]
        assert "t.transfer_type IN" not in sql, (
            "AR Transactions dataset SQL re-acquired a "
            "`t.transfer_type IN (...)` filter. I.4.B Commit 2 removed "
            "it; if it came back, audit account_recon/datasets.py edit "
            "history before re-applying."
        )
        assert "transfer_type" in sql, (
            "AR Transactions dataset no longer projects transfer_type. "
            "The column is the dataset-side anchor for the Transfer Type "
            "multi-select control on the Transactions tab."
        )


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

    def test_sasquatch_bank_ar_name(self):
        from quicksight_gen.account_recon.analysis import build_analysis

        name = build_analysis(self._cfg("sasquatch-bank-ar")).Name
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
        # Both seeds insert into the shared transactions / ar_*_accounts tables;
        # PR-only ledger marker + AR-only limits table prove --all stitched both.
        assert "INSERT INTO transactions" in content
        assert "pr-merchant-ledger" in content  # PR-only ledger account
        assert "INSERT INTO ar_ledger_transfer_limits" in content  # AR-only
