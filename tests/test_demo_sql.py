"""Integration tests for demo SQL output and CLI commands."""

import re
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.cli import main
from quicksight_gen.demo_data import generate_demo_sql


ANCHOR = date(2026, 4, 11)


# ---------------------------------------------------------------------------
# SQL structure validation
# ---------------------------------------------------------------------------

class TestSchemaSql:
    @pytest.fixture()
    def schema_sql(self) -> str:
        schema_path = Path(__file__).resolve().parent.parent / "demo" / "schema.sql"
        return schema_path.read_text()

    def test_creates_all_tables(self, schema_sql):
        for table in [
            "merchants",
            "external_transactions",
            "settlements",
            "sales",
            "payments",
        ]:
            assert f"CREATE TABLE {table}" in schema_sql

    def test_creates_all_views(self, schema_sql):
        assert "CREATE VIEW payment_recon_view" in schema_sql

    def test_drops_before_creates(self, schema_sql):
        # DROP statements appear before CREATE statements
        first_drop = schema_sql.index("DROP")
        first_create = schema_sql.index("CREATE TABLE")
        assert first_drop < first_create

    def test_creates_indexes(self, schema_sql):
        assert schema_sql.count("CREATE INDEX") >= 7


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
        assert len(inserts) == 5, f"Expected 5 INSERT blocks, got {len(inserts)}"
        for block in inserts:
            assert block.rstrip().endswith(";")

    def test_insert_tables_match_schema(self, seed_sql):
        tables = re.findall(r"INSERT INTO (\w+)", seed_sql)
        expected = {
            "merchants",
            "external_transactions",
            "settlements",
            "sales",
            "payments",
        }
        assert set(tables) == expected

    def test_fk_safe_order(self, seed_sql):
        """INSERT order must respect foreign key dependencies."""
        positions = {}
        for m in re.finditer(r"INSERT INTO (\w+)", seed_sql):
            table = m.group(1)
            if table not in positions:
                positions[table] = m.start()

        # FK order: merchants before ext_txns before
        # settlements before sales, payments
        assert positions["merchants"] < positions["external_transactions"]
        assert positions["external_transactions"] < positions["settlements"]
        assert positions["settlements"] < positions["sales"]
        assert positions["sales"] < positions["payments"]


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestDemoSchemaCli:
    def test_writes_schema_file(self, tmp_path):
        out = tmp_path / "schema.sql"
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "schema", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text()
        assert "CREATE TABLE merchants" in content


class TestDemoSeedCli:
    def test_writes_seed_file(self, tmp_path):
        out = tmp_path / "seed.sql"
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "seed", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text()
        assert "INSERT INTO merchants" in content
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
        result = runner.invoke(main, ["demo", "apply", "-c", str(config)])
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
             "--theme-preset", "sasquatch-bank"],
        )
        assert result.exit_code == 0, result.output

        import json

        theme = json.loads((out / "theme.json").read_text())
        assert theme["Name"] == "Sasquatch National Bank Theme"

        analysis = json.loads((out / "financial-analysis.json").read_text())
        assert "Sasquatch National Bank" in analysis["Name"]
