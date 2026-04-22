"""Unit tests for demo data generation.

After Phase G the only seed tables are ``transactions``, ``daily_balances``,
``ar_ledger_accounts``, ``ar_subledger_accounts`` and (AR-only)
``ar_ledger_transfer_limits``.  All PR-domain assertions read PR rows out
of ``transactions`` (scoped under ``control_account_id='pr-merchant-ledger'``)
and recover legacy fields from each row's JSON metadata.
"""

import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from quicksight_gen.apps.account_recon.demo_data import (
    generate_demo_sql as generate_ar_sql,
)
from quicksight_gen.apps.investigation.demo_data import (
    INV_LEDGER_ACCOUNTS,
    INV_SUBLEDGER_ACCOUNTS,
    generate_demo_sql as generate_inv_sql,
)
from quicksight_gen.apps.payment_recon.demo_data import (
    MERCHANTS,
    PR_SUBLEDGER_ACCOUNTS,
    generate_demo_sql,
)

ANCHOR = date(2026, 4, 11)


# ---------------------------------------------------------------------------
# Parsing helpers (shared base layer)
# ---------------------------------------------------------------------------

TXN_COLS = [
    "transaction_id", "transfer_id", "parent_transfer_id",
    "transfer_type", "origin", "account_id", "account_name",
    "control_account_id", "account_type", "is_internal",
    "signed_amount", "amount", "status", "posted_at",
    "expected_complete_at", "balance_date", "external_system",
    "memo", "metadata",
]
_COL_IDX = {c: i for i, c in enumerate(TXN_COLS)}


def _row_parts(row: str) -> list[str]:
    """Naive comma-split of a VALUES row.  Safe for cols 0..16; metadata
    (col 17) carries JSON and must be extracted with :func:`_last_quoted`."""
    return [p.strip().strip("'") for p in row.split(",")]


def _val(row: str, col: str) -> str:
    return _row_parts(row)[_COL_IDX[col]]


def _last_quoted(row: str) -> str | None:
    m = re.search(r"'((?:[^']|'')*)'\s*$", row)
    return m.group(1).replace("''", "'") if m else None


def _metadata(row: str) -> dict:
    raw = _last_quoted(row)
    return json.loads(raw) if raw else {}


def _parse_inserts(sql: str) -> dict[str, list[str]]:
    """Parse SQL into table -> list of value-row strings (parens-balanced)."""
    result: dict[str, list[str]] = {}
    for m in re.finditer(
        r"INSERT INTO (\w+) \([^)]+\) VALUES\n(.*?);",
        sql, re.DOTALL,
    ):
        table = m.group(1)
        body = m.group(2)
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
        result.setdefault(table, []).extend(rows)
    return result


def _pr_rows(parsed: dict[str, list[str]]) -> list[str]:
    """PR transaction rows: those scoped under the PR ledger."""
    return [
        r for r in parsed["transactions"]
        if _val(r, "control_account_id") == "pr-merchant-ledger"
    ]


def _by_type(rows: list[str], ttype: str) -> list[str]:
    return [r for r in rows if _val(r, "transfer_type") == ttype]


def _distinct_transfers(rows: list[str]) -> dict[str, str]:
    """transfer_id → first posting row encountered (used for per-transfer
    metadata since metadata is identical across a transfer's postings)."""
    out: dict[str, str] = {}
    for r in rows:
        xid = _val(r, "transfer_id")
        if xid not in out:
            out[xid] = r
    return out


@pytest.fixture()
def sql() -> str:
    return generate_demo_sql(ANCHOR)


@pytest.fixture()
def parsed(sql: str) -> dict[str, list[str]]:
    return _parse_inserts(sql)


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

    def test_seed_output_hash_is_locked(self, sql):
        """Pinned hash so any silent drift in the PR generator is caught.

        When intentionally regenerating (e.g. new metadata key, additional
        scenario rows), update the hash here in the same commit.
        """
        import hashlib
        digest = hashlib.sha256(sql.encode()).hexdigest()
        assert digest == (
            "7e5b4123aee9f7830647c88159329b015515a2a1f28d7d4f626f6d27cfd6be18"
        ), f"PR seed drifted; new hash: {digest}"


# ---------------------------------------------------------------------------
# Row counts (per transfer_type, derived from transactions)
# ---------------------------------------------------------------------------

class TestRowCounts:
    def test_merchants(self, parsed):
        # PR merchants are now sub-ledger accounts under pr-merchant-ledger.
        merchant_ids = {
            _val(r, "account_id") for r in _pr_rows(parsed)
            if _val(r, "account_type") == "merchant_dda"
        }
        assert len(merchant_ids) == 6

    def test_sales_count(self, parsed):
        count = len(_distinct_transfers(_by_type(_pr_rows(parsed), "sale")))
        # 200 regular sales + ~15 refund rows
        assert 195 <= count <= 235, f"Expected ~215 sales+refunds, got {count}"

    def test_settlements_count(self, parsed):
        count = len(_distinct_transfers(_by_type(_pr_rows(parsed), "settlement")))
        assert 25 <= count <= 50, f"Expected ~30-35 settlements, got {count}"

    def test_payments_count(self, parsed):
        count = len(_distinct_transfers(_by_type(_pr_rows(parsed), "payment")))
        assert 20 <= count <= 45, f"Expected ~25-30 payments, got {count}"

    def test_external_transactions_count(self, parsed):
        count = len(_distinct_transfers(_by_type(_pr_rows(parsed), "external_txn")))
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
        # merchant_type is now carried in sale-row metadata.
        for mtype in ("franchise", "independent", "cart"):
            assert mtype in sql


# ---------------------------------------------------------------------------
# Referential integrity (FK relationships across transfer_type, via metadata)
# ---------------------------------------------------------------------------

class TestReferentialIntegrity:
    def test_sales_reference_known_merchants(self, parsed):
        merchant_ids = {m[0] for m in MERCHANTS}
        for row in _by_type(_pr_rows(parsed), "sale"):
            meta = _metadata(row)
            assert meta.get("merchant_id") in merchant_ids

    def test_sale_settlement_ids_exist(self, parsed):
        settlement_ids = {
            _metadata(r)["settlement_id"]
            for r in _distinct_transfers(_by_type(_pr_rows(parsed), "settlement")).values()
        }
        for row in _distinct_transfers(_by_type(_pr_rows(parsed), "sale")).values():
            sid = _metadata(row).get("settlement_id")
            if sid:
                assert sid in settlement_ids, f"Unknown settlement_id: {sid}"

    def test_payment_settlement_ids_exist(self, parsed):
        settlement_ids = {
            _metadata(r)["settlement_id"]
            for r in _distinct_transfers(_by_type(_pr_rows(parsed), "settlement")).values()
        }
        for row in _distinct_transfers(_by_type(_pr_rows(parsed), "payment")).values():
            sid = _metadata(row).get("settlement_id")
            assert sid in settlement_ids, f"Payment {sid!r} has unknown settlement"

    def test_payment_merchant_ids_exist(self, parsed):
        merchant_ids = {m[0] for m in MERCHANTS}
        for row in _distinct_transfers(_by_type(_pr_rows(parsed), "payment")).values():
            assert _metadata(row)["merchant_id"] in merchant_ids

    def test_ext_txn_merchant_ids_exist(self, parsed):
        merchant_ids = {m[0] for m in MERCHANTS}
        for row in _distinct_transfers(_by_type(_pr_rows(parsed), "external_txn")).values():
            assert _metadata(row)["merchant_id"] in merchant_ids

    def test_payment_ext_txn_ids_exist(self, parsed):
        ext_ids = {
            _metadata(r)["external_transaction_id"]
            for r in _distinct_transfers(_by_type(_pr_rows(parsed), "external_txn")).values()
        }
        for row in _distinct_transfers(_by_type(_pr_rows(parsed), "payment")).values():
            ext_id = _metadata(row).get("external_transaction_id")
            if ext_id:
                assert ext_id in ext_ids


# ---------------------------------------------------------------------------
# Scenario coverage (each visual must have non-empty data)
# ---------------------------------------------------------------------------

class TestScenarioCoverage:
    def test_unsettled_sales_exist(self, parsed):
        """Sales without a settlement_id power Show-Only-Unsettled."""
        unsettled = [
            r for r in _distinct_transfers(_by_type(_pr_rows(parsed), "sale")).values()
            if not _metadata(r).get("settlement_id")
        ]
        assert len(unsettled) >= 8, f"Only {len(unsettled)} unsettled sales"

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
        # settlement_status carried in metadata as JSON string literal
        assert '"settlement_status":"completed"' in sql
        assert '"settlement_status":"pending"' in sql
        assert '"settlement_status":"failed"' in sql

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
            _metadata(r)["external_transaction_id"]
            for r in _distinct_transfers(_by_type(_pr_rows(parsed), "external_txn")).values()
        }
        referenced = {
            _metadata(r).get("external_transaction_id")
            for r in _distinct_transfers(_by_type(_pr_rows(parsed), "payment")).values()
        } - {None}
        orphans = ext_ids - referenced
        assert len(orphans) >= 8, (
            f"Need orphan ext txns for recon/exceptions visuals, got {len(orphans)}"
        )

    def test_unmatched_payments_exist(self, parsed):
        """Payments without an ext txn power the Show-Only-Unmatched toggle."""
        unmatched = [
            r for r in _distinct_transfers(_by_type(_pr_rows(parsed), "payment")).values()
            if not _metadata(r).get("external_transaction_id")
        ]
        assert len(unmatched) >= 2, (
            f"Need unmatched payments for Payments toggle, got {len(unmatched)}"
        )


# ---------------------------------------------------------------------------
# Lateness column population (K.3.1)
# ---------------------------------------------------------------------------

class TestExpectedCompleteAt:
    """Per-rail `expected_complete_at` population on PR transactions.

    The column is optional — most rows are NULL and downstream views fall
    back to `posted_at + INTERVAL '1 day'` via COALESCE.  This suite
    enforces the rail-specific values the demo plants so the data-driven
    `is_late` predicate has a realistic mix to fire against.
    """

    def test_card_payments_populated_t_plus_3(self, parsed):
        card_payment_legs = [
            r for r in _by_type(_pr_rows(parsed), "payment")
            if _metadata(r).get("payment_method") == "card"
        ]
        assert card_payment_legs, (
            "No card payments in demo seed — generator regression?"
        )
        for r in card_payment_legs:
            posted = datetime.fromisoformat(_val(r, "posted_at"))
            expected = _val(r, "expected_complete_at")
            assert expected != "NULL", (
                f"Card payment leg missing expected_complete_at: {r[:80]}"
            )
            parsed_expected = datetime.fromisoformat(expected)
            assert parsed_expected == posted + timedelta(days=3), (
                f"Card payment expected_complete_at != posted + T+3 "
                f"({parsed_expected} vs {posted + timedelta(days=3)})"
            )

    def test_external_txns_populated_same_hour(self, parsed):
        ext_legs = _by_type(_pr_rows(parsed), "external_txn")
        assert ext_legs, "No external_txn rows — generator regression?"
        for r in ext_legs:
            posted = datetime.fromisoformat(_val(r, "posted_at"))
            expected = _val(r, "expected_complete_at")
            assert expected != "NULL", (
                f"external_txn leg missing expected_complete_at: {r[:80]}"
            )
            parsed_expected = datetime.fromisoformat(expected)
            assert parsed_expected == posted + timedelta(hours=1), (
                f"external_txn expected_complete_at != posted + 1h "
                f"({parsed_expected} vs {posted + timedelta(hours=1)})"
            )

    def test_sales_left_null(self, parsed):
        for r in _by_type(_pr_rows(parsed), "sale"):
            assert _val(r, "expected_complete_at") == "NULL", (
                f"sale leg should leave expected_complete_at NULL: {r[:80]}"
            )

    def test_settlements_left_null(self, parsed):
        for r in _by_type(_pr_rows(parsed), "settlement"):
            assert _val(r, "expected_complete_at") == "NULL", (
                f"settlement leg should leave expected_complete_at NULL: {r[:80]}"
            )

    def test_non_card_payments_left_null(self, parsed):
        non_card = [
            r for r in _by_type(_pr_rows(parsed), "payment")
            if _metadata(r).get("payment_method") != "card"
        ]
        for r in non_card:
            assert _val(r, "expected_complete_at") == "NULL", (
                f"non-card payment should leave expected_complete_at NULL: "
                f"method={_metadata(r).get('payment_method')!r}"
            )


# ---------------------------------------------------------------------------
# Refund scenarios (SPEC 2.1)
# ---------------------------------------------------------------------------

class TestRefunds:
    def _sale_transfers(self, parsed) -> list[str]:
        return list(_distinct_transfers(_by_type(_pr_rows(parsed), "sale")).values())

    def test_refund_rows_exist(self, parsed):
        refund_count = sum(
            1 for r in self._sale_transfers(parsed)
            if _metadata(r).get("sale_type") == "refund"
        )
        assert refund_count >= 10, f"Expected ~15 refunds, got {refund_count}"

    def test_refund_amounts_are_negative(self, parsed):
        """Under the canonical sign convention, signed_amount on the
        merchant_dda leg IS the customer-facing amount — negative for
        every refund, matching the build_sales_dataset projection."""
        for r in _by_type(_pr_rows(parsed), "sale"):
            meta = _metadata(r)
            if meta.get("sale_type") != "refund":
                continue
            if _val(r, "account_type") != "merchant_dda":
                continue
            amount = Decimal(_val(r, "signed_amount"))
            assert amount < 0, f"Refund customer-facing amount not negative: {amount}"

    def test_sale_rows_are_non_negative(self, parsed):
        """Customer-facing amount is positive for every regular sale."""
        for r in _by_type(_pr_rows(parsed), "sale"):
            meta = _metadata(r)
            if meta.get("sale_type") != "sale":
                continue
            if _val(r, "account_type") != "merchant_dda":
                continue
            amount = Decimal(_val(r, "signed_amount"))
            assert amount > 0, f"Sale customer-facing amount not positive: {amount}"

    def test_refunds_flow_into_settlements(self, parsed):
        """Some refunds must land inside a settlement so signed sums net."""
        settled_refunds = sum(
            1 for r in self._sale_transfers(parsed)
            if _metadata(r).get("sale_type") == "refund"
            and _metadata(r).get("settlement_id")
        )
        assert settled_refunds >= 5, (
            f"Only {settled_refunds} refunds reached a settlement; "
            "signed-sum nets won't be exercised"
        )


# ---------------------------------------------------------------------------
# PR transfer-chain integrity (verified directly on the unified table)
# ---------------------------------------------------------------------------

class TestPrChainIntegrity:
    def _ttype_by_xid(self, parsed) -> dict[str, str]:
        return {
            _val(r, "transfer_id"): _val(r, "transfer_type")
            for r in _pr_rows(parsed)
        }

    def test_transfer_types_present(self, parsed):
        types = {_val(r, "transfer_type") for r in _pr_rows(parsed)}
        assert types == {"sale", "settlement", "payment", "external_txn"}

    def test_chain_payment_to_ext(self, parsed):
        ttype_by_xid = self._ttype_by_xid(parsed)
        for r in _by_type(_pr_rows(parsed), "payment"):
            parent = _val(r, "parent_transfer_id")
            if parent != "NULL":
                assert ttype_by_xid[parent] == "external_txn"

    def test_chain_settlement_to_payment(self, parsed):
        ttype_by_xid = self._ttype_by_xid(parsed)
        for r in _by_type(_pr_rows(parsed), "settlement"):
            parent = _val(r, "parent_transfer_id")
            if parent != "NULL":
                assert ttype_by_xid[parent] == "payment"

    def test_chain_sale_to_settlement(self, parsed):
        ttype_by_xid = self._ttype_by_xid(parsed)
        for r in _by_type(_pr_rows(parsed), "sale"):
            parent = _val(r, "parent_transfer_id")
            if parent != "NULL":
                assert ttype_by_xid[parent] == "settlement"

    def test_non_failed_transfers_net_to_zero(self, parsed):
        """For each PR transfer with two postings whose statuses are all
        'success', Σ signed_amount = 0."""
        legs_by_xfer: dict[str, list[tuple[Decimal, str]]] = {}
        for r in _pr_rows(parsed):
            xid = _val(r, "transfer_id")
            amount = Decimal(_val(r, "signed_amount"))
            status = _val(r, "status")
            legs_by_xfer.setdefault(xid, []).append((amount, status))
        for xid, legs in legs_by_xfer.items():
            if len(legs) == 2 and all(s == "success" for _, s in legs):
                net = sum(a for a, _ in legs)
                assert net == 0, f"Transfer {xid} has net={net}, expected 0"

    def test_external_txn_has_single_posting(self, parsed):
        """external_txn transfers have exactly 1 posting."""
        legs_by_xfer: dict[str, int] = {}
        for r in _by_type(_pr_rows(parsed), "external_txn"):
            xid = _val(r, "transfer_id")
            legs_by_xfer[xid] = legs_by_xfer.get(xid, 0) + 1
        for xid, n in legs_by_xfer.items():
            assert n == 1, f"External txn {xid} should have 1 posting, got {n}"

    def test_sale_settlement_payment_have_two_postings(self, parsed):
        """Non-external PR transfers have exactly 2 postings."""
        legs_by_xfer: dict[str, int] = {}
        for r in _pr_rows(parsed):
            if _val(r, "transfer_type") == "external_txn":
                continue
            xid = _val(r, "transfer_id")
            legs_by_xfer[xid] = legs_by_xfer.get(xid, 0) + 1
        for xid, n in legs_by_xfer.items():
            assert n == 2, f"Transfer {xid} should have 2 postings, got {n}"

    def test_pr_subledger_accounts_inserted(self, parsed):
        """PR sub-ledger accounts must be present in ar_subledger_accounts."""
        ids = {
            _row_parts(r)[0] for r in parsed["ar_subledger_accounts"]
        }
        for sid, _, _, _ in PR_SUBLEDGER_ACCOUNTS:
            assert sid in ids, f"Missing PR sub-ledger account: {sid}"

    def test_unsettled_sales_have_no_parent(self, parsed):
        """Sales without a settlement_id get parent_transfer_id = NULL."""
        for r in _distinct_transfers(_by_type(_pr_rows(parsed), "sale")).values():
            meta = _metadata(r)
            if not meta.get("settlement_id"):
                assert _val(r, "parent_transfer_id") == "NULL", (
                    f"Unsettled sale {meta.get('sale_id')} has non-NULL parent"
                )


# ---------------------------------------------------------------------------
# Cross-app integrity
# ---------------------------------------------------------------------------

@pytest.fixture()
def combined_parsed() -> dict[str, list[str]]:
    """Parse PR + AR + investigation seeds into one merged dict."""
    combined = _parse_inserts(generate_demo_sql(ANCHOR))
    for src in (generate_ar_sql(ANCHOR), generate_inv_sql(ANCHOR)):
        for table, rows in _parse_inserts(src).items():
            combined.setdefault(table, []).extend(rows)
    return combined


def _xid_app(xid: str) -> str:
    """Classify a transfer_id by its app prefix."""
    if xid.startswith("pr-"):
        return "pr"
    if xid.startswith("inv-"):
        return "inv"
    return "ar"


class TestCrossAppIntegrity:
    def test_transfer_types_cover_declared_enum(self, combined_parsed):
        """Every transfer_type value in the unified data is in the schema
        CHECK enum, and the data covers every declared type."""
        declared = {
            "sale", "settlement", "payment", "external_txn",
            "ach", "wire", "internal", "cash",
            "funding_batch", "fee", "clearing_sweep",
        }
        actual = {
            _val(r, "transfer_type") for r in combined_parsed["transactions"]
        }
        assert actual.issubset(declared), (
            f"Undeclared transfer types: {actual - declared}"
        )
        assert actual == declared, (
            f"Missing transfer types in data: {declared - actual}"
        )

    def test_all_transactions_have_known_subledger_or_ledger(self, combined_parsed):
        """Every transactions row's account_id resolves to a known ledger or
        sub-ledger account."""
        ledger_ids = {
            _row_parts(r)[0] for r in combined_parsed["ar_ledger_accounts"]
        }
        subledger_ids = {
            _row_parts(r)[0] for r in combined_parsed["ar_subledger_accounts"]
        }
        for r in combined_parsed["transactions"]:
            account_id = _val(r, "account_id")
            assert account_id in ledger_ids or account_id in subledger_ids, (
                f"Unknown account_id in transaction: {account_id}"
            )

    def test_no_transfer_id_collision(self, combined_parsed):
        """PR / AR / investigation transfer IDs must not collide."""
        ids_by_app: dict[str, set[str]] = {}
        for r in combined_parsed["transactions"]:
            xid = _val(r, "transfer_id")
            ids_by_app.setdefault(_xid_app(xid), set()).add(xid)
        for app in ("pr", "ar", "inv"):
            assert ids_by_app.get(app), f"No {app.upper()} transfers"
        # Pairwise disjoint.
        for a, b in (("pr", "ar"), ("pr", "inv"), ("ar", "inv")):
            overlap = ids_by_app[a] & ids_by_app[b]
            assert not overlap, f"Transfer IDs collide across {a}/{b}: {overlap}"

    def test_no_transaction_id_collision(self, combined_parsed):
        """transaction_id must be globally unique."""
        ids = [_val(r, "transaction_id") for r in combined_parsed["transactions"]]
        assert len(ids) == len(set(ids)), "Duplicate transaction_id across apps"


# ---------------------------------------------------------------------------
# Phase G shared base layer — transactions + daily_balances dual-write
# ---------------------------------------------------------------------------

CANONICAL_ACCOUNT_TYPES = {
    "gl_control", "dda", "merchant_dda",
    "external_counter", "concentration_master", "funds_pool",
}


class TestSharedBaseLayer:
    def test_includes_pr_and_ar_transfer_types(self, combined_parsed):
        types = {
            _val(r, "transfer_type") for r in combined_parsed["transactions"]
        }
        assert {"sale", "settlement", "payment", "external_txn"}.issubset(types)
        assert {"ach", "wire", "clearing_sweep"}.issubset(types)

    def test_account_type_values_are_canonical(self, combined_parsed):
        types = {
            _val(r, "account_type") for r in combined_parsed["transactions"]
        }
        assert types.issubset(CANONICAL_ACCOUNT_TYPES), (
            f"Unknown account_type values: {types - CANONICAL_ACCOUNT_TYPES}"
        )

    def test_metadata_carries_source_provenance(self, combined_parsed):
        # Sample first 50 across both apps; every row must declare source.
        for row in combined_parsed["transactions"][:50]:
            doc = _metadata(row)
            assert doc, f"Metadata not JSON-quoted: {row[:120]}"
            assert "source" in doc, f"Missing source in metadata: {doc}"

    def test_pr_sales_carry_merchant_account_id(self, combined_parsed):
        # G.3.5 Phase H prep: every PR sale row carries merchant_account_id.
        sale_rows = [
            r for r in combined_parsed["transactions"]
            if _val(r, "transfer_type") == "sale"
        ]
        assert sale_rows, "Expected sale rows in shared transactions"
        for row in sale_rows[:30]:
            payload = _metadata(row)
            assert "merchant_account_id" in payload, (
                "Phase H prep: PR sale metadata must carry merchant_account_id"
            )

    def test_daily_balances_includes_pr_and_ar_accounts(self, combined_parsed):
        ids = {
            _row_parts(r)[0] for r in combined_parsed["daily_balances"]
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
            parts = _row_parts(r)
            account_id = parts[0]
            # control_account_id is col 2 — preserve NULL marker.
            raw_ctrl = r.split(",")[2].strip()
            if raw_ctrl == "NULL":
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


# ---------------------------------------------------------------------------
# Investigation seed (K.4.6)
# ---------------------------------------------------------------------------

@pytest.fixture()
def inv_sql() -> str:
    return generate_inv_sql(ANCHOR)


@pytest.fixture()
def inv_parsed(inv_sql: str) -> dict[str, list[str]]:
    return _parse_inserts(inv_sql)


def _inv_rows(parsed: dict[str, list[str]]) -> list[str]:
    """Investigation transactions rows: those whose transfer_id has the
    `inv-` prefix."""
    return [
        r for r in parsed["transactions"]
        if _val(r, "transfer_id").startswith("inv-")
    ]


class TestInvestigationDeterminism:
    def test_same_anchor_produces_identical_output(self):
        a = generate_inv_sql(ANCHOR)
        b = generate_inv_sql(ANCHOR)
        assert a == b

    def test_different_anchor_produces_different_dates(self):
        a = generate_inv_sql(date(2026, 1, 1))
        b = generate_inv_sql(date(2026, 6, 1))
        assert a != b

    def test_seed_output_hash_is_locked(self, inv_sql):
        """Pin the investigation seed hash so silent generator drift fails
        loudly.  Update the hash in the same commit when the change is
        intentional."""
        import hashlib
        digest = hashlib.sha256(inv_sql.encode()).hexdigest()
        assert digest == (
            "50787ad3e9ebec05877b6fd211241cc7a08370b1f482b9c52612c271adaa0804"
        ), f"investigation seed drifted; new hash: {digest}"


class TestInvestigationAccounts:
    def test_ledger_accounts_inserted(self, inv_parsed):
        ids = {_row_parts(r)[0] for r in inv_parsed["ar_ledger_accounts"]}
        for lid, _, _ in INV_LEDGER_ACCOUNTS:
            assert lid in ids, f"Missing investigation ledger: {lid}"

    def test_subledger_accounts_inserted(self, inv_parsed):
        ids = {_row_parts(r)[0] for r in inv_parsed["ar_subledger_accounts"]}
        for sid, *_ in INV_SUBLEDGER_ACCOUNTS:
            assert sid in ids, f"Missing investigation sub-ledger: {sid}"

    def test_no_daily_balances_rows(self, inv_parsed):
        """Investigation seed deliberately writes nothing to daily_balances.
        AR drift checks pivot on stored balance rows, so absent rows can't
        trigger false positives on investigation accounts."""
        assert "daily_balances" not in inv_parsed

    def test_subledger_account_types_canonical(self, inv_parsed):
        """Every investigation transactions row's account_type is in the
        canonical set."""
        types = {_val(r, "account_type") for r in _inv_rows(inv_parsed)}
        assert types.issubset(CANONICAL_ACCOUNT_TYPES), (
            f"Non-canonical account_type in investigation rows: "
            f"{types - CANONICAL_ACCOUNT_TYPES}"
        )

    def test_every_row_carries_source_provenance(self, inv_parsed):
        for r in _inv_rows(inv_parsed):
            doc = _metadata(r)
            assert doc, f"Metadata not JSON-quoted: {r[:120]}"
            assert "source" in doc, f"Missing source in metadata: {doc}"


class TestInvestigationScenarios:
    """K.4.6: each visual must have non-empty data."""

    def test_fanout_has_twelve_distinct_senders(self, inv_parsed):
        """K.4.3: the recipient (juniper) must receive from 12+ distinct
        external sender accounts to exceed the default 5-sender threshold."""
        juniper = "cust-900-0007-juniper-ridge-llc"
        senders: set[str] = set()
        # For each fanout transfer the sender leg has signed_amount < 0
        # and is a depositor; the credit leg lands on juniper.
        fanout_xfers = {
            _val(r, "transfer_id") for r in _inv_rows(inv_parsed)
            if _val(r, "transfer_id").startswith("inv-fanout-")
            and _val(r, "account_id") == juniper
        }
        assert len(fanout_xfers) >= 12, (
            f"Expected 12+ fanout transfers into juniper, got {len(fanout_xfers)}"
        )
        for r in _inv_rows(inv_parsed):
            xid = _val(r, "transfer_id")
            if xid in fanout_xfers and _val(r, "account_id") != juniper:
                senders.add(_val(r, "account_id"))
        assert len(senders) >= 12, (
            f"Need 12 distinct senders for K.4.3 fanout, got {len(senders)}"
        )
        # Every fanout sender must be an individual depositor.
        for s in senders:
            assert s.startswith("ext-individual-depositors-"), (
                f"Unexpected fanout sender: {s}"
            )

    def test_anomaly_has_baseline_plus_spike(self, inv_parsed):
        """K.4.4: 8 baseline cascadia→juniper wires + 1 spike day."""
        cascadia = "ext-cascadia-trust-bank-sub-ops"
        anomaly_credit_legs = [
            r for r in _inv_rows(inv_parsed)
            if _val(r, "transfer_id").startswith("inv-anomaly-")
            and _val(r, "account_id") == "cust-900-0007-juniper-ridge-llc"
        ]
        assert len(anomaly_credit_legs) == 9, (
            f"Expected 9 anomaly credit legs (8 base + 1 spike), "
            f"got {len(anomaly_credit_legs)}"
        )
        amounts = [Decimal(_val(r, "amount")) for r in anomaly_credit_legs]
        assert max(amounts) >= Decimal("25000"), (
            f"Spike must be ≥$25,000 to clear 2σ comfortably; max={max(amounts)}"
        )
        assert min(amounts) <= Decimal("700"), (
            f"Baseline must include sub-$700 wires; min={min(amounts)}"
        )
        # Source side is always cascadia.
        for r in _inv_rows(inv_parsed):
            xid = _val(r, "transfer_id")
            if not xid.startswith("inv-anomaly-"):
                continue
            if Decimal(_val(r, "signed_amount")) < 0:
                assert _val(r, "account_id") == cascadia, (
                    f"Anomaly debit leg not from cascadia: {_val(r, 'account_id')}"
                )

    def test_money_trail_chain_links_four_hops(self, inv_parsed):
        """K.4.5: 4-hop chain via parent_transfer_id."""
        chain_xfers = {
            _val(r, "transfer_id"): _val(r, "parent_transfer_id")
            for r in _inv_rows(inv_parsed)
            if _val(r, "transfer_id").startswith("inv-trail-")
        }
        assert set(chain_xfers.keys()) == {
            "inv-trail-root-001",
            "inv-trail-hop-002",
            "inv-trail-hop-003",
            "inv-trail-hop-004",
        }, f"Chain has unexpected transfers: {chain_xfers.keys()}"
        # Linkage: root has no parent; each subsequent hop points to its parent.
        assert chain_xfers["inv-trail-root-001"] == "NULL"
        assert chain_xfers["inv-trail-hop-002"] == "inv-trail-root-001"
        assert chain_xfers["inv-trail-hop-003"] == "inv-trail-hop-002"
        assert chain_xfers["inv-trail-hop-004"] == "inv-trail-hop-003"

    def test_money_trail_each_hop_has_two_legs(self, inv_parsed):
        """The matview source × target leg JOIN requires multi-leg transfers."""
        legs_by_xfer: dict[str, int] = {}
        for r in _inv_rows(inv_parsed):
            xid = _val(r, "transfer_id")
            if not xid.startswith("inv-trail-"):
                continue
            legs_by_xfer[xid] = legs_by_xfer.get(xid, 0) + 1
        for xid, n in legs_by_xfer.items():
            assert n == 2, f"Chain hop {xid} should have 2 legs, got {n}"

    def test_money_trail_terminates_at_shell_c(self, inv_parsed):
        """The chain ends at shell-company-c (no further hop)."""
        shell_c = "cust-700-0012-shell-company-c"
        # shell_c must appear as a credit (signed > 0) leg on hop-004.
        terminating = [
            r for r in _inv_rows(inv_parsed)
            if _val(r, "transfer_id") == "inv-trail-hop-004"
            and _val(r, "account_id") == shell_c
        ]
        assert len(terminating) == 1
        assert Decimal(terminating[0].split(",")[10].strip()) > 0, (
            "shell_c leg on terminal hop should be the credit leg"
        )

    def test_all_investigation_transfers_are_multi_leg(self, inv_parsed):
        """Every investigation transfer is 2-leg multi-leg — single-leg
        transfers don't surface as visible edges in the money-trail matview
        and don't pair-up in the anomaly matview."""
        legs_by_xfer: dict[str, int] = {}
        for r in _inv_rows(inv_parsed):
            xid = _val(r, "transfer_id")
            legs_by_xfer[xid] = legs_by_xfer.get(xid, 0) + 1
        offenders = {x: n for x, n in legs_by_xfer.items() if n != 2}
        assert not offenders, f"Non-2-leg investigation transfers: {offenders}"

    def test_all_legs_succeed(self, inv_parsed):
        """Investigation seed plants signal scenarios — no failed legs (which
        would be filtered out of all three matviews)."""
        for r in _inv_rows(inv_parsed):
            assert _val(r, "status") == "success", (
                f"Non-success investigation leg: {r[:120]}"
            )
