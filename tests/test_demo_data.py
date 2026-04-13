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
        assert len(parsed["pr_merchants"]) == 6

    def test_sales_count(self, parsed):
        count = len(parsed["pr_sales"])
        # 200 regular sales + ~15 refund rows
        assert 195 <= count <= 235, f"Expected ~215 sales+refunds, got {count}"

    def test_settlements_count(self, parsed):
        count = len(parsed["pr_settlements"])
        assert 25 <= count <= 50, f"Expected ~30-35 settlements, got {count}"

    def test_payments_count(self, parsed):
        count = len(parsed["pr_payments"])
        assert 20 <= count <= 45, f"Expected ~25-30 payments, got {count}"

    def test_external_transactions_count(self, parsed):
        count = len(parsed["pr_external_transactions"])
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
        merchant_ids = set(self._extract_col(parsed["pr_merchants"], 0))
        sale_mids = set(self._extract_col(parsed["pr_sales"], 1))
        assert sale_mids.issubset(merchant_ids)

    def test_sales_settlement_ids_exist(self, parsed):
        settlement_ids = set(self._extract_col(parsed["pr_settlements"], 0))
        # settlement_id is col 11 (sale_id, merchant_id, location_id, amount,
        # sale_type, payment_method, sale_timestamp, card_brand, card_last_four,
        # reference_id, metadata, settlement_id, taxes, tips,
        # discount_percentage, cashier)
        sale_stls = set(self._extract_col(parsed["pr_sales"], 11))
        non_null = {s for s in sale_stls if s != "NULL"}
        assert non_null.issubset(settlement_ids), (
            f"Unknown settlement_ids: {non_null - settlement_ids}"
        )

    def test_payments_settlement_ids_exist(self, parsed):
        settlement_ids = set(self._extract_col(parsed["pr_settlements"], 0))
        pay_stls = set(self._extract_col(parsed["pr_payments"], 1))
        assert pay_stls.issubset(settlement_ids)

    def test_payments_merchant_ids_exist(self, parsed):
        merchant_ids = set(self._extract_col(parsed["pr_merchants"], 0))
        pay_mids = set(self._extract_col(parsed["pr_payments"], 2))
        assert pay_mids.issubset(merchant_ids)

    def test_ext_txn_merchant_ids_exist(self, parsed):
        merchant_ids = set(self._extract_col(parsed["pr_merchants"], 0))
        # merchant_id is col 6 (transaction_id, external_system,
        # external_amount, record_count, transaction_date, status, merchant_id)
        ext_mids = set(self._extract_col(parsed["pr_external_transactions"], 6))
        assert ext_mids.issubset(merchant_ids)

    def test_payment_ext_txn_ids_exist(self, parsed):
        ext_ids = set(self._extract_col(parsed["pr_external_transactions"], 0))
        pay_ext = set(self._extract_col(parsed["pr_payments"], 8))
        non_null = {s for s in pay_ext if s != "NULL"}
        assert non_null.issubset(ext_ids)


# ---------------------------------------------------------------------------
# Scenario coverage
# ---------------------------------------------------------------------------

class TestScenarioCoverage:
    def test_unsettled_sales_exist(self, parsed):
        """At least 8 sales have NULL settlement_id."""
        # settlement_id is col 11 (shifted again after the payment_method column)
        stl_col = [
            p.strip().strip("'")
            for row in parsed["pr_sales"]
            for p in [row.split(",")[11]]
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

    def test_orphan_external_txns_exist(self, parsed):
        """Orphan ext txns — not referenced by any payment — power the
        Unmatched External Transactions exceptions table."""
        ext_ids = {
            row.split(",")[0].strip().strip("'")
            for row in parsed["pr_external_transactions"]
        }
        referenced = {
            row.split(",")[8].strip().strip("'")
            for row in parsed["pr_payments"]
        } - {"NULL"}
        orphans = ext_ids - referenced
        assert len(orphans) >= 8, (
            f"Need orphan ext txns for recon/exceptions visuals, got {len(orphans)}"
        )

    def test_unmatched_payments_exist(self, parsed):
        """Payments without an ext txn power the Show-Only-Unmatched toggle."""
        null_count = sum(
            1 for row in parsed["pr_payments"]
            if row.split(",")[8].strip() == "NULL"
        )
        assert null_count >= 2, (
            f"Need unmatched payments for Payments toggle, got {null_count}"
        )


# ---------------------------------------------------------------------------
# Refund scenarios (SPEC 2.1)
# ---------------------------------------------------------------------------

class TestRefunds:
    def test_refund_rows_exist(self, parsed):
        """At least a handful of refund rows are generated."""
        sale_types = self._sale_types(parsed)
        refund_count = sum(1 for t in sale_types if t == "refund")
        assert refund_count >= 10, f"Expected ~15 refunds, got {refund_count}"

    def test_refund_amounts_are_negative(self, parsed):
        """Every refund row carries a negative amount."""
        for row in parsed["pr_sales"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            amount = parts[3]
            sale_type = parts[4]
            if sale_type == "refund":
                assert amount.startswith("-"), (
                    f"Refund row has non-negative amount: {row!r}"
                )

    def test_sale_rows_are_non_negative(self, parsed):
        """Regular sale rows always have positive amounts."""
        for row in parsed["pr_sales"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            amount = parts[3]
            sale_type = parts[4]
            if sale_type == "sale":
                assert not amount.startswith("-"), (
                    f"Sale row has negative amount: {row!r}"
                )

    def test_refunds_flow_into_settlements(self, parsed):
        """Some refund rows must land inside a settlement so signed sums net."""
        settled_refunds = 0
        for row in parsed["pr_sales"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            sale_type = parts[4]
            settlement_id = parts[11]
            if sale_type == "refund" and settlement_id != "NULL":
                settled_refunds += 1
        assert settled_refunds >= 5, (
            f"Only {settled_refunds} refunds reached a settlement; "
            "signed-sum nets won't be exercised"
        )

    def _sale_types(self, parsed) -> list[str]:
        types: list[str] = []
        for row in parsed["pr_sales"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            types.append(parts[4])
        return types
