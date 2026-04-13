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
    ACCOUNTS,
    PARENT_ACCOUNTS,
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


class TestDemoDeterminism:
    def test_same_anchor_identical_output(self):
        assert generate_demo_sql(ANCHOR) == generate_demo_sql(ANCHOR)

    def test_different_anchor_shifts_dates(self):
        a = generate_demo_sql(date(2026, 1, 1))
        b = generate_demo_sql(date(2026, 6, 1))
        assert a != b


class TestDemoRowCounts:
    def test_parent_accounts(self, ar_parsed):
        assert len(ar_parsed["ar_parent_accounts"]) == len(PARENT_ACCOUNTS)

    def test_accounts(self, ar_parsed):
        assert len(ar_parsed["ar_accounts"]) == len(ACCOUNTS)

    def test_transactions(self, ar_parsed):
        # 60 base transfers + 3 planted breach + 3 planted overdraft
        # = 66 transfers × 2 legs each = 132 transactions
        assert len(ar_parsed["ar_transactions"]) == 132

    def test_parent_transfer_limits(self, ar_parsed):
        from quicksight_gen.account_recon.demo_data import _PARENT_LIMITS
        assert (
            len(ar_parsed["ar_parent_transfer_limits"]) == len(_PARENT_LIMITS)
        )

    def test_parent_daily_balances(self, ar_parsed):
        # 3 internal parents × 41 days (0..40 inclusive) = 123 rows.
        # External parents are not reconciled (SPEC "Reconciliation scope").
        assert len(ar_parsed["ar_parent_daily_balances"]) == 123

    def test_account_daily_balances(self, ar_parsed):
        # 6 internal children × 41 days = 246 rows (the two external
        # parents' four children are omitted).
        assert len(ar_parsed["ar_account_daily_balances"]) == 246


class TestReferentialIntegrity:
    """FK-safe seeds — every FK value exists in the parent table."""

    def _col(self, rows: list[str], idx: int) -> list[str]:
        return [
            [p.strip().strip("'") for p in row.split(",")][idx]
            for row in rows
        ]

    def test_account_parent_fk(self, ar_parsed):
        parent_ids = set(self._col(ar_parsed["ar_parent_accounts"], 0))
        child_parents = set(self._col(ar_parsed["ar_accounts"], 3))
        assert child_parents.issubset(parent_ids), (
            f"Unknown parent_account_ids: {child_parents - parent_ids}"
        )

    def test_transaction_account_fk(self, ar_parsed):
        account_ids = set(self._col(ar_parsed["ar_accounts"], 0))
        txn_accounts = set(self._col(ar_parsed["ar_transactions"], 1))
        assert txn_accounts.issubset(account_ids)

    def test_parent_daily_balance_fk(self, ar_parsed):
        parent_ids = set(self._col(ar_parsed["ar_parent_accounts"], 0))
        bal_parents = set(self._col(ar_parsed["ar_parent_daily_balances"], 0))
        assert bal_parents.issubset(parent_ids)

    def test_account_daily_balance_fk(self, ar_parsed):
        account_ids = set(self._col(ar_parsed["ar_accounts"], 0))
        bal_accounts = set(self._col(ar_parsed["ar_account_daily_balances"], 0))
        assert bal_accounts.issubset(account_ids)


class TestScenarioCoverage:
    """Guarantees every AR visual has non-empty data out-of-the-box."""

    def test_failed_transactions_exist(self, ar_parsed):
        """Status=failed must be present so the Transactions bar chart and
        the failed-transaction KPI aren't empty."""
        statuses = [
            [p.strip().strip("'") for p in row.split(",")][5]
            for row in ar_parsed["ar_transactions"]
        ]
        failed = sum(1 for s in statuses if s == "failed")
        # 4 failed-leg + 8 all-failed (both legs) = 12
        assert failed >= 8, f"Only {failed} failed transactions"

    def test_posted_and_failed_statuses_both_present(self, ar_parsed):
        statuses = {
            [p.strip().strip("'") for p in row.split(",")][5]
            for row in ar_parsed["ar_transactions"]
        }
        assert {"posted", "failed"}.issubset(statuses)

    def test_internal_and_external_parents_exist(self, ar_parsed):
        is_internals = {
            [p.strip() for p in row.split(",")][2].strip().lower()
            for row in ar_parsed["ar_parent_accounts"]
        }
        assert {"true", "false"}.issubset(is_internals), (
            "Need both internal + external parents for scope splits"
        )

    def test_parent_drift_is_planted(self, ar_parsed):
        """Parent-level drift plants must include both signs and each
        planted (parent, date) cell must exist in the balances table."""
        from quicksight_gen.account_recon.demo_data import _PARENT_DRIFT_PLANT

        assert len(_PARENT_DRIFT_PLANT) >= 3, "Need several parent drift cells"
        deltas = [Decimal(d) for _, _, d in _PARENT_DRIFT_PLANT]
        assert any(d > 0 for d in deltas), "Need a positive parent drift"
        assert any(d < 0 for d in deltas), "Need a negative parent drift"

        balance_rows = {
            tuple(p.strip().strip("'") for p in row.split(",")[:2])
            for row in ar_parsed["ar_parent_daily_balances"]
        }
        from datetime import timedelta
        for parent_id, days_ago, _ in _PARENT_DRIFT_PLANT:
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            assert (parent_id, bdate) in balance_rows, (
                f"Missing balance row for planted drift ({parent_id}, {bdate})"
            )

    def test_child_drift_is_planted(self, ar_parsed):
        """Child-level drift plants must include both signs and land on
        internal child accounts with rows in ar_account_daily_balances."""
        from quicksight_gen.account_recon.demo_data import _CHILD_DRIFT_PLANT

        assert len(_CHILD_DRIFT_PLANT) >= 3, "Need several child drift cells"
        deltas = [Decimal(d) for _, _, d in _CHILD_DRIFT_PLANT]
        assert any(d > 0 for d in deltas), "Need a positive child drift"
        assert any(d < 0 for d in deltas), "Need a negative child drift"

        balance_rows = {
            tuple(p.strip().strip("'") for p in row.split(",")[:2])
            for row in ar_parsed["ar_account_daily_balances"]
        }
        from datetime import timedelta
        for account_id, days_ago, _ in _CHILD_DRIFT_PLANT:
            bdate = (ANCHOR - timedelta(days=days_ago)).isoformat()
            assert (account_id, bdate) in balance_rows, (
                f"Missing balance row for planted drift ({account_id}, {bdate})"
            )

    def test_parent_and_child_drift_are_independent(self):
        """Parent-level and child-level drift plants should surface
        different rows on the Exceptions tab — guard against cell overlap
        that would make them look like the same finding in two places."""
        from quicksight_gen.account_recon.demo_data import (
            _CHILD_DRIFT_PLANT,
            _PARENT_DRIFT_PLANT,
        )
        from quicksight_gen.account_recon.demo_data import ACCOUNTS

        parent_cells = {(p, d) for p, d, _ in _PARENT_DRIFT_PLANT}
        # Map child accounts back to their parents so we can detect overlap.
        account_parent = {aid: pid for aid, _n, pid in ACCOUNTS}
        child_by_parent_day = {
            (account_parent[aid], d)
            for aid, d, _ in _CHILD_DRIFT_PLANT
        }
        assert not (parent_cells & child_by_parent_day), (
            "Parent and child drift plants collide on the same "
            "(parent, day) — pick disjoint cells"
        )

    def test_memos_present(self, ar_sql):
        """Memos must flow onto transactions so the transfer-summary memo
        column is non-empty."""
        for memo_fragment in ("Feed lot settlement", "Grain silo delivery"):
            assert memo_fragment in ar_sql

    def _transfer_legs_by_scope(
        self, ar_parsed,
    ) -> dict[str, tuple[int, int]]:
        """Return {transfer_id: (internal_leg_count, external_leg_count)}.

        Parses account.is_internal from ar_accounts, then groups
        ar_transactions by transfer_id and counts the legs on each side.
        Used by the scenario coverage tests for transfer pair-patterns.
        """
        internal_by_account: dict[str, bool] = {}
        for row in ar_parsed["ar_accounts"]:
            parts = [p.strip() for p in row.split(",")]
            aid = parts[0].strip("'")
            is_internal = parts[2].strip().lower() == "true"
            internal_by_account[aid] = is_internal

        buckets: dict[str, list[bool]] = {}
        for row in ar_parsed["ar_transactions"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            account_id = parts[1]
            transfer_id = parts[2]
            buckets.setdefault(transfer_id, []).append(
                internal_by_account[account_id]
            )
        return {
            tid: (sum(flags), sum(1 for f in flags if not f))
            for tid, flags in buckets.items()
        }

    def test_cross_scope_transfers_exist(self, ar_parsed):
        """Transfers with one internal leg + one external leg must exist
        so the dashboard has examples where the external leg doesn't
        affect any tracked balance."""
        by_scope = self._transfer_legs_by_scope(ar_parsed)
        cross_scope = [
            tid for tid, (i, e) in by_scope.items() if i >= 1 and e >= 1
        ]
        assert len(cross_scope) >= 20, (
            f"Need ≥20 cross-scope transfers, got {len(cross_scope)}"
        )

    def test_internal_only_transfers_exist(self, ar_parsed):
        """Transfers where both legs land on internal children must exist
        so drift bugs that only manifest when one transfer touches two
        tracked balances are surfaced by the demo data.

        Without these, a query that sums transfer legs by transfer_id
        instead of by account_id would silently work on cross-scope-only
        seed data — the bug only shows up when both legs are tracked.
        """
        by_scope = self._transfer_legs_by_scope(ar_parsed)
        internal_only = [
            tid for tid, (i, e) in by_scope.items() if i >= 2 and e == 0
        ]
        assert len(internal_only) >= 15, (
            f"Need ≥15 internal-internal transfers, got {len(internal_only)}"
        )

    def test_failed_transfer_pattern_coverage(self, ar_parsed):
        """Both failed-leg and fully-failed scenarios must include at
        least one internal-internal instance — otherwise a regression in
        how failed internal legs affect child balances would slip
        through the demo."""
        by_scope = self._transfer_legs_by_scope(ar_parsed)
        # Pull all transactions grouped by transfer to check statuses.
        statuses_by_transfer: dict[str, list[str]] = {}
        for row in ar_parsed["ar_transactions"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            transfer_id = parts[2]
            status = parts[5]
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

    def test_all_four_transfer_types_present(self, ar_parsed):
        """All four transfer types must have traffic so the
        transfer-type filter has something to filter on."""
        types = {
            [p.strip().strip("'") for p in row.split(",")][6]
            for row in ar_parsed["ar_transactions"]
        }
        assert types == {"ach", "wire", "internal", "cash"}, (
            f"Expected all four transfer types, got {types}"
        )

    def test_parent_limits_seeded(self, ar_parsed):
        """Parent transfer limits must be seeded — otherwise the
        limit-breach view has no thresholds to compare against."""
        from quicksight_gen.account_recon.demo_data import _PARENT_LIMITS

        assert len(_PARENT_LIMITS) >= 3, "Need ≥3 parent limit rows"
        types = {xtype for _pid, xtype, _lim in _PARENT_LIMITS}
        assert len(types) >= 2, "Limits must cover ≥2 transfer types"
        parents = {pid for pid, _x, _l in _PARENT_LIMITS}
        assert len(parents) >= 2, "Limits must span ≥2 parents"

    def test_limit_breaches_materialize(self, ar_parsed):
        """Planted breach cells must emerge from running the view
        logic on the seed data — the query sums outbound |amount| per
        (child, day, type), joins parent-limits, and keeps rows where
        total > limit."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import (
            _LIMIT_BREACH_PLANT,
            _PARENT_LIMITS,
        )

        is_internal: dict[str, bool] = {}
        parent_by_account: dict[str, str] = {}
        for row in ar_parsed["ar_accounts"]:
            parts = [p.strip() for p in row.split(",")]
            aid = parts[0].strip().strip("'")
            is_internal[aid] = parts[2].strip().lower() == "true"
            parent_by_account[aid] = parts[3].strip().strip("'")

        totals: dict[tuple[str, str, str], Decimal] = {}
        for row in ar_parsed["ar_transactions"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            acct = parts[1]
            amount = Decimal(parts[3])
            day = parts[4].split(" ")[0]
            status = parts[5]
            xtype = parts[6]
            if status == "failed":
                continue
            if amount >= 0:
                continue
            if not is_internal.get(acct):
                continue
            key = (acct, day, xtype)
            totals[key] = totals.get(key, Decimal("0")) + abs(amount)

        limit_map = {
            (pid, xtype): Decimal(lim) for pid, xtype, lim in _PARENT_LIMITS
        }
        breaches: set[tuple[str, str, str]] = set()
        for (acct, day, xtype), outbound in totals.items():
            parent = parent_by_account[acct]
            limit = limit_map.get((parent, xtype))
            if limit is not None and outbound > limit:
                breaches.add((acct, day, xtype))

        assert len(breaches) >= 3, (
            f"Expected ≥3 limit-breach cells, got {len(breaches)}"
        )
        for acct, days_ago, xtype, _amt, _memo in _LIMIT_BREACH_PLANT:
            day = (ANCHOR - timedelta(days=days_ago)).isoformat()
            assert (acct, day, xtype) in breaches, (
                f"Planted breach ({acct}, {day}, {xtype}) didn't materialize"
            )

    def test_overdrafts_materialize(self, ar_parsed):
        """Planted overdraft cells must show up as balance < 0 in
        ar_account_daily_balances — the ar_child_overdraft view just
        filters on that condition."""
        from datetime import timedelta
        from quicksight_gen.account_recon.demo_data import _OVERDRAFT_PLANT

        balances: dict[tuple[str, str], Decimal] = {}
        for row in ar_parsed["ar_account_daily_balances"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            balances[(parts[0], parts[1])] = Decimal(parts[2])

        negative = [k for k, v in balances.items() if v < 0]
        assert len(negative) >= 3, (
            f"Expected ≥3 overdraft rows, got {len(negative)}"
        )
        for acct, days_ago, _amt, _memo in _OVERDRAFT_PLANT:
            day = (ANCHOR - timedelta(days=days_ago)).isoformat()
            bal = balances.get((acct, day))
            assert bal is not None and bal < 0, (
                f"Planted overdraft cell ({acct}, {day}) is not negative "
                f"(got {bal})"
            )

    def test_all_plants_disjoint(self):
        """Each of the four exception tables must surface a different
        set of findings — drift, breach, and overdraft plants must not
        share child×day cells. Otherwise the Exceptions tab would show
        the same row across multiple tables and obscure the four
        distinct reconciliation checks."""
        from quicksight_gen.account_recon.demo_data import (
            _CHILD_DRIFT_PLANT,
            _LIMIT_BREACH_PLANT,
            _OVERDRAFT_PLANT,
            _PARENT_DRIFT_PLANT,
        )

        child_cells = {(a, d) for a, d, _ in _CHILD_DRIFT_PLANT}
        breach_cells = {(a, d) for a, d, _, _, _ in _LIMIT_BREACH_PLANT}
        overdraft_cells = {(a, d) for a, d, _, _ in _OVERDRAFT_PLANT}

        assert not (child_cells & breach_cells), (
            "Child drift and limit breach plants share child×day cells"
        )
        assert not (child_cells & overdraft_cells), (
            "Child drift and overdraft plants share child×day cells"
        )
        assert not (breach_cells & overdraft_cells), (
            "Breach and overdraft plants share child×day cells"
        )

        account_parent = {aid: pid for aid, _n, pid in ACCOUNTS}
        parent_cells = {(p, d) for p, d, _ in _PARENT_DRIFT_PLANT}
        breach_parent_cells = {
            (account_parent[a], d) for a, d, _, _, _ in _LIMIT_BREACH_PLANT
        }
        overdraft_parent_cells = {
            (account_parent[a], d) for a, d, _, _ in _OVERDRAFT_PLANT
        }
        assert not (parent_cells & breach_parent_cells), (
            "Parent drift and breach plants share (parent, day) cells"
        )
        assert not (parent_cells & overdraft_parent_cells), (
            "Parent drift and overdraft plants share (parent, day) cells"
        )


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
        tables = set(re.findall(r"INSERT INTO (ar_\w+)", ar_sql))
        assert tables == {
            "ar_parent_accounts",
            "ar_accounts",
            "ar_transactions",
            "ar_parent_transfer_limits",
            "ar_parent_daily_balances",
            "ar_account_daily_balances",
        }

    def test_fk_safe_order(self, ar_sql):
        positions = {}
        for m in re.finditer(r"INSERT INTO (ar_\w+)", ar_sql):
            positions.setdefault(m.group(1), m.start())
        assert positions["ar_parent_accounts"] < positions["ar_accounts"]
        assert positions["ar_accounts"] < positions["ar_transactions"]
        # ar_parent_daily_balances FKs to parent_accounts
        assert (
            positions["ar_parent_accounts"]
            < positions["ar_parent_daily_balances"]
        )
        # ar_account_daily_balances FKs to accounts
        assert (
            positions["ar_accounts"]
            < positions["ar_account_daily_balances"]
        )
        # ar_parent_transfer_limits FKs to parent_accounts
        assert (
            positions["ar_parent_accounts"]
            < positions["ar_parent_transfer_limits"]
        )


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
            "ar_parent_accounts",
            "ar_accounts",
            "ar_parent_daily_balances",
            "ar_account_daily_balances",
            "ar_transactions",
            "ar_parent_transfer_limits",
        ):
            assert f"CREATE TABLE {table}" in schema_sql

    def test_creates_ar_views(self, schema_sql):
        for view in (
            "ar_computed_account_daily_balance",
            "ar_computed_parent_daily_balance",
            "ar_account_balance_drift",
            "ar_parent_balance_drift",
            "ar_transfer_net_zero",
            "ar_transfer_summary",
            "ar_child_daily_outbound_by_type",
            "ar_child_limit_breach",
            "ar_child_overdraft",
        ):
            assert f"CREATE VIEW {view}" in schema_sql

    def test_transaction_transfer_type_column(self, schema_sql):
        """ar_transactions must carry the transfer_type column (Phase 5)."""
        assert "transfer_type" in schema_sql
        # Column appears in the CREATE TABLE ar_transactions block
        m = re.search(
            r"CREATE TABLE ar_transactions \((.*?)\);",
            schema_sql,
            re.DOTALL,
        )
        assert m, "ar_transactions CREATE TABLE missing"
        assert "transfer_type" in m.group(1), (
            "ar_transactions.transfer_type column missing"
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
    """Phase 5: shared date-range + 5 multi-selects + 4 Show-Only toggles +
    5 drill-down parameter filters = 15 filter groups."""

    _EXPECTED_IDS = {
        "fg-ar-date-range",
        "fg-ar-parent-account",
        "fg-ar-child-account",
        "fg-ar-transfer-status",
        "fg-ar-transaction-status",
        "fg-ar-transfer-type",
        "fg-ar-balances-parent-drift",
        "fg-ar-balances-child-drift",
        "fg-ar-balances-overdraft",
        "fg-ar-transactions-failed",
        "fg-ar-drill-account-on-txn",
        "fg-ar-drill-transfer-on-txn",
        "fg-ar-drill-parent-on-balances-child",
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
            "fg-ar-parent-account",
            "fg-ar-child-account",
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
            ("fg-ar-balances-parent-drift", SHEET_AR_BALANCES),
            ("fg-ar-balances-child-drift", SHEET_AR_BALANCES),
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
            "pArAccountId",
            "pArParentAccountId",
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
                "fg-ar-drill-account-on-txn",
                "pArAccountId",
                "account_id",
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
                "fg-ar-drill-parent-on-balances-child",
                "pArParentAccountId",
                "parent_account_id",
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

    def test_parent_drill_targets_child_table_only(self, ar_output_dir):
        """The Balances parent-to-child drill must not wipe the parent table;
        it's scoped to the child table visual only via SELECTED_VISUALS."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = _find_fg(analysis, "fg-ar-drill-parent-on-balances-child")
        scope = fg["ScopeConfiguration"]["SelectedSheets"][
            "SheetVisualScopingConfigurations"
        ][0]
        assert scope["Scope"] == "SELECTED_VISUALS"
        assert scope["VisualIds"] == ["ar-balances-child-table"]


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

    def test_balances_parent_right_click_sets_parent_parameter(self, ar_output_dir):
        """Right-click filters the child table on the same sheet via the
        pArParentAccountId parameter. AWS rejects a SetParametersOperation
        that isn't preceded by a NavigationOperation, so the action
        includes a no-op navigation back to the Balances sheet."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-balances-parent-table")
        action = v["Actions"][0]
        assert action["Trigger"] == "DATA_POINT_MENU"
        assert _drill_nav_target(v) == SHEET_AR_BALANCES
        assert _set_param(v) == ("pArParentAccountId", "ar-bal-parent-id")

    def test_balances_child_drills_to_transactions(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-balances-child-table")
        assert v["Actions"][0]["Trigger"] == "DATA_POINT_CLICK"
        assert _drill_nav_target(v) == SHEET_AR_TRANSACTIONS
        assert _set_param(v) == ("pArAccountId", "ar-bal-child-id")

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
                "ar-exc-parent-drift-table",
                SHEET_AR_BALANCES,
                "pArParentAccountId",
                "ar-exc-pdrift-parent-id",
            ),
            (
                "ar-exc-child-drift-table",
                SHEET_AR_TRANSACTIONS,
                "pArAccountId",
                "ar-exc-cdrift-account-id",
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

    def test_breach_drill_sets_account_date_and_type(self, ar_output_dir):
        """Limit-breach row → Transactions (account, day, type) slice.

        The breach table's three-parameter drill narrows Transactions to
        the exact (child, activity_date, transfer_type) that breached the
        limit — a two-param drill would leave type open and bury the
        signal in unrelated same-account rows."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-exc-breach-table")
        assert _drill_nav_target(v) == SHEET_AR_TRANSACTIONS
        assert _set_params_all(v) == [
            ("pArAccountId", "ar-exc-br-account-id"),
            ("pArActivityDate", "ar-exc-br-date-str"),
            ("pArTransferType", "ar-exc-br-type"),
        ]

    def test_overdraft_drill_sets_account_and_date(self, ar_output_dir):
        """Overdraft row → Transactions (account, day). Transfer-type isn't
        relevant — overdraft is the sum of legs regardless of type."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-exc-overdraft-table")
        assert _drill_nav_target(v) == SHEET_AR_TRANSACTIONS
        assert _set_params_all(v) == [
            ("pArAccountId", "ar-exc-od-account-id"),
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
            ("ar-balances-child-table", "ar-bal-child-id"),
            ("ar-transfers-summary-table", "ar-xfr-id"),
            ("ar-exc-parent-drift-table", "ar-exc-pdrift-parent-id"),
            ("ar-exc-child-drift-table", "ar-exc-cdrift-account-id"),
            ("ar-exc-nonzero-table", "ar-exc-nz-id"),
            ("ar-exc-breach-table", "ar-exc-br-account-id"),
            ("ar-exc-overdraft-table", "ar-exc-od-account-id"),
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

    def test_balances_parent_right_click_uses_menu_format(self, ar_output_dir):
        """Right-click (DATA_POINT_MENU) cells get an accent+tint style —
        distinguishing them from the plain-accent left-click cells."""
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        v = _find_visual(analysis, "ar-balances-parent-table")
        cells = [
            c for c in _cf_cells(v) if c["FieldId"] == "ar-bal-parent-id"
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
        assert titles.get("ctrl-ar-balances-parent-drift") == (
            "Show Only Parent Drift"
        )
        assert titles.get("ctrl-ar-balances-child-drift") == (
            "Show Only Child Drift"
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

    def test_child_drift_dataset_has_overdraft_status(self, ar_output_dir):
        """The Show-Only-Overdraft toggle binds to
        account_balance_drift.overdraft_status — verify the derived column
        is emitted in the dataset's InputColumns and SELECT."""
        path = ar_output_dir / "datasets" / (
            "qs-gen-ar-account-balance-drift-dataset.json"
        )
        data = json.loads(path.read_text())
        table = next(iter(data["PhysicalTableMap"].values()))
        cols = {c["Name"] for c in table["CustomSql"]["Columns"]}
        assert "overdraft_status" in cols
        assert "overdraft_status" in table["CustomSql"]["SqlQuery"]


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
        assert "INSERT INTO ar_parent_accounts" in out.read_text()

    def test_demo_seed_all_includes_both(self, tmp_path: Path):
        out = tmp_path / "seed.sql"
        runner = CliRunner()
        result = runner.invoke(
            main, ["demo", "seed", "--all", "-o", str(out)],
        )
        assert result.exit_code == 0, result.output
        content = out.read_text()
        assert "INSERT INTO pr_merchants" in content
        assert "INSERT INTO ar_parent_accounts" in content
