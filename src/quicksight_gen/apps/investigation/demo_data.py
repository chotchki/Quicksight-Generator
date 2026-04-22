"""Demo data generator for the Investigation app.

Plants three scenarios on the shared ``transactions`` base table:

* Fanout cluster — 12 individual depositors → ``cust-900-0007-juniper-ridge-llc``
  (drives the K.4.3 Recipient Fanout sheet past the default 5-sender threshold).
* Anomaly pair — ``ext-cascadia-trust-bank-sub-ops`` → juniper, with 8 baseline
  daily wires + 1 spike day (drives the K.4.4 Volume Anomalies sheet past the
  default 2σ threshold).
* Money trail chain — 4-hop layering chain rooted on a Cascadia wire, fanning
  through juniper into three shell DDAs (drives the K.4.5 Money Trail sheet
  with a non-trivial Sankey).

Investigation registers its own internal ledger (``inv-customer-deposits-watch``)
+ two external ledgers so ``demo seed investigation`` is FK-safe standalone.
No ``daily_balances`` rows are written: investigation visuals only consume
``transactions``, and AR drift checks pivot on stored balance rows so absent
rows can't trigger false positives.
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any


# ---------------------------------------------------------------------------
# Account model — investigation-only ledgers and sub-ledgers
# ---------------------------------------------------------------------------

INV_LEDGER_ACCOUNTS: list[tuple[str, str, bool]] = [
    # (ledger_account_id, name, is_internal)
    ("inv-customer-deposits-watch",  "Investigation Watch — Customer Deposits", True),
    ("ext-individual-depositors",    "Individual Depositors",                   False),
    ("ext-cascadia-trust-bank",      "Cascadia Trust Bank",                     False),
]

INV_SUBLEDGER_ACCOUNTS: list[tuple[str, str, bool, str, str]] = [
    # (subledger_account_id, name, is_internal, ledger_account_id, account_type)
    ("cust-900-0007-juniper-ridge-llc", "Juniper Ridge LLC — DDA",
     True,  "inv-customer-deposits-watch", "dda"),
    ("cust-700-0010-shell-company-a",   "Shell Company A — DDA",
     True,  "inv-customer-deposits-watch", "dda"),
    ("cust-700-0011-shell-company-b",   "Shell Company B — DDA",
     True,  "inv-customer-deposits-watch", "dda"),
    ("cust-700-0012-shell-company-c",   "Shell Company C — DDA",
     True,  "inv-customer-deposits-watch", "dda"),
    *[
        (f"ext-individual-depositors-d{i:02d}",
         f"Individual Depositor {i:02d}",
         False, "ext-individual-depositors", "external_counter")
        for i in range(1, 13)
    ],
    ("ext-cascadia-trust-bank-sub-ops", "Cascadia Trust Bank — Operations",
     False, "ext-cascadia-trust-bank", "external_counter"),
]


_SUB_LOOKUP: dict[str, tuple[str, bool, str, str]] = {
    sid: (name, is_internal, ctrl, acct_type)
    for (sid, name, is_internal, ctrl, acct_type) in INV_SUBLEDGER_ACCOUNTS
}


def _denorm(account_id: str) -> tuple[str, str, str, bool]:
    """(account_name, control_account_id, account_type, is_internal)."""
    if account_id not in _SUB_LOOKUP:
        raise KeyError(f"No investigation account: {account_id!r}")
    name, is_internal, ctrl, acct_type = _SUB_LOOKUP[account_id]
    return name, ctrl, acct_type, is_internal


# ---------------------------------------------------------------------------
# SQL formatting helpers
# ---------------------------------------------------------------------------

def _val(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (int, float)):
        # bool is a subclass of int — str(True) → "True", which Postgres
        # accepts. Matches PR/AR convention.
        return str(v)
    if isinstance(v, datetime):
        return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    raise TypeError(f"Unsupported SQL value type: {type(v)}")


def _inserts(table: str, columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return ""
    col_list = ", ".join(columns)
    lines = [f"INSERT INTO {table} ({col_list}) VALUES"]
    for i, row in enumerate(rows):
        vals = ", ".join(_val(v) for v in row)
        sep = "," if i < len(rows) - 1 else ";"
        lines.append(f"  ({vals}){sep}")
    return "\n".join(lines) + "\n"


def _json_metadata(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


# ---------------------------------------------------------------------------
# Transfer-row helper (every scenario hop is a 2-leg multi-leg transfer)
# ---------------------------------------------------------------------------

def _make_transfer_rows(
    *,
    transfer_id: str,
    parent_transfer_id: str | None,
    transfer_type: str,
    debit_account: str,
    credit_account: str,
    amount: Decimal,
    posted_at: datetime,
    source: str,
    memo: str,
) -> list[tuple]:
    debit_name, debit_ctrl, debit_type, debit_internal = _denorm(debit_account)
    credit_name, credit_ctrl, credit_type, credit_internal = _denorm(credit_account)
    metadata = _json_metadata({"source": source})
    balance_date = posted_at.date()
    return [
        (
            f"{transfer_id}-leg-d",
            transfer_id,
            parent_transfer_id,
            transfer_type,
            "internal_initiated",
            debit_account, debit_name, debit_ctrl, debit_type, debit_internal,
            -amount, amount,
            "success",
            posted_at,
            None,
            balance_date,
            None,
            memo,
            metadata,
        ),
        (
            f"{transfer_id}-leg-c",
            transfer_id,
            parent_transfer_id,
            transfer_type,
            "internal_initiated",
            credit_account, credit_name, credit_ctrl, credit_type, credit_internal,
            amount, amount,
            "success",
            posted_at,
            None,
            balance_date,
            None,
            memo,
            metadata,
        ),
    ]


# ---------------------------------------------------------------------------
# Scenario generators
# ---------------------------------------------------------------------------

JUNIPER = "cust-900-0007-juniper-ridge-llc"
CASCADIA_OPS = "ext-cascadia-trust-bank-sub-ops"
SHELL_A = "cust-700-0010-shell-company-a"
SHELL_B = "cust-700-0011-shell-company-b"
SHELL_C = "cust-700-0012-shell-company-c"


def _generate_fanout_cluster(
    rng: random.Random, today: date,
) -> list[tuple]:
    """K.4.3 driver: 12 depositors × 2 ACH transfers each → juniper."""
    rows: list[tuple] = []
    for d in range(1, 13):
        sender = f"ext-individual-depositors-d{d:02d}"
        for n in range(2):
            days_ago = rng.randint(1, 29)
            posted_at = datetime.combine(
                today - timedelta(days=days_ago),
                datetime.min.time(),
            ).replace(hour=rng.randint(8, 17), minute=rng.randint(0, 59))
            amount = Decimal(rng.randint(50, 500))
            rows.extend(_make_transfer_rows(
                transfer_id=f"inv-fanout-d{d:02d}-{n:02d}",
                parent_transfer_id=None,
                transfer_type="ach",
                debit_account=sender,
                credit_account=JUNIPER,
                amount=amount,
                posted_at=posted_at,
                source="ach_processor",
                memo=f"ACH deposit from depositor {d:02d}",
            ))
    return rows


def _generate_anomaly_pair(
    rng: random.Random, today: date,
) -> list[tuple]:
    """K.4.4 driver: cascadia → juniper, 8 baseline + 1 spike day.

    The spike's 2-day rolling window will exceed 2σ once
    ``inv_pair_rolling_anomalies`` computes its z-score over the population.
    """
    rows: list[tuple] = []
    for n in range(8):
        days_ago = 25 - n  # contiguous days 25..18, oldest first
        posted_at = datetime.combine(
            today - timedelta(days=days_ago),
            datetime.min.time(),
        ).replace(hour=10, minute=0)
        amount = Decimal(rng.randint(300, 700))
        rows.extend(_make_transfer_rows(
            transfer_id=f"inv-anomaly-base-{n:02d}",
            parent_transfer_id=None,
            transfer_type="wire",
            debit_account=CASCADIA_OPS,
            credit_account=JUNIPER,
            amount=amount,
            posted_at=posted_at,
            source="wire_network",
            memo=f"Cascadia routine wire #{n + 1}",
        ))
    spike_at = datetime.combine(
        today - timedelta(days=10),
        datetime.min.time(),
    ).replace(hour=10, minute=0)
    rows.extend(_make_transfer_rows(
        transfer_id="inv-anomaly-spike-001",
        parent_transfer_id=None,
        transfer_type="wire",
        debit_account=CASCADIA_OPS,
        credit_account=JUNIPER,
        amount=Decimal("25000.00"),
        posted_at=spike_at,
        source="wire_network",
        memo="Cascadia anomaly wire — investigate",
    ))
    return rows


def _generate_money_trail_chain(today: date) -> list[tuple]:
    """K.4.5 driver: 4-hop layering chain.

    cascadia → juniper → shell-a → shell-b → shell-c. Each hop is a 2-leg
    multi-leg transfer so the matview's ``source × target`` JOIN produces
    one edge per hop. ``parent_transfer_id`` chains them; depth-0 is the
    root (NULL parent).
    """
    chain: list[tuple[str, str, str]] = [
        ("inv-trail-root-001", CASCADIA_OPS, JUNIPER),
        ("inv-trail-hop-002",  JUNIPER,      SHELL_A),
        ("inv-trail-hop-003",  SHELL_A,      SHELL_B),
        ("inv-trail-hop-004",  SHELL_B,      SHELL_C),
    ]
    rows: list[tuple] = []
    parent: str | None = None
    base_amount = Decimal("18750.00")
    for hop_idx, (tid, debit, credit) in enumerate(chain):
        posted_at = datetime.combine(
            today - timedelta(days=5 - hop_idx),
            datetime.min.time(),
        ).replace(hour=14 + hop_idx, minute=0)
        # Slight residue per hop — layering rarely round-trips a clean amount.
        amount = base_amount - Decimal(hop_idx * 250)
        rows.extend(_make_transfer_rows(
            transfer_id=tid,
            parent_transfer_id=parent,
            transfer_type="wire" if hop_idx == 0 else "internal",
            debit_account=debit,
            credit_account=credit,
            amount=amount,
            posted_at=posted_at,
            source="wire_network" if hop_idx == 0 else "core_banking",
            memo=f"Layering hop {hop_idx} — manual investigation",
        ))
        parent = tid
    return rows


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

ANCHOR_DEFAULT = date(2026, 4, 11)


def generate_demo_sql(anchor_date: date | None = None) -> str:
    """Return SQL for investigation-specific seed data."""
    today = anchor_date or ANCHOR_DEFAULT
    rng = random.Random(42)

    transaction_rows: list[tuple] = []
    transaction_rows.extend(_generate_fanout_cluster(rng, today))
    transaction_rows.extend(_generate_anomaly_pair(rng, today))
    transaction_rows.extend(_generate_money_trail_chain(today))

    parts = [
        "-- Investigation — demo seed data",
        f"-- Anchor date: {today.isoformat()}\n",

        _inserts(
            "ar_ledger_accounts",
            ["ledger_account_id", "name", "is_internal"],
            list(INV_LEDGER_ACCOUNTS),
        ),

        _inserts(
            "ar_subledger_accounts",
            ["subledger_account_id", "name", "is_internal", "ledger_account_id"],
            [(sid, name, is_internal, ctrl)
             for (sid, name, is_internal, ctrl, _atype) in INV_SUBLEDGER_ACCOUNTS],
        ),

        _inserts(
            "transactions",
            ["transaction_id", "transfer_id", "parent_transfer_id",
             "transfer_type", "origin", "account_id", "account_name",
             "control_account_id", "account_type", "is_internal",
             "signed_amount", "amount", "status", "posted_at",
             "expected_complete_at", "balance_date", "external_system",
             "memo", "metadata"],
            transaction_rows,
        ),
    ]
    return "\n".join(parts) + "\n"
