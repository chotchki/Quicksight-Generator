"""Demo data for Account Recon — Farmers Exchange Bank.

Deterministic SQL INSERTs for the ``ar_*`` tables. Plants scenarios
across four independent reconciliation checks so the Exceptions tab is
always populated:

* Failed-leg transfers — one leg posted, the counter-leg failed; the
  transfer's net-of-non-failed amount is non-zero.
* Off-amount transfers — both legs posted, amounts differ by a few
  dollars; non-zero net again but via a different mechanism.
* Balance drift — stored daily balance for a parent account doesn't
  match the sum of posted transactions for its children on that day.
* Limit breach — daily outbound for one (child, date, transfer_type)
  cell exceeds the parent's configured daily_limit for that type.
* Overdraft — stored child balance for a given day is negative.

Naming uses generic valley/farm/harvest vocabulary — no trademarked
characters or places.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


# ---------------------------------------------------------------------------
# Static definitions — valley / farm / harvest flavor
# ---------------------------------------------------------------------------

PARENT_ACCOUNTS: list[tuple[str, str, bool]] = [
    # (parent_account_id, name, is_internal)
    ("ar-par-checking",  "Big Meadow Checking",     True),
    ("ar-par-savings",   "Harvest Moon Savings",    True),
    ("ar-par-loans",     "Orchard Lending Pool",    True),
    ("ar-par-coop",      "Valley Grain Co-op",      False),
    ("ar-par-exchange",  "Harvest Credit Exchange", False),
]

ACCOUNTS: list[tuple[str, str, str]] = [
    # (account_id, name, parent_account_id)
    ("ar-acc-checking-main", "Checking – Main Office",       "ar-par-checking"),
    ("ar-acc-checking-west", "Checking – Westfield Branch",  "ar-par-checking"),
    ("ar-acc-savings-core",  "Savings – Core Reserve",       "ar-par-savings"),
    ("ar-acc-savings-op",    "Savings – Operating Surplus",  "ar-par-savings"),
    ("ar-acc-loans-farm",    "Loans – Farmland Mortgages",   "ar-par-loans"),
    ("ar-acc-loans-equip",   "Loans – Equipment Financing",  "ar-par-loans"),
    ("ar-acc-coop-clearing", "Valley Grain Co-op Clearing",  "ar-par-coop"),
    ("ar-acc-coop-settle",   "Valley Grain Co-op Settlement","ar-par-coop"),
    ("ar-acc-exchange-in",   "Harvest Exchange Inbound",     "ar-par-exchange"),
    ("ar-acc-exchange-out",  "Harvest Exchange Outbound",    "ar-par-exchange"),
]

_MEMOS = [
    "Feed lot settlement",
    "Grain silo delivery",
    "Irrigation canal dues",
    "Orchard payroll run",
    "Tractor lease payment",
    "Harvest market payout",
    "Fall seed advance",
    "Cold-storage fees",
    "Barn renovation draw",
    "Livestock auction clearing",
    "County co-op transfer",
    "Wheat futures settlement",
]

# Each bucket is split (cross_scope, internal_internal) so the demo
# exercises both patterns. Cross-scope transfers (one internal leg, one
# external) are the common case — the external leg doesn't affect any
# tracked balance. Internal-internal transfers touch two tracked balances
# at once; without them, a bug that sums a transfer's legs by transfer_id
# instead of account_id would never surface.
_SUCCESSFUL_CROSS_SCOPE = 28
_SUCCESSFUL_INTERNAL_INTERNAL = 20
_FAILED_LEG_CROSS_SCOPE = 2
_FAILED_LEG_INTERNAL_INTERNAL = 2
_OFF_AMOUNT_CROSS_SCOPE = 2
_OFF_AMOUNT_INTERNAL_INTERNAL = 2
_EXTRA_FAILED_CROSS_SCOPE = 2   # all legs failed — show up in failed-txn lists
_EXTRA_FAILED_INTERNAL_INTERNAL = 2
_SUCCESSFUL_TRANSFERS = _SUCCESSFUL_CROSS_SCOPE + _SUCCESSFUL_INTERNAL_INTERNAL
_FAILED_LEG_TRANSFERS = _FAILED_LEG_CROSS_SCOPE + _FAILED_LEG_INTERNAL_INTERNAL
_OFF_AMOUNT_TRANSFERS = _OFF_AMOUNT_CROSS_SCOPE + _OFF_AMOUNT_INTERNAL_INTERNAL
_EXTRA_FAILED_TRANSFERS = (
    _EXTRA_FAILED_CROSS_SCOPE + _EXTRA_FAILED_INTERNAL_INTERNAL
)
_TRANSFER_COUNT = (
    _SUCCESSFUL_TRANSFERS
    + _FAILED_LEG_TRANSFERS
    + _OFF_AMOUNT_TRANSFERS
    + _EXTRA_FAILED_TRANSFERS
)
_DAYS_OF_HISTORY = 40

# Planted drift cells — kept small so each drift table is readable.
#
# Parent and child drift are INDEPENDENT reconciliation problems (see
# SPEC "Reconciliation scope"). Planting them on different cells keeps
# the two Exceptions tables surfacing different rows.
#
# Parent drift: stored parent balance vs Σ children's stored balances.
_PARENT_DRIFT_PLANT: list[tuple[str, int, str]] = [
    # (parent_id, days_ago, delta as decimal string)
    ("ar-par-checking", 3,  "125.00"),
    ("ar-par-savings",  7,  "-80.50"),
    ("ar-par-loans",    14, "310.00"),
]

# Child drift: stored child balance vs Σ that child's posted transactions.
_CHILD_DRIFT_PLANT: list[tuple[str, int, str]] = [
    # (account_id, days_ago, delta as decimal string)
    ("ar-acc-checking-main", 5,  "200.00"),
    ("ar-acc-checking-west", 2,  "-75.00"),
    ("ar-acc-savings-core",  10, "-150.50"),
    ("ar-acc-loans-farm",    20, "450.00"),
]


# Transfer type weights — assigned per transfer. All four types must
# have non-trivial traffic so the transfer-type filter is exercised.
_TRANSFER_TYPES: list[tuple[str, int]] = [
    ("ach",      3),
    ("wire",     2),
    ("internal", 3),
    ("cash",     2),
]


# Parent-defined per-type daily transfer limits. Lenient amounts —
# normal seed transfers (up to $9,000 each, ≤1-2 per child × day × type)
# shouldn't accidentally breach these. Planted breaches inject an extra
# oversized transfer on a specific cell to force the breach.
#
# Absence of a row means "no limit enforced" (e.g., loans×wire is
# unlimited here — wire-out from loans accounts doesn't hit a limit).
# External parents (coop, exchange) have no rows — their children don't
# participate in the limit check (outbound view filters internal only).
_PARENT_LIMITS: list[tuple[str, str, str]] = [
    # (parent_account_id, transfer_type, daily_limit)
    ("ar-par-checking", "ach",  "20000.00"),
    ("ar-par-checking", "wire", "15000.00"),
    ("ar-par-savings",  "ach",  "12000.00"),
    ("ar-par-savings",  "wire", "15000.00"),
    ("ar-par-loans",    "cash", "10000.00"),
    ("ar-par-loans",    "ach",  "18000.00"),
]


# Limit breach plants: one extra outbound transfer per (child, day,
# type). Each plant amount is chosen to exceed the corresponding
# parent-limit entry so the breach view reliably surfaces the cell.
# Disjoint from _CHILD_DRIFT_PLANT (different cells) — each exception
# table surfaces a different set of rows.
_LIMIT_BREACH_PLANT: list[tuple[str, int, str, str, str]] = [
    # (account_id, days_ago, transfer_type, debit_amount, memo)
    ("ar-acc-checking-main", 8,  "wire", "22000.00", "Bulk wire payout"),
    ("ar-acc-savings-op",    12, "ach",  "16000.00", "Oversize ACH batch"),
    ("ar-acc-loans-equip",   18, "cash", "13000.00", "Large cash disbursement"),
]


# Overdraft plants: one extra outbound transfer per (child, day) that
# drives the child's running balance negative. The overdraft view picks
# up every day where stored balance < 0 — after the plant, the child
# may stay negative for several days until a compensating credit is
# emitted, which is the realistic operational shape for a short-lived
# overdraft. Disjoint from drift and breach plant cells.
_OVERDRAFT_PLANT: list[tuple[str, int, str, str]] = [
    # (account_id, days_ago, debit_amount, memo)
    ("ar-acc-checking-west", 6, "35000.00", "Emergency outbound — covered next day"),
    ("ar-acc-savings-op",    4, "18000.00", "Overnight sweep reversal pending"),
    ("ar-acc-loans-equip",   9, "28000.00", "Equipment purchase — funding pending"),
]


# External accounts used as counter-legs for planted breach/overdraft
# transfers. The counter-leg doesn't affect any tracked balance.
_EXTERNAL_COUNTER_LEG_POOL: list[str] = [
    "ar-acc-coop-clearing",
    "ar-acc-coop-settle",
    "ar-acc-exchange-in",
    "ar-acc-exchange-out",
]


# ---------------------------------------------------------------------------
# SQL formatting helpers
# ---------------------------------------------------------------------------

def _val(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (int, float)):
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


def _money(rng: random.Random, lo: float, hi: float) -> Decimal:
    raw = rng.uniform(lo, hi)
    return Decimal(str(raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ts(base: date, days_ago: int, rng: random.Random) -> datetime:
    d = base - timedelta(days=days_ago)
    return datetime(d.year, d.month, d.day,
                    rng.randint(8, 17), rng.randint(0, 59), 0)


def _pick_cross_scope_pair(
    rng: random.Random,
) -> tuple[str, str]:
    """Return (debit_account_id, credit_account_id) for one transfer.

    One leg is an internal child, the other is an external child. The
    direction is randomized so the "external leg" appears as both the
    debit and the credit side roughly half the time.
    """
    internal_ids = [a[0] for a in ACCOUNTS
                    if _parent_is_internal(a[2])]
    external_ids = [a[0] for a in ACCOUNTS
                    if not _parent_is_internal(a[2])]
    debit = rng.choice(internal_ids)
    credit = rng.choice(external_ids)
    if rng.random() < 0.5:
        return debit, credit
    return credit, debit


def _pick_internal_pair(
    rng: random.Random,
) -> tuple[str, str]:
    """Return (debit_account_id, credit_account_id) for one transfer
    between two distinct internal children.

    Both legs affect tracked balances — this exercises the case where
    a single transfer moves two child accounts' running totals in
    opposite directions.
    """
    internal_ids = [a[0] for a in ACCOUNTS
                    if _parent_is_internal(a[2])]
    debit = rng.choice(internal_ids)
    credit_choices = [a for a in internal_ids if a != debit]
    credit = rng.choice(credit_choices)
    return debit, credit


def _parent_is_internal(parent_id: str) -> bool:
    for pid, _name, is_internal in PARENT_ACCOUNTS:
        if pid == parent_id:
            return is_internal
    raise KeyError(parent_id)


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def _generate_transfers(
    rng: random.Random, today: date,
) -> list[dict]:
    """Generate the full mix of transfer legs.

    Returns a list of transaction dicts. Each transfer emits 2 legs
    with the same ``transfer_id`` but opposite-sign amounts (with
    intentional deviations for the failure buckets). Every bucket
    splits between cross-scope and internal-internal pair-picking so
    both patterns exist in the seed.
    """
    transactions: list[dict] = []
    txn_idx = 0

    def _emit(
        transfer_id: str,
        account_id: str,
        amount: Decimal,
        posted_at: datetime,
        status: str,
        transfer_type: str,
        memo: str,
    ) -> None:
        nonlocal txn_idx
        txn_idx += 1
        transactions.append({
            "transaction_id": f"ar-txn-{txn_idx:05d}",
            "account_id": account_id,
            "transfer_id": transfer_id,
            "amount": amount,
            "posted_at": posted_at,
            "status": status,
            "transfer_type": transfer_type,
            "memo": memo,
        })

    next_tid = [1]

    def _next_id() -> str:
        tid = f"ar-xfer-{next_tid[0]:04d}"
        next_tid[0] += 1
        return tid

    def _emit_pair(
        debit_acct: str, credit_acct: str,
        amount: Decimal, credit_amount: Decimal,
        posted: datetime,
        debit_status: str, credit_status: str,
        transfer_type: str,
        memo: str,
    ) -> None:
        tid = _next_id()
        _emit(tid, debit_acct, amount, posted, debit_status,
              transfer_type, memo)
        _emit(tid, credit_acct, credit_amount, posted, credit_status,
              transfer_type, memo)

    def _pick(pair_kind: str) -> tuple[str, str]:
        if pair_kind == "cross":
            return _pick_cross_scope_pair(rng)
        return _pick_internal_pair(rng)

    type_pool = [t for t, w in _TRANSFER_TYPES for _ in range(w)]

    def _pick_type() -> str:
        return rng.choice(type_pool)

    # 1. Successful transfers — both legs posted, amounts sum to zero.
    for pair_kind, count in (
        ("cross", _SUCCESSFUL_CROSS_SCOPE),
        ("internal", _SUCCESSFUL_INTERNAL_INTERNAL),
    ):
        for _ in range(count):
            debit_acct, credit_acct = _pick(pair_kind)
            amount = _money(rng, 100, 9000)
            posted = _ts(today, rng.randint(1, _DAYS_OF_HISTORY - 1), rng)
            memo = rng.choice(_MEMOS)
            _emit_pair(debit_acct, credit_acct,
                       amount, -amount, posted,
                       "posted", "posted", _pick_type(), memo)

    # 2. Failed-leg transfers — debit posts, credit fails. Net non-zero.
    for pair_kind, count in (
        ("cross", _FAILED_LEG_CROSS_SCOPE),
        ("internal", _FAILED_LEG_INTERNAL_INTERNAL),
    ):
        for _ in range(count):
            debit_acct, credit_acct = _pick(pair_kind)
            amount = _money(rng, 200, 4000)
            posted = _ts(today, rng.randint(2, 20), rng)
            memo = rng.choice(_MEMOS)
            _emit_pair(debit_acct, credit_acct,
                       amount, -amount, posted,
                       "posted", "failed", _pick_type(), memo)

    # 3. Off-amount transfers — both legs posted but amounts don't
    #    balance (manual keying error, rounding, fee drift).
    for pair_kind, count in (
        ("cross", _OFF_AMOUNT_CROSS_SCOPE),
        ("internal", _OFF_AMOUNT_INTERNAL_INTERNAL),
    ):
        for _ in range(count):
            debit_acct, credit_acct = _pick(pair_kind)
            amount = _money(rng, 300, 5000)
            offset = _money(rng, 2, 25)
            posted = _ts(today, rng.randint(2, 25), rng)
            memo = rng.choice(_MEMOS)
            _emit_pair(debit_acct, credit_acct,
                       amount, -(amount + offset), posted,
                       "posted", "posted", _pick_type(), memo)

    # 4. Fully-failed transfers — both legs failed. Exposes the
    #    failed-transactions list without distorting net.
    for pair_kind, count in (
        ("cross", _EXTRA_FAILED_CROSS_SCOPE),
        ("internal", _EXTRA_FAILED_INTERNAL_INTERNAL),
    ):
        for _ in range(count):
            debit_acct, credit_acct = _pick(pair_kind)
            amount = _money(rng, 150, 2500)
            posted = _ts(today, rng.randint(2, 30), rng)
            memo = rng.choice(_MEMOS)
            _emit_pair(debit_acct, credit_acct,
                       amount, -amount, posted,
                       "failed", "failed", _pick_type(), memo)

    # 5. Planted limit-breach transfers — oversized outbound on a
    #    specific (child, day, type) cell that exceeds the parent's
    #    configured daily_limit. Counter-leg lands on an external
    #    account so it doesn't perturb another tracked child.
    for i, (acct, days_ago, xtype, amount_str, memo) in enumerate(
        _LIMIT_BREACH_PLANT,
    ):
        amount = Decimal(amount_str)
        external_leg = _EXTERNAL_COUNTER_LEG_POOL[
            i % len(_EXTERNAL_COUNTER_LEG_POOL)
        ]
        posted = _ts(today, days_ago, rng)
        _emit_pair(acct, external_leg,
                   -amount, amount, posted,
                   "posted", "posted", xtype, memo)

    # 6. Planted overdraft transfers — outbound debit that drives the
    #    child's running balance below zero for the planted day. Uses
    #    'internal' transfer_type so it doesn't inflate ach/wire/cash
    #    outbound totals (keeps breach plants independent).
    for i, (acct, days_ago, amount_str, memo) in enumerate(
        _OVERDRAFT_PLANT,
    ):
        amount = Decimal(amount_str)
        external_leg = _EXTERNAL_COUNTER_LEG_POOL[
            (i + 1) % len(_EXTERNAL_COUNTER_LEG_POOL)
        ]
        posted = _ts(today, days_ago, rng)
        _emit_pair(acct, external_leg,
                   -amount, amount, posted,
                   "posted", "posted", "internal", memo)

    return transactions


def _generate_daily_balances(
    today: date, transactions: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Compute stored daily balances at both account levels.

    Child balances are the running Σ of posted txns per internal child.
    Parent balances are Σ of children's stored balances per internal parent.
    Child-level and parent-level drift are then planted independently —
    child drift offsets the child stored balance only; parent drift
    offsets the parent stored balance only.

    Returns ``(account_balance_rows, parent_balance_rows)``. Only
    internal accounts/parents get stored balance rows (the application
    does not reconcile external accounts — see SPEC).
    """
    internal_parents = {pid for pid, _n, is_int in PARENT_ACCOUNTS if is_int}
    internal_children = [
        (aid, pid) for aid, _n, pid in ACCOUNTS if pid in internal_parents
    ]

    # ---- Child-level stored balances ----
    account_balances: dict[tuple[str, date], Decimal] = {}
    for account_id, _parent_id in internal_children:
        running = Decimal("0.00")
        for days_ago in range(_DAYS_OF_HISTORY, -1, -1):
            bdate = today - timedelta(days=days_ago)
            for t in transactions:
                if (
                    t["status"] == "posted"
                    and t["account_id"] == account_id
                    and t["posted_at"].date() == bdate
                ):
                    running += t["amount"]
            account_balances[(account_id, bdate)] = running

    for account_id, days_ago, delta_str in _CHILD_DRIFT_PLANT:
        key = (account_id, today - timedelta(days=days_ago))
        if key in account_balances:
            account_balances[key] += Decimal(delta_str)

    # ---- Parent-level stored balances ----
    # Σ of children's (planted) stored balances per parent per day.
    parent_balances: dict[tuple[str, date], Decimal] = {}
    for parent_id in internal_parents:
        parent_children = [
            aid for aid, pid in internal_children if pid == parent_id
        ]
        for days_ago in range(_DAYS_OF_HISTORY, -1, -1):
            bdate = today - timedelta(days=days_ago)
            total = sum(
                (account_balances[(aid, bdate)] for aid in parent_children),
                Decimal("0.00"),
            )
            parent_balances[(parent_id, bdate)] = total

    for parent_id, days_ago, delta_str in _PARENT_DRIFT_PLANT:
        key = (parent_id, today - timedelta(days=days_ago))
        if key in parent_balances:
            parent_balances[key] += Decimal(delta_str)

    account_rows = [
        {
            "account_id": aid,
            "balance_date": bdate,
            "balance": bal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        }
        for (aid, bdate), bal in sorted(account_balances.items())
    ]
    parent_rows = [
        {
            "parent_account_id": pid,
            "balance_date": bdate,
            "balance": bal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        }
        for (pid, bdate), bal in sorted(parent_balances.items())
    ]
    return account_rows, parent_rows


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def generate_demo_sql(anchor_date: date | None = None) -> str:
    """Return INSERT statements for every ``ar_*`` demo table.

    Deterministic for a given anchor_date (default: today).
    """
    rng = random.Random(42)
    today = anchor_date or date.today()

    parent_rows = [
        (pid, name, is_internal)
        for pid, name, is_internal in PARENT_ACCOUNTS
    ]
    account_rows = [
        # is_internal derived from parent
        (aid, name, _parent_is_internal(pid), pid)
        for aid, name, pid in ACCOUNTS
    ]
    transactions = _generate_transfers(rng, today)
    account_balances, parent_balances = _generate_daily_balances(
        today, transactions,
    )

    parts = [
        f"-- Farmers Exchange Bank — demo seed data",
        f"-- Anchor date: {today.isoformat()}\n",

        _inserts("ar_parent_accounts",
                 ["parent_account_id", "name", "is_internal"],
                 parent_rows),

        _inserts("ar_accounts",
                 ["account_id", "name", "is_internal", "parent_account_id"],
                 account_rows),

        _inserts("ar_transactions",
                 ["transaction_id", "account_id", "transfer_id",
                  "amount", "posted_at", "status", "transfer_type", "memo"],
                 [(t["transaction_id"], t["account_id"], t["transfer_id"],
                   t["amount"], t["posted_at"], t["status"],
                   t["transfer_type"], t["memo"])
                  for t in transactions]),

        _inserts("ar_parent_transfer_limits",
                 ["parent_account_id", "transfer_type", "daily_limit"],
                 [(pid, xtype, Decimal(lim))
                  for pid, xtype, lim in _PARENT_LIMITS]),

        _inserts("ar_parent_daily_balances",
                 ["parent_account_id", "balance_date", "balance"],
                 [(b["parent_account_id"], b["balance_date"], b["balance"])
                  for b in parent_balances]),

        _inserts("ar_account_daily_balances",
                 ["account_id", "balance_date", "balance"],
                 [(b["account_id"], b["balance_date"], b["balance"])
                  for b in account_balances]),
    ]
    return "\n".join(parts) + "\n"
