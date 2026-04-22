"""Integration tests for demo SQL output and CLI commands."""

import re
from datetime import date

import pytest
from click.testing import CliRunner

from quicksight_gen.cli import main
from quicksight_gen.apps.payment_recon.demo_data import generate_demo_sql


ANCHOR = date(2026, 4, 11)


# ---------------------------------------------------------------------------
# SQL structure validation
# ---------------------------------------------------------------------------

class TestSchemaSql:
    @pytest.fixture()
    def schema_sql(self) -> str:
        from quicksight_gen.schema import generate_schema_sql

        return generate_schema_sql()

    def test_creates_all_tables(self, schema_sql):
        for table in [
            "transactions",
            "daily_balances",
            "ar_ledger_accounts",
            "ar_subledger_accounts",
            "ar_ledger_transfer_limits",
        ]:
            assert f"CREATE TABLE {table}" in schema_sql

    def test_legacy_tables_dropped_not_created(self, schema_sql):
        # v3.0.0 drop: per-app PR tables and the AR-only transfer/posting
        # tables are now dead.  Their DROP IF EXISTS stays for upgrade
        # safety, but the CREATE TABLE must not come back.
        for table in [
            "pr_merchants", "pr_external_transactions", "pr_settlements",
            "pr_sales", "pr_payments",
            "transfer", "posting",
            "ar_ledger_daily_balances", "ar_subledger_daily_balances",
        ]:
            assert f"CREATE TABLE {table}" not in schema_sql, (
                f"{table} was dropped in v3.0.0 — should not be re-created"
            )
            assert f"DROP TABLE IF EXISTS {table}" in schema_sql, (
                f"{table} drop must remain for upgrade safety"
            )

    def test_drops_before_creates(self, schema_sql):
        # DROP statements appear before CREATE statements
        first_drop = schema_sql.index("DROP")
        first_create = schema_sql.index("CREATE TABLE")
        assert first_drop < first_create

    def test_creates_indexes(self, schema_sql):
        assert schema_sql.count("CREATE INDEX") >= 7

    def test_shared_base_layer_uses_portable_json(self, schema_sql):
        # Per Phase G portability constraint: TEXT + IS JSON, no JSONB.
        # Guards against silent reintroduction of Postgres-only features.
        for table in ["transactions", "daily_balances"]:
            block_start = schema_sql.index(f"CREATE TABLE {table}")
            block_end = schema_sql.index(");", block_start)
            block = schema_sql[block_start:block_end]
            assert "metadata            TEXT" in block, (
                f"{table} should declare metadata as TEXT"
            )
            assert "JSONB" not in block, (
                f"{table} must not use JSONB (portability constraint)"
            )
            assert "metadata IS JSON" in block, (
                f"{table} should constrain metadata with IS JSON"
            )


class TestSeedSql:
    @pytest.fixture()
    def seed_sql(self) -> str:
        return generate_demo_sql(ANCHOR)

    def test_no_unclosed_quotes(self, seed_sql):
        # Every line with a single quote should have an even count
        # (accounting for escaped '' pairs)
        collapsed = seed_sql.replace("''", "")
        for i, line in enumerate(collapsed.split("\n"), 1):
            count = line.count("'")
            assert count % 2 == 0, (
                f"Line {i} has {count} unescaped single quotes: {line[:80]}"
            )

    def test_every_insert_ends_with_semicolon(self, seed_sql):
        inserts = re.findall(r"(INSERT INTO \w+.*?;)", seed_sql, re.DOTALL)
        assert len(inserts) == 4, f"Expected 4 INSERT blocks, got {len(inserts)}"
        for block in inserts:
            assert block.rstrip().endswith(";")

    def test_insert_tables_match_schema(self, seed_sql):
        tables = re.findall(r"INSERT INTO (\w+)", seed_sql)
        expected = {
            "ar_ledger_accounts",
            "ar_subledger_accounts",
            "transactions",
            "daily_balances",
        }
        assert set(tables) == expected

    def test_fk_safe_order(self, seed_sql):
        """INSERT order must respect foreign key dependencies."""
        positions = {}
        for m in re.finditer(r"INSERT INTO (\w+)", seed_sql):
            table = m.group(1)
            if table not in positions:
                positions[table] = m.start()

        assert positions["ar_ledger_accounts"] < positions["ar_subledger_accounts"]
        # transactions / daily_balances reference the account dimension tables.
        assert positions["ar_subledger_accounts"] < positions["transactions"]
        assert positions["transactions"] < positions["daily_balances"]


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestDemoSchemaCli:
    def test_writes_schema_file(self, tmp_path):
        out = tmp_path / "schema.sql"
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "schema", "payment-recon", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text()
        assert "CREATE TABLE transactions" in content


class TestDemoSeedCli:
    def test_writes_seed_file(self, tmp_path):
        out = tmp_path / "seed.sql"
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "seed", "payment-recon", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text()
        assert "INSERT INTO transactions" in content
        assert "Bigfoot Brews" in content


class TestDemoApplyCli:
    def test_fails_without_database_url(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "aws_account_id: '111122223333'\n"
            "aws_region: us-west-2\n"
            "datasource_arn: arn:aws:quicksight:us-west-2:111122223333:datasource/ds\n"
        )
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "apply", "payment-recon", "-c", str(config)])
        assert result.exit_code != 0
        assert "demo_database_url" in result.output


class TestGenerateThemePresetCli:
    def test_theme_preset_flag(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "aws_account_id: '111122223333'\n"
            "aws_region: us-west-2\n"
            "datasource_arn: arn:aws:quicksight:us-west-2:111122223333:datasource/ds\n"
        )
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["generate", "-c", str(config), "-o", str(out),
             "--theme-preset", "sasquatch-bank",
             "payment-recon"],
        )
        assert result.exit_code == 0, result.output

        import json

        theme = json.loads((out / "theme.json").read_text())
        assert theme["Name"] == "Sasquatch National Bank Theme"

        analysis = json.loads((out / "payment-recon-analysis.json").read_text())
        assert analysis["Name"] == "Demo — Payment Reconciliation"
