"""Unit tests for demo data generation."""

import re
from datetime import date
from decimal import Decimal

import pytest

from quicksight_gen.account_recon.demo_data import (
    generate_demo_sql as generate_ar_sql,
)
from quicksight_gen.payment_recon.demo_data import (
    MERCHANTS,
    PR_SUBLEDGER_ACCOUNTS,
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


# ---------------------------------------------------------------------------
# PR unified transfer + posting tables
# ---------------------------------------------------------------------------

class TestPrUnifiedTables:
    """Phase B.5: PR transfer chain integrity and equivalence."""

    def _col(self, rows: list[str], idx: int) -> list[str]:
        return [
            [p.strip().strip("'") for p in row.split(",")][idx]
            for row in rows
        ]

    def test_transfer_types_present(self, parsed):
        types = set(self._col(parsed["transfer"], 2))
        assert types == {"sale", "settlement", "payment", "external_txn"}

    def test_one_transfer_per_legacy_row(self, parsed):
        """Every legacy PR row has a corresponding transfer."""
        sale_count = len(parsed["pr_sales"])
        stl_count = len(parsed["pr_settlements"])
        pay_count = len(parsed["pr_payments"])
        ext_count = len(parsed["pr_external_transactions"])
        xfer_count = len(parsed["transfer"])
        assert xfer_count == sale_count + stl_count + pay_count + ext_count

    def test_posting_fk_to_transfer(self, parsed):
        transfer_ids = set(self._col(parsed["transfer"], 0))
        posting_tids = set(self._col(parsed["posting"], 1))
        assert posting_tids.issubset(transfer_ids)

    def test_posting_fk_to_subledger(self, parsed):
        subledger_ids = set(self._col(parsed["ar_subledger_accounts"], 0))
        posting_accounts = set(self._col(parsed["posting"], 3))
        assert posting_accounts.issubset(subledger_ids)

    def test_chain_integrity_payment_to_ext(self, parsed):
        """Every payment transfer with a non-NULL parent links to an
        external_txn transfer."""
        xfer_type_by_id = {
            self._col([r], 0)[0]: self._col([r], 2)[0]
            for r in parsed["transfer"]
        }
        for row in parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            if parts[2] == "payment" and parts[1] != "NULL":
                assert xfer_type_by_id[parts[1]] == "external_txn"

    def test_chain_integrity_settlement_to_payment(self, parsed):
        """Every settlement transfer with a non-NULL parent links to a
        payment transfer."""
        xfer_type_by_id = {
            self._col([r], 0)[0]: self._col([r], 2)[0]
            for r in parsed["transfer"]
        }
        for row in parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            if parts[2] == "settlement" and parts[1] != "NULL":
                assert xfer_type_by_id[parts[1]] == "payment"

    def test_chain_integrity_sale_to_settlement(self, parsed):
        """Every sale transfer with a non-NULL parent links to a
        settlement transfer."""
        xfer_type_by_id = {
            self._col([r], 0)[0]: self._col([r], 2)[0]
            for r in parsed["transfer"]
        }
        for row in parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            if parts[2] == "sale" and parts[1] != "NULL":
                assert xfer_type_by_id[parts[1]] == "settlement"

    def test_non_failed_transfers_net_to_zero(self, parsed):
        """For each transfer with 2 postings, Σ signed_amount = 0
        when both postings are 'success'."""
        postings_by_xfer: dict[str, list[tuple[Decimal, str]]] = {}
        for row in parsed["posting"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            tid = parts[1]
            amount = Decimal(parts[4])
            status = parts[6]
            postings_by_xfer.setdefault(tid, []).append((amount, status))

        for tid, legs in postings_by_xfer.items():
            if len(legs) == 2:
                all_success = all(s == "success" for _, s in legs)
                if all_success:
                    net = sum(a for a, _ in legs)
                    assert net == 0, (
                        f"Transfer {tid} has net={net}, expected 0"
                    )

    def test_external_txn_has_single_posting(self, parsed):
        """External txn transfers have exactly 1 posting (external
        observation, no double-entry counter-party)."""
        ext_xfer_ids = {
            self._col([r], 0)[0]
            for r in parsed["transfer"]
            if self._col([r], 2)[0] == "external_txn"
        }
        postings_by_xfer: dict[str, int] = {}
        for row in parsed["posting"]:
            tid = self._col([row], 1)[0]
            postings_by_xfer[tid] = postings_by_xfer.get(tid, 0) + 1
        for eid in ext_xfer_ids:
            assert postings_by_xfer.get(eid) == 1, (
                f"External txn transfer {eid} should have 1 posting"
            )

    def test_sale_settlement_payment_have_two_postings(self, parsed):
        """Non-external transfers have exactly 2 postings."""
        non_ext_ids = {
            self._col([r], 0)[0]
            for r in parsed["transfer"]
            if self._col([r], 2)[0] != "external_txn"
        }
        postings_by_xfer: dict[str, int] = {}
        for row in parsed["posting"]:
            tid = self._col([row], 1)[0]
            postings_by_xfer[tid] = postings_by_xfer.get(tid, 0) + 1
        for nid in non_ext_ids:
            assert postings_by_xfer.get(nid) == 2, (
                f"Transfer {nid} should have 2 postings, "
                f"got {postings_by_xfer.get(nid)}"
            )

    def test_pr_subledger_accounts_inserted(self, parsed):
        """PR sub-ledger accounts must be present."""
        ids = set(self._col(parsed["ar_subledger_accounts"], 0))
        for sid, _, _, _ in PR_SUBLEDGER_ACCOUNTS:
            assert sid in ids, f"Missing PR sub-ledger account: {sid}"

    def test_unsettled_sales_have_no_parent(self, parsed):
        """Sales without a settlement_id get transfer.parent = NULL."""
        unsettled_sale_ids = set()
        for row in parsed["pr_sales"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            if parts[11] == "NULL":
                unsettled_sale_ids.add(parts[0])
        for row in parsed["transfer"]:
            parts = [p.strip().strip("'") for p in row.split(",")]
            if parts[2] == "sale":
                sale_id = parts[0].replace("pr-xfer-sale-", "")
                if sale_id in unsettled_sale_ids:
                    assert parts[1] == "NULL", (
                        f"Unsettled sale {sale_id} should have NULL parent"
                    )


# ---------------------------------------------------------------------------
# Cross-app integrity (B.7)
# ---------------------------------------------------------------------------

def _parse_inserts(sql: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for m in re.finditer(
        r"INSERT INTO (\w+) \([^)]+\) VALUES\n(.*?);",
        sql, re.DOTALL,
    ):
        table = m.group(1)
        body = m.group(2)
        rows = re.findall(r"\(([^)]+)\)", body)
        result.setdefault(table, []).extend(rows)
    return result


@pytest.fixture()
def combined_parsed() -> dict[str, list[str]]:
    """Parse both PR and AR seeds, merging shared tables."""
    pr_sql = generate_demo_sql(ANCHOR)
    ar_sql = generate_ar_sql(ANCHOR)
    combined = _parse_inserts(pr_sql)
    ar_parsed = _parse_inserts(ar_sql)
    for table, rows in ar_parsed.items():
        combined.setdefault(table, []).extend(rows)
    return combined


class TestCrossAppIntegrity:
    def _col(self, rows: list[str], idx: int) -> list[str]:
        return [
            [p.strip().strip("'") for p in row.split(",")][idx]
            for row in rows
        ]

    def test_transfer_types_cover_declared_enum(self, combined_parsed):
        """Every transfer_type value in data is in the schema CHECK enum."""
        declared = {
            "sale", "settlement", "payment", "external_txn",
            "ach", "wire", "internal", "cash",
            "funding_batch", "fee", "clearing_sweep",
        }
        actual = set(self._col(combined_parsed["transfer"], 2))
        assert actual.issubset(declared), (
            f"Undeclared transfer types: {actual - declared}"
        )
        assert len(actual) == len(declared), (
            f"Missing transfer types in data: {declared - actual}"
        )

    def test_all_posting_transfer_ids_exist(self, combined_parsed):
        """Every posting.transfer_id exists in transfer."""
        transfer_ids = set(self._col(combined_parsed["transfer"], 0))
        posting_tids = set(self._col(combined_parsed["posting"], 1))
        assert posting_tids.issubset(transfer_ids)

    def test_all_posting_subledger_ids_exist(self, combined_parsed):
        """Every posting.subledger_account_id (when set) exists in ar_subledger_accounts."""
        subledger_ids = set(
            self._col(combined_parsed["ar_subledger_accounts"], 0)
        )
        posting_accounts = set(
            self._col(combined_parsed["posting"], 3)
        )
        posting_accounts.discard("NULL")  # ledger-level postings
        assert posting_accounts.issubset(subledger_ids), (
            f"Unknown subledger accounts in postings: "
            f"{posting_accounts - subledger_ids}"
        )

    def test_no_transfer_id_collision(self, combined_parsed):
        """PR and AR transfer IDs must not collide (prefix guarantees)."""
        ids = self._col(combined_parsed["transfer"], 0)
        assert len(ids) == len(set(ids)), "Duplicate transfer IDs across apps"

    def test_no_posting_id_collision(self, combined_parsed):
        """PR and AR posting IDs must not collide."""
        ids = self._col(combined_parsed["posting"], 0)
        assert len(ids) == len(set(ids)), "Duplicate posting IDs across apps"


# ---------------------------------------------------------------------------
# Phase G shared base layer — transactions + daily_balances dual-write
# ---------------------------------------------------------------------------

import json as _json

CANONICAL_ACCOUNT_TYPES = {
    "gl_control", "dda", "merchant_dda",
    "external_counter", "concentration_master", "funds_pool",
}


def _last_quoted(row: str) -> str | None:
    # Returns the last single-quoted SQL literal (handles '' escape).
    m = re.search(r"'((?:[^']|'')*)'\s*$", row)
    return m.group(1).replace("''", "'") if m else None


class TestSharedBaseLayer:
    TXN_COLS = [
        "transaction_id", "transfer_id", "parent_transfer_id",
        "transfer_type", "origin", "account_id", "account_name",
        "control_account_id", "account_type", "is_internal",
        "signed_amount", "amount", "status", "posted_at",
        "balance_date", "external_system", "memo", "metadata",
    ]

    def _col_value(self, row: str, name: str) -> str:
        # Naive comma-split — safe for cols 0..16 (metadata is index 17
        # and contains JSON commas, so don't index it this way).
        idx = self.TXN_COLS.index(name)
        return [p.strip().strip("'") for p in row.split(",")][idx]

    def test_one_transactions_row_per_posting(self, combined_parsed):
        # Every posting (PR + AR) gets exactly one transactions row.
        assert (
            len(combined_parsed["transactions"])
            == len(combined_parsed["posting"])
        )

    def test_includes_pr_and_ar_transfer_types(self, combined_parsed):
        types = {
            self._col_value(r, "transfer_type")
            for r in combined_parsed["transactions"]
        }
        assert {"sale", "settlement", "payment", "external_txn"}.issubset(types)
        assert {"ach", "wire", "clearing_sweep"}.issubset(types)

    def test_account_type_values_are_canonical(self, combined_parsed):
        types = {
            self._col_value(r, "account_type")
            for r in combined_parsed["transactions"]
        }
        assert types.issubset(CANONICAL_ACCOUNT_TYPES), (
            f"Unknown account_type values: {types - CANONICAL_ACCOUNT_TYPES}"
        )

    def test_metadata_carries_source_provenance(self, combined_parsed):
        # Sample first 50 across both apps; every row must declare source.
        for row in combined_parsed["transactions"][:50]:
            raw = _last_quoted(row)
            assert raw is not None and raw.startswith("{"), (
                f"Metadata not JSON-quoted: {row[:120]}"
            )
            doc = _json.loads(raw)
            assert "source" in doc, f"Missing source in metadata: {doc}"

    def test_pr_sales_carry_merchant_account_id(self, combined_parsed):
        # G.3.5 Phase H prep: every PR sale row carries merchant_account_id.
        sale_rows = [
            r for r in combined_parsed["transactions"]
            if self._col_value(r, "transfer_type") == "sale"
        ]
        assert sale_rows, "Expected sale rows in shared transactions"
        for row in sale_rows[:30]:
            payload = _json.loads(_last_quoted(row))
            assert "merchant_account_id" in payload, (
                "Phase H prep: PR sale metadata must carry merchant_account_id"
            )

    def test_daily_balances_includes_pr_and_ar_accounts(self, combined_parsed):
        ids = {
            r.split(",")[0].strip().strip("'")
            for r in combined_parsed["daily_balances"]
        }
        # PR ledger row + per-merchant sub-ledgers
        assert "pr-merchant-ledger" in ids
        assert any(i.startswith("pr-sub-merch-") for i in ids)
        # AR ledger + DDA samples
        assert any(i.startswith("gl-") for i in ids)
        assert any(i.startswith("cust-") for i in ids)

    def test_ledger_rows_have_null_control(self, combined_parsed):
        # control_account_id NULL ⇒ structural ledger row; populated ⇒
        # sub-ledger row (per G.0.12 control_account_id IS NULL invariant).
        null_ctrl: set[str] = set()
        set_ctrl: set[str] = set()
        for r in combined_parsed["daily_balances"]:
            parts = [p.strip() for p in r.split(",")]
            account_id = parts[0].strip("'")
            control = parts[2]
            if control == "NULL":
                null_ctrl.add(account_id)
            else:
                set_ctrl.add(account_id)
        # No account_id is BOTH a ledger and sub-ledger.
        overlap = null_ctrl & set_ctrl
        assert not overlap, f"Account both ledger + sub-ledger row: {overlap}"
        # PR ledger is among the NULL-control set.
        assert "pr-merchant-ledger" in null_ctrl
        # No PR sub-ledger appears with NULL control.
        assert not any(
            i.startswith("pr-sub-") or i in {
                "pr-external-customer-pool", "pr-external-rail",
            }
            for i in null_ctrl
        )
