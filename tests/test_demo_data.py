"""Unit tests for the Investigation demo data generator (M.4.3 trim).

Originally tested PR + AR + Investigation seeds. After M.4.3 (apps/account_recon
deleted) + M.4.4 (apps/payment_recon deletion pending), the AR + PR portions
were removed; only the Investigation tests remain. M.4.5 will re-evaluate
whether Investigation itself stays.
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal

import pytest

from quicksight_gen.apps.investigation.demo_data import (
    INV_LEDGER_ACCOUNTS,
    INV_SUBLEDGER_ACCOUNTS,
    generate_demo_sql as generate_inv_sql,
)


ANCHOR = date(2026, 4, 11)


# Canonical account_type set per the shared base layer (Schema_v6).
CANONICAL_ACCOUNT_TYPES = {
    "gl_control", "dda", "merchant_dda",
    "external_counter", "concentration_master", "funds_pool",
}


# ---------------------------------------------------------------------------
# Parsing helpers — generic, used by Investigation tests only after M.4.3
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
    """Naive comma-split of a VALUES row. Strips outer single quotes
    from each token so callers can compare against plain strings.
    Safe for cols 0..16; metadata (last column) may contain commas
    inside the JSON string but we don't parse past it via this helper.
    """
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    in_quote = False
    for ch in row:
        if ch == "'" and (not cur or cur[-1] != "\\"):
            in_quote = not in_quote
        if not in_quote and ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        cur.append(ch)
    out.append("".join(cur).strip())
    # Strip outer single quotes — callers compare against unquoted Python
    # strings (e.g. INV_LEDGER_ACCOUNTS tuples).
    stripped: list[str] = []
    for tok in out:
        if tok.startswith("'") and tok.endswith("'"):
            stripped.append(tok[1:-1])
        else:
            stripped.append(tok)
    return stripped


def _val(row: str, col: str) -> str:
    parts = _row_parts(row)
    raw = parts[_COL_IDX[col]]
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    return raw


def _last_quoted(row: str) -> str | None:
    """Return the last single-quoted substring on the row, if any."""
    matches = re.findall(r"'((?:[^'\\]|\\.)*)'", row)
    return matches[-1] if matches else None


def _metadata(row: str) -> dict:
    raw = _last_quoted(row)
    if raw is None:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _parse_inserts(sql: str) -> dict[str, list[str]]:
    """Pull INSERT INTO …rows into ``{table: [row_text, ...]}`` dict."""
    out: dict[str, list[str]] = {}
    pattern = re.compile(
        r"INSERT INTO (\w+).*?VALUES\s*(.+?);", re.DOTALL,
    )
    for m in pattern.finditer(sql):
        table = m.group(1)
        body = m.group(2)
        # Split on `),(` boundaries, then trim.
        rows = re.split(r"\)\s*,\s*\(", body)
        cleaned = [r.lstrip("(").rstrip(")") for r in rows]
        out.setdefault(table, []).extend(cleaned)
    return out


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
        loudly. Update the hash in the same commit when the change is
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
