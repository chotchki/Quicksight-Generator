"""Demo data for Account Recon — Sasquatch National Bank (SNB).

Deterministic SQL INSERTs for the ``ar_*`` tables. Account model is
GL-control accounts (numbered per a typical bank chart of accounts) +
per-customer DDAs + ZBA operating sub-pools, plus external counterparty
ledgers (Federal Reserve, card processor, suppliers). See
``docs/Training_Story.md`` for the business framing.

Plants scenarios across the existing reconciliation checks so the
Exceptions tab is always populated:

* Failed-leg transfers — one leg posted, the counter-leg failed; the
  transfer's net-of-non-failed amount is non-zero.
* Off-amount transfers — both legs posted, amounts differ by a few
  dollars; non-zero net again but via a different mechanism.
* Balance drift — stored daily balance for a ledger account doesn't
  match the sum of posted transactions for its sub-ledgers on that day.
* Limit breach — daily outbound for one (sub-ledger, date, transfer_type)
  cell exceeds the ledger's configured daily_limit for that type.
* Overdraft — stored sub-ledger balance for a given day is negative.

ID scheme:
* ``gl-<num>-<slug>``         GL control accounts       (e.g. ``gl-2010-dda-control``)
* ``cust-<num>-<slug>``       customer DDAs             (e.g. ``cust-900-0001-bigfoot-brews``)
* ``gl-<num>-sub-<slug>``     operational sub-pools     (e.g. ``gl-1850-sub-big-meadow-dairy-main``)
* ``ext-<slug>`` / ``ext-<slug>-sub-<role>``  external counterparties + their sub-pools
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


# ---------------------------------------------------------------------------
# Static definitions — Sasquatch National Bank chart of accounts
# ---------------------------------------------------------------------------

LEDGER_ACCOUNTS: list[tuple[str, str, bool]] = [
    # (ledger_account_id, name, is_internal)
    # Internal GL control accounts — SNB's chart of accounts.
    ("gl-1010-cash-due-frb",              "Cash & Due From Federal Reserve",  True),
    ("gl-1810-ach-orig-settlement",       "ACH Origination Settlement",       True),
    ("gl-1815-card-acquiring-settlement", "Card Acquiring Settlement",        True),
    ("gl-1820-wire-settlement-suspense",  "Wire Settlement Suspense",         True),
    ("gl-1830-internal-transfer-suspense","Internal Transfer Suspense",       True),
    ("gl-1850-cash-concentration-master", "Cash Concentration Master",        True),
    ("gl-1899-internal-suspense-recon",   "Internal Suspense / Reconciliation", True),
    ("gl-2010-dda-control",               "Customer Deposits — DDA Control",  True),
    # External counterparties — SNB transacts with them but doesn't hold
    # their accounts. Reconciliation compares SNB's view to the
    # counterparty's view (Fed statement, processor reports, etc.).
    ("ext-frb-snb-master",                "Federal Reserve Bank — SNB Master", False),
    ("ext-payment-gateway-processor",     "Payment Gateway Processor",        False),
    ("ext-coffee-shop-supply-co",         "Coffee Shop Supply Co",            False),
    ("ext-valley-grain-coop",             "Valley Grain Co-op",               False),
    ("ext-harvest-credit-exchange",       "Harvest Credit Exchange",          False),
]

SUBLEDGER_ACCOUNTS: list[tuple[str, str, str]] = [
    # (subledger_account_id, name, ledger_account_id)
    #
    # Customer DDAs under Customer Deposits — DDA Control.
    # Account numbers follow SNB's pattern: 900-* merchants, 800-*/700-*
    # commercial customers (legacy FEB acquisition kept their original
    # 800/700 numbering ranges).
    ("cust-900-0001-bigfoot-brews",       "Bigfoot Brews — DDA",              "gl-2010-dda-control"),
    ("cust-900-0002-sasquatch-sips",      "Sasquatch Sips — DDA",             "gl-2010-dda-control"),
    ("cust-900-0003-yeti-espresso",       "Yeti Espresso — DDA",              "gl-2010-dda-control"),
    ("cust-800-0001-cascade-timber-mill", "Cascade Timber Mill — DDA",        "gl-2010-dda-control"),
    ("cust-800-0002-pinecrest-vineyards", "Pinecrest Vineyards LLC — DDA",    "gl-2010-dda-control"),
    ("cust-700-0001-big-meadow-dairy",    "Big Meadow Dairy — DDA",           "gl-2010-dda-control"),
    ("cust-700-0002-harvest-moon-bakery", "Harvest Moon Bakery — DDA",        "gl-2010-dda-control"),
    #
    # ZBA operating sub-accounts under Cash Concentration Master. Each
    # sweeps to zero EOD; the master receives the consolidated balance.
    # Big Meadow Dairy and Cascade Timber Mill have multiple operating
    # locations (the primary ZBA scenario customers); the others have one.
    ("gl-1850-sub-big-meadow-dairy-main",   "Big Meadow Dairy — Operating (Main)",   "gl-1850-cash-concentration-master"),
    ("gl-1850-sub-big-meadow-dairy-north",  "Big Meadow Dairy — Operating (North)",  "gl-1850-cash-concentration-master"),
    ("gl-1850-sub-cascade-timber-mill-a",   "Cascade Timber Mill — Operating (Mill A)", "gl-1850-cash-concentration-master"),
    ("gl-1850-sub-cascade-timber-mill-b",   "Cascade Timber Mill — Operating (Mill B)", "gl-1850-cash-concentration-master"),
    ("gl-1850-sub-pinecrest-vineyards",     "Pinecrest Vineyards LLC — Operating",   "gl-1850-cash-concentration-master"),
    ("gl-1850-sub-harvest-moon-bakery",     "Harvest Moon Bakery — Operating",       "gl-1850-cash-concentration-master"),
    #
    # External counterparty sub-pools — clearing/settlement or
    # inbound/outbound split per counterparty so cross-scope transfers
    # have realistic counter-leg targets.
    ("ext-frb-sub-inbound",                 "FRB Master — Inbound (credits to SNB)",  "ext-frb-snb-master"),
    ("ext-frb-sub-outbound",                "FRB Master — Outbound (debits from SNB)","ext-frb-snb-master"),
    ("ext-payment-gateway-sub-clearing",    "Payment Gateway — Clearing",           "ext-payment-gateway-processor"),
    ("ext-payment-gateway-sub-settlement",  "Payment Gateway — Settlement",         "ext-payment-gateway-processor"),
    ("ext-coffee-supply-sub-inbound",       "Coffee Shop Supply Co — Inbound",      "ext-coffee-shop-supply-co"),
    ("ext-coffee-supply-sub-outbound",      "Coffee Shop Supply Co — Outbound",     "ext-coffee-shop-supply-co"),
    ("ext-valley-grain-sub-clearing",       "Valley Grain Co-op — Clearing",        "ext-valley-grain-coop"),
    ("ext-valley-grain-sub-settlement",     "Valley Grain Co-op — Settlement",      "ext-valley-grain-coop"),
    ("ext-harvest-credit-sub-inbound",      "Harvest Credit Exchange — Inbound",    "ext-harvest-credit-exchange"),
    ("ext-harvest-credit-sub-outbound",     "Harvest Credit Exchange — Outbound",   "ext-harvest-credit-exchange"),
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
# instead of subledger_account_id would never surface.
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
# Ledger and sub-ledger drift are INDEPENDENT reconciliation problems
# (see SPEC "Reconciliation scope"). Planting them on different cells
# keeps the two Exceptions tables surfacing different rows.
#
# Ledger drift: stored ledger balance vs Σ sub-ledgers' stored balances.
_LEDGER_DRIFT_PLANT: list[tuple[str, int, str]] = [
    # (ledger_account_id, days_ago, delta as decimal string)
    ("ar-par-checking", 3,  "125.00"),
    ("ar-par-savings",  7,  "-80.50"),
    ("ar-par-loans",    14, "310.00"),
]

# Sub-ledger drift: stored sub-ledger balance vs Σ that sub-ledger's
# posted transactions.
_SUBLEDGER_DRIFT_PLANT: list[tuple[str, int, str]] = [
    # (subledger_account_id, days_ago, delta as decimal string)
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


# Ledger-defined per-type daily transfer limits. Lenient amounts —
# normal seed transfers (up to $9,000 each, ≤1-2 per sub-ledger × day ×
# type) shouldn't accidentally breach these. Planted breaches inject an
# extra oversized transfer on a specific cell to force the breach.
#
# Absence of a row means "no limit enforced" (e.g., loans×wire is
# unlimited here — wire-out from loans accounts doesn't hit a limit).
# External ledgers (coop, exchange) have no rows — their sub-ledgers
# don't participate in the limit check (outbound view filters internal
# only).
_LEDGER_LIMITS: list[tuple[str, str, str]] = [
    # (ledger_account_id, transfer_type, daily_limit)
    ("ar-par-checking", "ach",  "20000.00"),
    ("ar-par-checking", "wire", "15000.00"),
    ("ar-par-savings",  "ach",  "12000.00"),
    ("ar-par-savings",  "wire", "15000.00"),
    ("ar-par-loans",    "cash", "10000.00"),
    ("ar-par-loans",    "ach",  "18000.00"),
]


# Limit breach plants: one extra outbound transfer per (sub-ledger, day,
# type). Each plant amount is chosen to exceed the corresponding
# ledger-limit entry so the breach view reliably surfaces the cell.
# Disjoint from _SUBLEDGER_DRIFT_PLANT (different cells) — each exception
# table surfaces a different set of rows.
_LIMIT_BREACH_PLANT: list[tuple[str, int, str, str, str]] = [
    # (subledger_account_id, days_ago, transfer_type, debit_amount, memo)
    ("ar-acc-checking-main", 8,  "wire", "22000.00", "Bulk wire payout"),
    ("ar-acc-savings-op",    12, "ach",  "16000.00", "Oversize ACH batch"),
    ("ar-acc-loans-equip",   18, "cash", "13000.00", "Large cash disbursement"),
]


# Overdraft plants: one extra outbound transfer per (sub-ledger, day)
# that drives the sub-ledger's running balance negative. The overdraft
# view picks up every day where stored balance < 0 — after the plant,
# the sub-ledger may stay negative for several days until a compensating
# credit is emitted, which is the realistic operational shape for a
# short-lived overdraft. Disjoint from drift and breach plant cells.
_OVERDRAFT_PLANT: list[tuple[str, int, str, str]] = [
    # (subledger_account_id, days_ago, debit_amount, memo)
    ("ar-acc-checking-west", 6, "35000.00", "Emergency outbound — covered next day"),
    ("ar-acc-savings-op",    4, "18000.00", "Overnight sweep reversal pending"),
    ("ar-acc-loans-equip",   9, "28000.00", "Equipment purchase — funding pending"),
]


# External sub-ledger accounts used as counter-legs for planted breach/
# overdraft transfers. The counter-leg doesn't affect any tracked balance.
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
    """Return (debit_subledger_id, credit_subledger_id) for one transfer.

    One leg is an internal sub-ledger, the other is an external
    sub-ledger. The direction is randomized so the "external leg"
    appears as both the debit and the credit side roughly half the time.
    """
    internal_ids = [s[0] for s in SUBLEDGER_ACCOUNTS
                    if _ledger_is_internal(s[2])]
    external_ids = [s[0] for s in SUBLEDGER_ACCOUNTS
                    if not _ledger_is_internal(s[2])]
    debit = rng.choice(internal_ids)
    credit = rng.choice(external_ids)
    if rng.random() < 0.5:
        return debit, credit
    return credit, debit


def _pick_internal_pair(
    rng: random.Random,
) -> tuple[str, str]:
    """Return (debit_subledger_id, credit_subledger_id) for one transfer
    between two distinct internal sub-ledgers.

    Both legs affect tracked balances — this exercises the case where
    a single transfer moves two sub-ledger accounts' running totals in
    opposite directions.
    """
    internal_ids = [s[0] for s in SUBLEDGER_ACCOUNTS
                    if _ledger_is_internal(s[2])]
    debit = rng.choice(internal_ids)
    credit_choices = [s for s in internal_ids if s != debit]
    credit = rng.choice(credit_choices)
    return debit, credit


def _ledger_is_internal(ledger_id: str) -> bool:
    for lid, _name, is_internal in LEDGER_ACCOUNTS:
        if lid == ledger_id:
            return is_internal
    raise KeyError(ledger_id)


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
        subledger_account_id: str,
        amount: Decimal,
        posted_at: datetime,
        status: str,
        transfer_type: str,
        memo: str,
    ) -> None:
        nonlocal txn_idx
        txn_idx += 1
        # ~10% of rows land on external_force_posted — every 10th leg,
        # deterministic given the emit order. Tag-only in Phase A;
        # downstream phases will consume it.
        origin = (
            "external_force_posted" if txn_idx % 10 == 0
            else "internal_initiated"
        )
        transactions.append({
            "transaction_id": f"ar-txn-{txn_idx:05d}",
            "subledger_account_id": subledger_account_id,
            "transfer_id": transfer_id,
            "amount": amount,
            "posted_at": posted_at,
            "status": status,
            "transfer_type": transfer_type,
            "origin": origin,
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
    #    specific (sub-ledger, day, type) cell that exceeds the ledger's
    #    configured daily_limit. Counter-leg lands on an external
    #    sub-ledger so it doesn't perturb another tracked sub-ledger.
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
    #    sub-ledger's running balance below zero for the planted day.
    #    Uses 'internal' transfer_type so it doesn't inflate
    #    ach/wire/cash outbound totals (keeps breach plants independent).
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


# ---------------------------------------------------------------------------
# Ledger-level transfers (funding batches, fees, clearing sweeps)
# ---------------------------------------------------------------------------

_FUNDING_BATCH_COUNT = 5
_FEE_ASSESSMENT_COUNT = 3
_CLEARING_SWEEP_COUNT = 2

_FUNDING_MEMOS = [
    "Overnight funding batch",
    "Federal wire settlement",
    "ACH batch credit",
    "Clearing house deposit",
    "Correspondent bank transfer",
]

_FEE_MEMOS = [
    "Monthly maintenance fee",
    "Wire transfer fee",
    "Overdraft assessment fee",
]

_SWEEP_MEMOS = [
    "End-of-day clearing sweep",
    "Inter-ledger netting",
]


def _generate_ledger_level_transfers(
    rng: random.Random, today: date,
) -> tuple[list[tuple], list[tuple]]:
    """Generate transfers with ledger-level postings.

    Three scenario types:
    - Funding batch: 1 ledger credit + N sub-ledger debits (money arrives
      at ledger before distribution).
    - Fee assessment: 1 ledger debit only (single-leg, intentionally
      non-zero — exercises non-zero transfer + ledger drift exceptions).
    - Clearing sweep: 2 ledger postings (debit + credit) that net to zero.

    Returns (transfer_rows, posting_rows) in tuple format matching the
    existing INSERT column order.
    """
    internal_ledgers = [
        lid for lid, _n, is_int in LEDGER_ACCOUNTS if is_int
    ]
    internal_subledgers_by_ledger: dict[str, list[str]] = {}
    for sid, _n, lid in SUBLEDGER_ACCOUNTS:
        if _ledger_is_internal(lid):
            internal_subledgers_by_ledger.setdefault(lid, []).append(sid)

    transfer_rows: list[tuple] = []
    posting_rows: list[tuple] = []
    tid_idx = 0
    post_idx = 0

    def _next_tid() -> str:
        nonlocal tid_idx
        tid_idx += 1
        return f"ar-ledger-xfer-{tid_idx:04d}"

    def _next_post_id() -> str:
        nonlocal post_idx
        post_idx += 1
        return f"ar-ledger-post-{post_idx:05d}"

    # 1. Funding batches — credit to ledger, debits to sub-ledgers
    for i in range(_FUNDING_BATCH_COUNT):
        ledger_id = rng.choice(internal_ledgers)
        subs = internal_subledgers_by_ledger[ledger_id]
        total = _money(rng, 5000, 25000)
        posted = _ts(today, rng.randint(1, _DAYS_OF_HISTORY - 1), rng)
        tid = _next_tid()
        memo = _FUNDING_MEMOS[i % len(_FUNDING_MEMOS)]

        transfer_rows.append((
            tid, None, "funding_batch", "internal_initiated",
            total, "posted", posted, memo,
        ))
        # Ledger-level credit (positive = inbound)
        posting_rows.append((
            _next_post_id(), tid, ledger_id, None,
            total, posted, "success",
        ))
        # Distribute debits across sub-ledgers
        remaining = total
        for j, sub_id in enumerate(subs):
            if j == len(subs) - 1:
                share = remaining
            else:
                share = _money(rng, float(total) * 0.1, float(total) * 0.5)
                share = min(share, remaining)
            remaining -= share
            posting_rows.append((
                _next_post_id(), tid, ledger_id, sub_id,
                -share, posted, "success",
            ))

    # 2. Fee assessments — single ledger debit (intentionally unbalanced)
    for i in range(_FEE_ASSESSMENT_COUNT):
        ledger_id = rng.choice(internal_ledgers)
        amount = _money(rng, 15, 150)
        posted = _ts(today, rng.randint(1, _DAYS_OF_HISTORY - 1), rng)
        tid = _next_tid()
        memo = _FEE_MEMOS[i % len(_FEE_MEMOS)]

        transfer_rows.append((
            tid, None, "fee", "internal_initiated",
            amount, "posted", posted, memo,
        ))
        posting_rows.append((
            _next_post_id(), tid, ledger_id, None,
            -amount, posted, "success",
        ))

    # 3. Clearing sweeps — 2 ledger postings that net to zero
    for i in range(_CLEARING_SWEEP_COUNT):
        ledger_id = rng.choice(internal_ledgers)
        amount = _money(rng, 2000, 15000)
        posted = _ts(today, rng.randint(1, _DAYS_OF_HISTORY - 1), rng)
        tid = _next_tid()
        memo = _SWEEP_MEMOS[i % len(_SWEEP_MEMOS)]

        transfer_rows.append((
            tid, None, "clearing_sweep", "internal_initiated",
            amount, "posted", posted, memo,
        ))
        posting_rows.append((
            _next_post_id(), tid, ledger_id, None,
            amount, posted, "success",
        ))
        posting_rows.append((
            _next_post_id(), tid, ledger_id, None,
            -amount, posted, "success",
        ))

    return transfer_rows, posting_rows


def _generate_daily_balances(
    today: date,
    transactions: list[dict],
    ledger_posting_rows: list[tuple] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Compute stored daily balances at both account levels.

    Sub-ledger balances are the running Σ of posted txns per internal
    sub-ledger. Ledger balances are Σ of sub-ledgers' stored balances
    plus Σ of direct ledger postings per internal ledger.

    ``ledger_posting_rows`` are tuples in posting INSERT order:
    (posting_id, transfer_id, ledger_account_id, subledger_account_id,
     signed_amount, posted_at, status).  Only rows where
    subledger_account_id is None count as direct ledger postings.

    Returns ``(subledger_balance_rows, ledger_balance_rows)``. Only
    internal sub-ledgers/ledgers get stored balance rows (the
    application does not reconcile external accounts — see SPEC).
    """
    internal_ledgers = {lid for lid, _n, is_int in LEDGER_ACCOUNTS if is_int}
    internal_subledgers = [
        (sid, lid) for sid, _n, lid in SUBLEDGER_ACCOUNTS if lid in internal_ledgers
    ]

    # ---- Sub-ledger stored balances ----
    subledger_balances: dict[tuple[str, date], Decimal] = {}
    for subledger_account_id, _ledger_id in internal_subledgers:
        running = Decimal("0.00")
        for days_ago in range(_DAYS_OF_HISTORY, -1, -1):
            bdate = today - timedelta(days=days_ago)
            for t in transactions:
                if (
                    t["status"] == "posted"
                    and t["subledger_account_id"] == subledger_account_id
                    and t["posted_at"].date() == bdate
                ):
                    running += t["amount"]
            subledger_balances[(subledger_account_id, bdate)] = running

    for subledger_account_id, days_ago, delta_str in _SUBLEDGER_DRIFT_PLANT:
        key = (subledger_account_id, today - timedelta(days=days_ago))
        if key in subledger_balances:
            subledger_balances[key] += Decimal(delta_str)

    # ---- Direct ledger postings by (ledger, date) ----
    direct_ledger_totals: dict[tuple[str, date], Decimal] = {}
    for row in (ledger_posting_rows or []):
        _pid, _tid, lid, sub_id, amount, posted_at, status = row
        if sub_id is not None:
            continue  # sub-ledger posting — already in subledger_balances
        if status != "success":
            continue
        if lid not in internal_ledgers:
            continue
        bdate = posted_at.date() if isinstance(posted_at, datetime) else posted_at
        key = (lid, bdate)
        direct_ledger_totals[key] = (
            direct_ledger_totals.get(key, Decimal("0")) + Decimal(str(amount))
        )

    # ---- Ledger stored balances ----
    # Σ of sub-ledgers' (planted) stored balances + Σ direct ledger
    # postings per internal ledger per day.
    ledger_balances: dict[tuple[str, date], Decimal] = {}
    for ledger_id in internal_ledgers:
        ledger_subledgers = [
            sid for sid, lid in internal_subledgers if lid == ledger_id
        ]
        running_direct = Decimal("0.00")
        for days_ago in range(_DAYS_OF_HISTORY, -1, -1):
            bdate = today - timedelta(days=days_ago)
            sub_total = sum(
                (subledger_balances[(sid, bdate)] for sid in ledger_subledgers),
                Decimal("0.00"),
            )
            running_direct += direct_ledger_totals.get(
                (ledger_id, bdate), Decimal("0"),
            )
            ledger_balances[(ledger_id, bdate)] = sub_total + running_direct

    for ledger_id, days_ago, delta_str in _LEDGER_DRIFT_PLANT:
        key = (ledger_id, today - timedelta(days=days_ago))
        if key in ledger_balances:
            ledger_balances[key] += Decimal(delta_str)

    subledger_rows = [
        {
            "subledger_account_id": sid,
            "balance_date": bdate,
            "balance": bal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        }
        for (sid, bdate), bal in sorted(subledger_balances.items())
    ]
    ledger_rows = [
        {
            "ledger_account_id": lid,
            "balance_date": bdate,
            "balance": bal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        }
        for (lid, bdate), bal in sorted(ledger_balances.items())
    ]
    return subledger_rows, ledger_rows


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def _derive_unified_tables(
    transactions: list[dict],
) -> tuple[list[tuple], list[tuple]]:
    """Derive unified ``transfer`` + ``posting`` rows from AR transactions.

    Groups transactions by transfer_id to produce one transfer row per
    group. Each transaction maps to one posting row. AR transfers have
    no chain-of-custody, so parent_transfer_id is always NULL.
    """
    from collections import OrderedDict

    by_transfer: OrderedDict[str, list[dict]] = OrderedDict()
    for t in transactions:
        by_transfer.setdefault(t["transfer_id"], []).append(t)

    subledger_to_ledger = {sid: lid for sid, _n, lid in SUBLEDGER_ACCOUNTS}

    transfer_rows: list[tuple] = []
    posting_rows: list[tuple] = []

    for tid, legs in by_transfer.items():
        first = legs[0]
        any_posted = any(leg["status"] == "posted" for leg in legs)
        any_external = any(
            leg["origin"] == "external_force_posted" for leg in legs
        )
        transfer_rows.append((
            tid,
            None,  # parent_transfer_id — AR doesn't chain
            first["transfer_type"],
            "external_force_posted" if any_external else "internal_initiated",
            abs(first["amount"]),
            "posted" if any_posted else "failed",
            first["posted_at"],
            first["memo"],
        ))
        for leg in legs:
            status_map = {"posted": "success", "failed": "failed"}
            posting_rows.append((
                leg["transaction_id"],
                tid,
                subledger_to_ledger[leg["subledger_account_id"]],
                leg["subledger_account_id"],
                leg["amount"],  # already signed
                leg["posted_at"],
                status_map.get(leg["status"], "success"),
            ))

    return transfer_rows, posting_rows


def generate_demo_sql(anchor_date: date | None = None) -> str:
    """Return INSERT statements for every ``ar_*`` demo table.

    Deterministic for a given anchor_date (default: today).
    """
    rng = random.Random(42)
    today = anchor_date or date.today()

    ledger_rows = [
        (lid, name, is_internal)
        for lid, name, is_internal in LEDGER_ACCOUNTS
    ]
    subledger_rows = [
        # is_internal derived from the ledger
        (sid, name, _ledger_is_internal(lid), lid)
        for sid, name, lid in SUBLEDGER_ACCOUNTS
    ]
    transactions = _generate_transfers(rng, today)
    transfer_rows, posting_rows = _derive_unified_tables(transactions)

    ledger_xfer_rows, ledger_post_rows = _generate_ledger_level_transfers(
        rng, today,
    )
    transfer_rows.extend(ledger_xfer_rows)
    posting_rows.extend(ledger_post_rows)

    subledger_balances, ledger_balances = _generate_daily_balances(
        today, transactions, ledger_posting_rows=ledger_post_rows,
    )

    parts = [
        f"-- Sasquatch National Bank — demo seed data",
        f"-- Anchor date: {today.isoformat()}\n",

        _inserts("ar_ledger_accounts",
                 ["ledger_account_id", "name", "is_internal"],
                 ledger_rows),

        _inserts("ar_subledger_accounts",
                 ["subledger_account_id", "name", "is_internal", "ledger_account_id"],
                 subledger_rows),

        _inserts("ar_ledger_transfer_limits",
                 ["ledger_account_id", "transfer_type", "daily_limit"],
                 [(lid, xtype, Decimal(lim))
                  for lid, xtype, lim in _LEDGER_LIMITS]),

        _inserts("ar_ledger_daily_balances",
                 ["ledger_account_id", "balance_date", "balance"],
                 [(b["ledger_account_id"], b["balance_date"], b["balance"])
                  for b in ledger_balances]),

        _inserts("ar_subledger_daily_balances",
                 ["subledger_account_id", "balance_date", "balance"],
                 [(b["subledger_account_id"], b["balance_date"], b["balance"])
                  for b in subledger_balances]),

        _inserts("transfer",
                 ["transfer_id", "parent_transfer_id", "transfer_type",
                  "origin", "amount", "status", "created_at", "memo"],
                 transfer_rows),

        _inserts("posting",
                 ["posting_id", "transfer_id", "ledger_account_id",
                  "subledger_account_id", "signed_amount", "posted_at",
                  "status"],
                 posting_rows),
    ]
    return "\n".join(parts) + "\n"
