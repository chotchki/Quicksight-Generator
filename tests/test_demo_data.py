"""Unit tests for demo data generation."""

import re
from datetime import date

import pytest

from quicksight_gen.payment_recon.demo_data import (
    MERCHANTS,
    generate_demo_sql,
)

ANCHOR = date(2026, 4, 11)


@pytest.fixture()
def sql() -> str:
    return generate_demo_sql(ANCHOR)


@pytest.fixture()
def parsed(sql: str) -> dict[str, list[str]]:
    """Parse SQL into table -> list of value-row strings."""
    result: dict[str, list[str]] = {}
    for m in re.finditer(
        r"INSERT INTO (\w+) \([^)]+\) VALUES\n(.*?);",
        sql,
        re.DOTALL,
    ):
        table = m.group(1)
        body = m.group(2)
        rows = re.findall(r"\(([^)]+)\)", body)
        result[table] = rows
    return result


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_anchor_produces_identical_output(self):
        a = generate_demo_sql(ANCHOR)
        b = generate_demo_sql(ANCHOR)
        assert a == b

    def test_different_anchor_produces_different_dates(self):
        a = generate_demo_sql(date(2026, 1, 1))
        b = generate_demo_sql(date(2026, 6, 1))
        assert a != b


# ---------------------------------------------------------------------------
# Row counts
# ---------------------------------------------------------------------------

class TestRowCounts:
    def test_merchants(self, parsed):
        assert len(parsed["merchants"]) == 6

    def test_sales_count(self, parsed):
        count = len(parsed["sales"])
        assert 180 <= count <= 220, f"Expected ~200 sales, got {count}"

    def test_settlements_count(self, parsed):
        count = len(parsed["settlements"])
        assert 25 <= count <= 45, f"Expected ~30-35 settlements, got {count}"

    def test_payments_count(self, parsed):
        count = len(parsed["payments"])
        assert 20 <= count <= 40, f"Expected ~25-30 payments, got {count}"

    def test_external_transactions_count(self, parsed):
        count = len(parsed["external_transactions"])
        assert 10 <= count <= 35, f"Expected ~15-30 ext txns, got {count}"


# ---------------------------------------------------------------------------
# Merchant coverage
# ---------------------------------------------------------------------------

class TestMerchants:
    def test_all_six_present(self, sql):
        for mid, name, _, _ in MERCHANTS:
            assert mid in sql, f"Missing merchant {mid}"

    def test_all_names_present(self, sql):
        for _, name, _, _ in MERCHANTS:
            assert name.replace("'", "''") in sql

    def test_all_types_present(self, sql):
        for mtype in ("franchise", "independent", "cart"):
            assert mtype in sql


# ---------------------------------------------------------------------------
# Referential integrity
# ---------------------------------------------------------------------------

class TestReferentialIntegrity:
    def _extract_col(self, rows: list[str], col_idx: int) -> list[str]:
        """Extract the Nth comma-separated value from each row string."""
        vals = []
        for row in rows:
            parts = [p.strip().strip("'") for p in row.split(",")]
            vals.append(parts[col_idx])
        return vals

    def test_sales_merchant_ids_exist(self, parsed):
        merchant_ids = set(self._extract_col(parsed["merchants"], 0))
        sale_mids = set(self._extract_col(parsed["sales"], 1))
        assert sale_mids.issubset(merchant_ids)

    def test_sales_settlement_ids_exist(self, parsed):
        settlement_ids = set(self._extract_col(parsed["settlements"], 0))
        sale_stls = set(self._extract_col(parsed["sales"], 9))
        non_null = {s for s in sale_stls if s != "NULL"}
        assert non_null.issubset(settlement_ids), (
            f"Unknown settlement_ids: {non_null - settlement_ids}"
        )

    def test_payments_settlement_ids_exist(self, parsed):
        settlement_ids = set(self._extract_col(parsed["settlements"], 0))
        pay_stls = set(self._extract_col(parsed["payments"], 1))
        assert pay_stls.issubset(settlement_ids)

    def test_payments_merchant_ids_exist(self, parsed):
        merchant_ids = set(self._extract_col(parsed["merchants"], 0))
        pay_mids = set(self._extract_col(parsed["payments"], 2))
        assert pay_mids.issubset(merchant_ids)

    def test_ext_txn_merchant_ids_exist(self, parsed):
        merchant_ids = set(self._extract_col(parsed["merchants"], 0))
        # merchant_id is col 6 (transaction_id, external_system,
        # external_amount, record_count, transaction_date, status, merchant_id)
        ext_mids = set(self._extract_col(parsed["external_transactions"], 6))
        assert ext_mids.issubset(merchant_ids)

    def test_payment_ext_txn_ids_exist(self, parsed):
        ext_ids = set(self._extract_col(parsed["external_transactions"], 0))
        pay_ext = set(self._extract_col(parsed["payments"], 8))
        non_null = {s for s in pay_ext if s != "NULL"}
        assert non_null.issubset(ext_ids)


# ---------------------------------------------------------------------------
# Scenario coverage
# ---------------------------------------------------------------------------

class TestScenarioCoverage:
    def test_unsettled_sales_exist(self, parsed):
        """At least 8 sales have NULL settlement_id."""
        stl_col = [
            p.strip().strip("'")
            for row in parsed["sales"]
            for p in [row.split(",")[9]]
        ]
        null_count = sum(1 for v in stl_col if v.strip() == "NULL")
        assert null_count >= 8, f"Only {null_count} unsettled sales"

    def test_returned_payments_exist(self, sql):
        for reason in [
            "insufficient_funds",
            "bank_rejected",
            "disputed",
            "account_closed",
            "invalid_account",
        ]:
            assert reason in sql, f"Missing return reason: {reason}"

    def test_external_systems_present(self, sql):
        for system in ["BankSync", "PaymentHub", "ClearSettle"]:
            assert system in sql

    def test_settlement_statuses(self, sql):
        assert "'completed'" in sql
        assert "'pending'" in sql
        assert "'failed'" in sql

    def test_card_brands(self, sql):
        for brand in ["Visa", "Mastercard", "Amex", "Discover"]:
            assert brand in sql

    def test_metadata_promos(self, sql):
        assert "SQUATCH10" in sql
        assert "loyalty:" in sql

    def test_settlement_types(self, sql):
        for stype in ("daily", "weekly", "monthly"):
            assert stype in sql
