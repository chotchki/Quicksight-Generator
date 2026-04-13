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
        # 60 transfers × 2 legs each = 120 transactions
        assert len(ar_parsed["ar_transactions"]) == 120

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
        ):
            assert f"CREATE VIEW {view}" in schema_sql


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

    def test_seven_dataset_files(self, ar_output_dir):
        datasets = list((ar_output_dir / "datasets").glob("qs-gen-ar-*.json"))
        assert len(datasets) == 7

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
        self._assert_visual_count(ar_output_dir, SHEET_AR_TRANSFERS, 3)

    def test_transactions_visual_count(self, ar_output_dir):
        self._assert_visual_count(ar_output_dir, SHEET_AR_TRANSACTIONS, 4)

    def test_exceptions_visual_count(self, ar_output_dir):
        self._assert_visual_count(ar_output_dir, SHEET_AR_EXCEPTIONS, 7)

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


class TestFilterGroups:
    """Phase 3 has exactly one filter group: the shared date-range."""

    def test_single_filter_group(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fgs = analysis["Definition"]["FilterGroups"]
        assert len(fgs) == 1
        assert fgs[0]["FilterGroupId"] == "fg-ar-date-range"

    def test_date_range_scopes_four_tabs(self, ar_output_dir):
        analysis = _load(ar_output_dir, "account-recon-analysis.json")
        fg = analysis["Definition"]["FilterGroups"][0]
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
