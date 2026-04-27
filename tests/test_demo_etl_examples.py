"""Tests for the ``quicksight-gen demo etl-example`` CLI command.

These tests guard the *exemplary* INSERT patterns the command emits —
distinct from ``test_etl_examples.py`` which guards the live demo seed
against the Schema_v6 contract.  The output here is documentation
disguised as SQL: customers crib from it when building their own ETL,
so the patterns have to stay consistent with Schema_v6 even though
they're never executed against the demo database.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.apps.account_recon.etl_examples import (
    generate_etl_examples_sql as generate_ar_examples,
)
from quicksight_gen.cli import main
from quicksight_gen.apps.payment_recon.etl_examples import (
    generate_etl_examples_sql as generate_pr_examples,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DOC = REPO_ROOT / "src" / "quicksight_gen" / "docs" / "Schema_v6.md"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pr_sql() -> str:
    return generate_pr_examples()


@pytest.fixture(scope="module")
def ar_sql() -> str:
    return generate_ar_examples()


@pytest.fixture(scope="module")
def schema_doc() -> str:
    return SCHEMA_DOC.read_text()


# ---------------------------------------------------------------------------
# 1. Output structure — both apps emit the expected pattern catalogue
# ---------------------------------------------------------------------------

class TestPaymentReconExamples:
    def test_emits_non_empty_sql(self, pr_sql):
        assert len(pr_sql) > 1000, "PR ETL examples too short to be real"

    def test_emits_all_six_pr_patterns(self, pr_sql):
        for header in [
            "Pattern 1: PR sale",
            "Pattern 2: PR settlement",
            "Pattern 3: PR payment",
            "Pattern 4a: External transaction — one-to-one match",
            "Pattern 4b: External transaction — batched (one-to-many)",
            "Pattern 5: Returned payment",
        ]:
            assert header in pr_sql, f"PR examples missing: {header!r}"

    def test_every_pattern_has_a_why_comment(self, pr_sql):
        # Every pattern block should explain WHY before the INSERT.
        sections = re.split(r"-- Pattern \w+:", pr_sql)
        for i, section in enumerate(sections[1:], start=1):
            assert "-- WHY:" in section, (
                f"PR pattern #{i} has no -- WHY: comment explaining purpose"
            )

    def test_every_pattern_has_an_executable_statement(self, pr_sql):
        # Each section emits an INSERT or UPDATE.
        sections = re.split(r"-- Pattern \w+:", pr_sql)
        for i, section in enumerate(sections[1:], start=1):
            has_stmt = "INSERT INTO" in section or "UPDATE " in section
            assert has_stmt, (
                f"PR pattern #{i} has no INSERT or UPDATE statement"
            )


class TestAccountReconExamples:
    def test_emits_non_empty_sql(self, ar_sql):
        assert len(ar_sql) > 1000, "AR ETL examples too short to be real"

    def test_emits_all_five_ar_patterns(self, ar_sql):
        for header in [
            "Pattern 1: Customer DDA internal transfer",
            "Pattern 2: Force-posted ACH from the Fed",
            "Pattern 3: ZBA / cash-concentration sweep",
            "Pattern 4: Per-ledger limit configuration",
            "Pattern 5: GL drift recompute",
        ]:
            assert header in ar_sql, f"AR examples missing: {header!r}"

    def test_force_posted_pattern_uses_correct_origin(self, ar_sql):
        # Pattern 2 is the canonical force-post example — it MUST use the
        # external_force_posted origin or the doc-vs-example contract is broken.
        section = ar_sql.split("Pattern 2:")[1].split("Pattern 3:")[0]
        assert "'external_force_posted'" in section
        assert "'fed_statement'" in section  # source provenance

    def test_internal_transfer_legs_net_to_zero(self, ar_sql):
        # The two-leg internal transfer should sum to zero — extract the
        # signed_amount values from Pattern 1 and verify.
        section = ar_sql.split("Pattern 1:")[1].split("Pattern 2:")[0]
        # Find decimal literals adjacent to "-- positive = debit" / "-- negative = credit".
        # Simpler: pull signed_amounts from VALUES tuples.  Each VALUES has
        # signed_amount as a positional float.
        amounts = re.findall(r"^\s+(-?\d+\.\d+),\s+-- (?:positive|negative)", section, re.MULTILINE)
        assert len(amounts) == 2, f"Expected 2 signed_amounts in Pattern 1, got {amounts}"
        total = sum(float(a) for a in amounts)
        assert total == 0.0, f"Pattern 1 legs do not net to zero: {amounts} sum to {total}"

    def test_sweep_credits_concentration_master(self, ar_sql):
        # Pattern 3's credit leg targets gl-1850 with account_type = concentration_master.
        section = ar_sql.split("Pattern 3:")[1].split("Pattern 4:")[0]
        assert "'gl-1850'" in section
        assert "'concentration_master'" in section


# ---------------------------------------------------------------------------
# 2. Schema contract — every column referenced exists in the doc
# ---------------------------------------------------------------------------

class TestSchemaContractAlignment:
    # M.2d.7: test_every_inserted_column_is_documented +
    # test_metadata_keys_referenced_in_examples_are_documented removed
    # — both parsed Schema_v3 markdown structures the v6 rewrite
    # eliminated. The "seed values trace back to a declared spec"
    # intent moved to the M.2d.8 matrix in
    # tests/test_l2_seed_contract.py: parameterized over multiple L2
    # YAMLs, asserts contract against the v6 column lists +
    # Rail.metadata_keys.

    def test_no_forbidden_postgres_only_syntax(self, pr_sql, ar_sql):
        # Mirror the Forbidden SQL Patterns table from Schema_v6 — the
        # examples are user-facing reference material, so they must not
        # demonstrate any pattern the doc forbids elsewhere.
        combined = pr_sql + "\n" + ar_sql
        scrubbed = re.sub(r"--[^\n]*", "", combined)  # drop comments
        forbidden = [
            (r"\bJSONB\b", "JSONB type"),
            (r"->>", "metadata->>'key'"),
            (r"@>", "@> JSON containment"),
            (r"\?\s*'", "? key existence"),
            (r"\bGIN\b", "GIN index"),
        ]
        for pattern, description in forbidden:
            match = re.search(pattern, scrubbed)
            assert match is None, (
                f"Examples use forbidden pattern: {description} at "
                f"...{scrubbed[max(0, match.start()-30):match.end()+30]}..."
            )


# ---------------------------------------------------------------------------
# 3. CLI surface — `quicksight-gen demo etl-example` runs and emits SQL
# ---------------------------------------------------------------------------

class TestCliCommand:
    def test_help_lists_etl_example_subcommand(self):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--help"])
        assert result.exit_code == 0
        assert "etl-example" in result.output

    def test_all_apps_writes_combined_output(self, tmp_path):
        out = tmp_path / "examples.sql"
        runner = CliRunner()
        result = runner.invoke(
            main, ["demo", "etl-example", "--all", "-o", str(out)]
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert out.exists()
        body = out.read_text()
        # Both app headers should appear.
        assert "Payment Reconciliation — exemplary INSERT patterns" in body
        assert "Account Reconciliation — exemplary INSERT patterns" in body

    def test_payment_recon_only(self, tmp_path):
        out = tmp_path / "pr.sql"
        runner = CliRunner()
        result = runner.invoke(
            main, ["demo", "etl-example", "payment-recon", "-o", str(out)]
        )
        assert result.exit_code == 0
        body = out.read_text()
        assert "Payment Reconciliation" in body
        assert "Account Reconciliation" not in body

    def test_account_recon_only(self, tmp_path):
        out = tmp_path / "ar.sql"
        runner = CliRunner()
        result = runner.invoke(
            main, ["demo", "etl-example", "account-recon", "-o", str(out)]
        )
        assert result.exit_code == 0
        body = out.read_text()
        assert "Account Reconciliation" in body
        assert "Payment Reconciliation" not in body

    def test_neither_app_nor_all_errors(self):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "etl-example"])
        # _resolve_app raises UsageError → exit_code 2.
        assert result.exit_code != 0
