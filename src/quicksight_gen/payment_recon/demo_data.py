"""Demo data generation — sasquatch coffee shops in Seattle.

Produces deterministic SQL INSERT statements for the demo schema
(``demo/schema.sql``).  All dates are relative to an anchor date
(default: today) so the data always looks fresh.

Usage::

    from quicksight_gen.payment_recon.demo_data import generate_demo_sql
    sql = generate_demo_sql()            # uses today
    sql = generate_demo_sql(date(2026, 1, 15))  # fixed anchor
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Static definitions
# ---------------------------------------------------------------------------

MERCHANTS: list[tuple[str, str, str, str]] = [
    # (merchant_id, merchant_name, merchant_type, location_id)
    ("merch-bigfoot",   "Bigfoot Brews",       "franchise",   "loc-capitol-hill"),
    ("merch-sasquatch", "Sasquatch Sips",      "franchise",   "loc-pike-place"),
    ("merch-yeti",      "Yeti Espresso",       "independent", "loc-ballard"),
    ("merch-skookum",   "Skookum Coffee Co.",  "independent", "loc-fremont"),
    ("merch-cryptid",   "Cryptid Coffee Cart", "cart",        "loc-u-district"),
    ("merch-wildman",   "Wildman's Roastery",  "independent", "loc-queen-anne"),
]

_MERCHANT_WEIGHTS = [35, 25, 15, 10, 8, 7]

_CARD_BRANDS = ["Visa", "Mastercard", "Amex", "Discover"]
_CARD_WEIGHTS = [45, 30, 15, 10]

_RETURNED_PAYMENTS: list[tuple[str, str]] = [
    ("merch-sasquatch", "insufficient_funds"),
    ("merch-sasquatch", "bank_rejected"),
    ("merch-yeti",      "disputed"),
    ("merch-cryptid",   "account_closed"),
    ("merch-cryptid",   "invalid_account"),
]

_UNSETTLED_MERCHANTS = {"merch-yeti", "merch-cryptid"}
_UNSETTLED_COUNT = 10
_SALE_COUNT = 200
_REFUND_COUNT = 15
_METADATA_OPTIONS = [
    "loyalty:gold", "loyalty:silver", "loyalty:bronze",
    "promo:SQUATCH10", "promo:BIGFOOT20", "promo:YETI15",
    "catering:true",
]

_PAYMENT_METHODS = ["card", "cash", "mobile_wallet", "gift_card"]
_PAYMENT_METHOD_WEIGHTS = [60, 20, 15, 5]

_CASHIERS = [
    "Alex Ridgeway", "Jordan Cascade", "Sam Sawyer", "Morgan Elk",
    "Taylor Creek", "Riley Moss", "Jamie Pine", "Casey Hollow",
]


# ---------------------------------------------------------------------------
# SQL formatting helpers
# ---------------------------------------------------------------------------

def _val(v: Any) -> str:
    """Format a Python value as a SQL literal."""
    if v is None:
        return "NULL"
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
    """Build a multi-row INSERT statement."""
    if not rows:
        return ""
    col_list = ", ".join(columns)
    lines = [f"INSERT INTO {table} ({col_list}) VALUES"]
    for i, row in enumerate(rows):
        vals = ", ".join(_val(v) for v in row)
        sep = "," if i < len(rows) - 1 else ";"
        lines.append(f"  ({vals}){sep}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _amount(rng: random.Random) -> Decimal:
    """Random coffee-shop sale amount ($3.50 – $48.00)."""
    r = rng.random()
    if r < 0.60:
        raw = rng.uniform(3.50, 8.00)
    elif r < 0.85:
        raw = rng.uniform(8.00, 16.00)
    elif r < 0.95:
        raw = rng.uniform(16.00, 30.00)
    else:
        raw = rng.uniform(30.00, 48.00)
    return Decimal(str(raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ts(base: date, days_ago: int, rng: random.Random) -> datetime:
    """Random timestamp on a given day (6 AM – 8 PM)."""
    d = base - timedelta(days=days_ago)
    return datetime(d.year, d.month, d.day,
                    rng.randint(6, 20), rng.randint(0, 59), 0)


def _merchant_type(merchant_id: str) -> str:
    return next(m[2] for m in MERCHANTS if m[0] == merchant_id)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_demo_sql(anchor_date: date | None = None) -> str:
    """Return INSERT statements for all demo tables.

    Data is deterministic (``random.Random(42)``).  Dates are relative
    to *anchor_date* (default: today) so the dataset stays fresh.
    """
    rng = random.Random(42)
    today = anchor_date or date.today()

    # -- Merchants --
    merchant_rows: list[tuple] = []
    for mid, name, mtype, loc in MERCHANTS:
        created = today - timedelta(days=rng.randint(180, 365))
        merchant_rows.append((mid, name, mtype, loc, created, "active"))

    # -- Sales (plus refund rows mixed into the pool) --
    sales = _generate_sales(rng, today)
    refunds = _generate_refunds(rng, sales)
    sales.extend(refunds)
    sales.sort(key=lambda s: s["sale_timestamp"])

    # -- Settlements (groups of sales; leaves some unsettled) --
    settlements = _generate_settlements(rng, today, sales)

    # -- Payments --
    payments = _generate_payments(rng, settlements, sales)

    # -- Inject a handful of reconciliation mismatches so the Exceptions-tab
    #    mismatch tables are non-empty (SPEC 2.4).
    _inject_mismatches(rng, settlements, payments)

    # -- External transactions + linking --
    ext_txns = _generate_external_transactions(rng, today, payments)

    # -- Assemble SQL in FK-safe order --
    parts = [
        f"-- Sasquatch National Bank — demo seed data",
        f"-- Anchor date: {today.isoformat()}\n",

        _inserts("pr_merchants",
                 ["merchant_id", "merchant_name", "merchant_type",
                  "location_id", "created_at", "status"],
                 merchant_rows),

        _inserts("pr_external_transactions",
                 ["transaction_id", "external_system",
                  "external_amount", "record_count", "transaction_date",
                  "status", "merchant_id"],
                 [(e["transaction_id"],
                   e["external_system"], e["external_amount"],
                   e["record_count"], e["transaction_date"],
                   e["status"], e["merchant_id"])
                  for e in ext_txns]),

        _inserts("pr_settlements",
                 ["settlement_id", "merchant_id", "settlement_type",
                  "settlement_amount", "settlement_date", "settlement_status",
                  "sale_count"],
                 [(s["settlement_id"], s["merchant_id"], s["settlement_type"],
                   s["settlement_amount"], s["settlement_date"],
                   s["settlement_status"], s["sale_count"])
                  for s in settlements]),

        _inserts("pr_sales",
                 ["sale_id", "merchant_id", "location_id", "amount",
                  "sale_type", "payment_method",
                  "sale_timestamp", "card_brand", "card_last_four",
                  "reference_id", "metadata", "settlement_id",
                  "taxes", "tips", "discount_percentage", "cashier"],
                 [(s["sale_id"], s["merchant_id"], s["location_id"],
                   s["amount"], s["sale_type"], s["payment_method"],
                   s["sale_timestamp"], s["card_brand"],
                   s["card_last_four"], s["reference_id"], s["metadata"],
                   s["settlement_id"],
                   s["taxes"], s["tips"], s["discount_percentage"],
                   s["cashier"])
                  for s in sales]),

        _inserts("pr_payments",
                 ["payment_id", "settlement_id", "merchant_id",
                  "payment_amount", "payment_date", "payment_status",
                  "is_returned", "return_reason", "external_transaction_id",
                  "payment_method"],
                 [(p["payment_id"], p["settlement_id"], p["merchant_id"],
                   p["payment_amount"], p["payment_date"], p["payment_status"],
                   p["is_returned"], p["return_reason"], p["ext_txn_id"],
                   p["payment_method"])
                  for p in payments]),
    ]
    return "\n".join(parts) + "\n"


def generate_demo_sql_to_file(
    path: str | Path,
    anchor_date: date | None = None,
) -> None:
    """Write demo INSERT statements to a file."""
    Path(path).write_text(generate_demo_sql(anchor_date))


# ---------------------------------------------------------------------------
# Phase generators
# ---------------------------------------------------------------------------

def _generate_sales(rng: random.Random, today: date) -> list[dict]:
    """Generate ~200 sales across all merchants."""
    sales: list[dict] = []
    for i in range(_SALE_COUNT):
        idx = rng.choices(range(len(MERCHANTS)), _MERCHANT_WEIGHTS)[0]
        mid, _, _, loc = MERCHANTS[idx]
        days_ago = rng.randint(0, 89)

        payment_method = rng.choices(
            _PAYMENT_METHODS, _PAYMENT_METHOD_WEIGHTS
        )[0]

        card_brand = None
        card_last_four = None
        ref_id = None
        if payment_method == "card" and rng.random() >= 0.05:
            card_brand = rng.choices(_CARD_BRANDS, _CARD_WEIGHTS)[0]
            card_last_four = f"{rng.randint(0, 9999):04d}"
            ref_id = f"REF-{i + 1:04d}"

        metadata = None
        if rng.random() < 0.20:
            metadata = rng.choice(_METADATA_OPTIONS)

        amount = _amount(rng)
        # Taxes run ~9.5% in Seattle; tips ~15% on ~60% of sales
        taxes = (amount * Decimal("0.095")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        tips = None
        if rng.random() < 0.60:
            tip_pct = Decimal(str(rng.uniform(0.10, 0.25))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            tips = (amount * tip_pct).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
        discount_pct = None
        if rng.random() < 0.15:
            discount_pct = Decimal(str(rng.uniform(5, 25))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
        cashier = rng.choice(_CASHIERS)

        sales.append({
            "sale_id": f"sale-{i + 1:04d}",
            "merchant_id": mid,
            "location_id": loc,
            "amount": amount,
            "sale_type": "sale",
            "payment_method": payment_method,
            "sale_timestamp": _ts(today, days_ago, rng),
            "card_brand": card_brand,
            "card_last_four": card_last_four,
            "reference_id": ref_id,
            "metadata": metadata,
            "settlement_id": None,
            "taxes": taxes,
            "tips": tips,
            "discount_percentage": discount_pct,
            "cashier": cashier,
        })
    return sales


def _generate_refunds(
    rng: random.Random,
    sales: list[dict],
) -> list[dict]:
    """Generate refund rows from a subset of existing sales.

    Refunds are emitted as negative-amount ``sale_type='refund'`` rows that
    flow back through settlement grouping — settlements containing a refund
    net lower (or negative) totals via signed sums.

    Most refunds occur after the original sale (0h–5d later); a minority are
    pre-dated (within 6 hours *before*) to exercise the "some not later"
    edge case from SPEC 2.1.  Refunds are sourced from merchants that
    always settle so refund rows reliably reach the payment pipeline.
    """
    candidates = [s for s in sales
                  if s["merchant_id"] not in _UNSETTLED_MERCHANTS]
    rng.shuffle(candidates)
    sources = candidates[:_REFUND_COUNT]

    refunds: list[dict] = []
    for i, orig in enumerate(sources, start=1):
        if rng.random() < 0.40:
            factor = Decimal(str(rng.uniform(0.30, 0.80))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            refund_amount = (orig["amount"] * factor).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            refund_amount = orig["amount"]

        if rng.random() < 0.15:
            delta = timedelta(hours=-rng.randint(1, 6))
        else:
            delta = timedelta(hours=rng.randint(1, 120))

        refunds.append({
            "sale_id": f"ref-{i:04d}",
            "merchant_id": orig["merchant_id"],
            "location_id": orig["location_id"],
            "amount": -refund_amount,
            "sale_type": "refund",
            "payment_method": orig["payment_method"],
            "sale_timestamp": orig["sale_timestamp"] + delta,
            "card_brand": orig["card_brand"],
            "card_last_four": orig["card_last_four"],
            "reference_id": f"RFND-{i:04d}" if orig["reference_id"] else None,
            "metadata": orig["metadata"],
            "settlement_id": None,
            "taxes": None,
            "tips": None,
            "discount_percentage": None,
            "cashier": orig["cashier"],
        })
    return refunds


def _generate_settlements(
    rng: random.Random,
    today: date,
    sales: list[dict],
) -> list[dict]:
    """Group sales into settlements; leave ~10 unsettled."""
    # Pick unsettled sales from Yeti and Cryptid
    unsettled_pool = [s for s in sales
                      if s["merchant_id"] in _UNSETTLED_MERCHANTS]
    rng.shuffle(unsettled_pool)
    unsettled_ids = {s["sale_id"] for s in unsettled_pool[:_UNSETTLED_COUNT]}

    # Group remaining sales by merchant, sorted by timestamp
    by_merchant: dict[str, list[dict]] = {}
    for s in sales:
        if s["sale_id"] not in unsettled_ids:
            by_merchant.setdefault(s["merchant_id"], []).append(s)
    for lst in by_merchant.values():
        lst.sort(key=lambda x: x["sale_timestamp"])

    batch_sizes = {"franchise": 7, "independent": 5, "cart": 4}
    type_map = {"franchise": "daily", "independent": "weekly", "cart": "monthly"}

    settlements: list[dict] = []
    stl_idx = 0

    for mid, _, mtype, _ in MERCHANTS:
        if mid not in by_merchant:
            continue
        msales = by_merchant[mid]
        bsz = batch_sizes[mtype]

        for start in range(0, len(msales), bsz):
            batch = msales[start:start + bsz]
            stl_idx += 1
            stl_id = f"stl-{stl_idx:04d}"
            stl_amount = sum(s["amount"] for s in batch)
            stl_dt = max(s["sale_timestamp"] for s in batch) + timedelta(
                days=rng.randint(1, 3))

            if stl_idx <= 2:
                status = "failed"
            elif stl_dt.date() >= today - timedelta(days=2):
                status = "pending"
            else:
                status = "completed"

            settlements.append({
                "settlement_id": stl_id,
                "merchant_id": mid,
                "settlement_type": type_map[mtype],
                "settlement_amount": stl_amount,
                "settlement_date": stl_dt,
                "settlement_status": status,
                "sale_count": len(batch),
            })

            # Link sales → settlement
            for s in batch:
                s["settlement_id"] = stl_id

    return settlements


def _generate_payments(
    rng: random.Random,
    settlements: list[dict],
    sales: list[dict],
) -> list[dict]:
    """One payment per non-pending settlement; 5 returns.

    ``payment_method`` is copied from the most common method among the
    settlement's linked sales so it filters consistently on Settlements and
    Payments tabs.
    """
    payable = [s for s in settlements if s["settlement_status"] != "pending"]

    # Pre-assign returns to specific settlements so every return reason
    # lands on a real payment regardless of iteration order.
    return_map: dict[str, str] = {}  # settlement_id → return_reason
    return_queue = list(_RETURNED_PAYMENTS)
    rng.shuffle(return_queue)
    for rmid, rreason in return_queue:
        for stl in payable:
            if stl["merchant_id"] == rmid and stl["settlement_id"] not in return_map:
                return_map[stl["settlement_id"]] = rreason
                break

    # Map settlement_id → plurality payment_method (ties resolved
    # deterministically by _PAYMENT_METHODS order).
    method_by_settlement: dict[str, str] = {}
    for stl in payable:
        methods = [s["payment_method"] for s in sales
                   if s["settlement_id"] == stl["settlement_id"]]
        if not methods:
            method_by_settlement[stl["settlement_id"]] = "card"
            continue
        counts = {m: methods.count(m) for m in _PAYMENT_METHODS}
        method_by_settlement[stl["settlement_id"]] = max(
            _PAYMENT_METHODS, key=lambda m: counts[m]
        )

    payments: list[dict] = []
    for pay_idx, stl in enumerate(payable, start=1):
        pay_date = stl["settlement_date"] + timedelta(days=rng.randint(1, 5))
        return_reason = return_map.get(stl["settlement_id"])
        is_returned = return_reason is not None

        payments.append({
            "payment_id": f"pay-{pay_idx:04d}",
            "settlement_id": stl["settlement_id"],
            "merchant_id": stl["merchant_id"],
            "payment_amount": stl["settlement_amount"],
            "payment_date": pay_date,
            "payment_status": "returned" if is_returned else "completed",
            "is_returned": "true" if is_returned else "false",
            "return_reason": return_reason,
            "ext_txn_id": None,
            "payment_method": method_by_settlement[stl["settlement_id"]],
        })

    return payments


def _inject_mismatches(
    rng: random.Random,
    settlements: list[dict],
    payments: list[dict],
) -> None:
    """Perturb a handful of settlement/payment amounts (SPEC 2.4).

    - Bumps 3 settlement amounts by ±$10 while keeping their payment in
      sync — surfaces in ``pr_sale_settlement_mismatch``.
    - Bumps 3 payment amounts by ±$5 while leaving the settlement
      untouched — surfaces in ``pr_settlement_payment_mismatch``.

    Mutations are in place; caller lists are updated before SQL emission.
    """
    pay_by_stl = {p["settlement_id"]: p for p in payments}
    paid = [s for s in settlements if s["settlement_id"] in pay_by_stl]
    rng.shuffle(paid)

    for stl in paid[:3]:
        delta = Decimal(rng.choice(["10.00", "-10.00"]))
        stl["settlement_amount"] = stl["settlement_amount"] + delta
        pay_by_stl[stl["settlement_id"]]["payment_amount"] = (
            stl["settlement_amount"]
        )

    for stl in paid[3:6]:
        delta = Decimal(rng.choice(["5.00", "-5.00"]))
        pay = pay_by_stl[stl["settlement_id"]]
        pay["payment_amount"] = pay["payment_amount"] + delta


# ---------------------------------------------------------------------------
# External transactions (payments only)
# ---------------------------------------------------------------------------

def _generate_external_transactions(
    rng: random.Random,
    today: date,
    payments: list[dict],
) -> list[dict]:
    """Create external transactions with a realistic reconciliation mix.

    Emits three kinds of rows so every recon visual has data:

    * Balanced matches — most payments get linked to an ext txn whose
      amount equals the sum of its batch. Match status: *matched*.
    * Linked but off-by-a-bit — a handful of ext txns are linked to
      their payment batch but the ext amount deviates slightly. The
      recon view surfaces these as *not_yet_matched* / *late*.
    * Orphan unmatched ext txns — no payment references them at all.
      Populates the "Unmatched External Transactions" exceptions table
      and appears as *not_yet_matched*/*late* with zero internal total.
    * Unmatched payments — a few payments never receive an ext txn,
      powering the Payments "Show Only Unmatched Externally" toggle.
    """
    ext_txns: list[dict] = []
    ext_idx = 0
    systems = ["BankSync", "PaymentHub", "ClearSettle"]

    def _ext(
        system: str,
        amount: Decimal,
        txn_date: datetime,
        merchant_id: str,
        count: int,
    ) -> dict:
        nonlocal ext_idx
        ext_idx += 1
        txn = {
            "transaction_id": f"ext-{ext_idx:04d}",
            "external_system": system,
            "external_amount": Decimal(str(amount)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP),
            "record_count": count,
            "transaction_date": txn_date,
            "status": "processed",
            "merchant_id": merchant_id,
        }
        ext_txns.append(txn)
        return txn

    pool = list(payments)
    rng.shuffle(pool)

    # Reserve a handful of payments to stay internally-unmatched (no ext txn).
    reserved_unmatched = [pool.pop() for _ in range(min(4, len(pool)))]
    del reserved_unmatched  # kept only to exclude from the batching pool

    iteration = 0
    while pool:
        system = systems[iteration % len(systems)]
        pay = pool.pop(0)
        batch = [pay]
        mid = pay["merchant_id"]
        extras_wanted = rng.randint(0, 2)
        remaining = []
        for p in pool:
            if p["merchant_id"] == mid and extras_wanted > 0:
                batch.append(p)
                extras_wanted -= 1
            else:
                remaining.append(p)
        pool = remaining

        total = sum(p["payment_amount"] for p in batch)
        txn_date = max(p["payment_date"] for p in batch)

        # Every 6th batch drifts the ext amount so the recon view shows
        # a linked-but-not-balanced status alongside the matched rows.
        if iteration > 0 and iteration % 6 == 0:
            offset = Decimal(str(rng.uniform(5, 40))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            ext_amount = total + offset
        else:
            ext_amount = total
        ext = _ext(system, ext_amount, txn_date, mid, len(batch))
        for p in batch:
            p["ext_txn_id"] = ext["transaction_id"]
        iteration += 1

    # Orphan ext txns: no internal payment references them. Models
    # duplicate notifications, out-of-order arrivals, or erroneous posts.
    merchant_ids = [m[0] for m in MERCHANTS]
    for _ in range(8):
        _ext(
            rng.choice(systems),
            _amount(rng),
            _ts(today, rng.randint(0, 25), rng),
            rng.choice(merchant_ids),
            1,
        )
    for _ in range(5):
        _ext(
            rng.choice(systems),
            _amount(rng),
            _ts(today, rng.randint(35, 80), rng),
            rng.choice(merchant_ids),
            1,
        )

    return ext_txns
