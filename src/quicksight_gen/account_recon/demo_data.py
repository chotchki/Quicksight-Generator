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

import json
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
    # Names use em-dash separators only — no parentheses or commas (the
    # test fixtures parse SQL by simple regex/split and would mis-tokenize).
    ("gl-1850-sub-big-meadow-dairy-main",   "Big Meadow Dairy — Operating Main",      "gl-1850-cash-concentration-master"),
    ("gl-1850-sub-big-meadow-dairy-north",  "Big Meadow Dairy — Operating North",     "gl-1850-cash-concentration-master"),
    ("gl-1850-sub-cascade-timber-mill-a",   "Cascade Timber Mill — Operating Mill A", "gl-1850-cash-concentration-master"),
    ("gl-1850-sub-cascade-timber-mill-b",   "Cascade Timber Mill — Operating Mill B", "gl-1850-cash-concentration-master"),
    ("gl-1850-sub-pinecrest-vineyards",     "Pinecrest Vineyards LLC — Operating",    "gl-1850-cash-concentration-master"),
    ("gl-1850-sub-harvest-moon-bakery",     "Harvest Moon Bakery — Operating",        "gl-1850-cash-concentration-master"),
    #
    # External counterparty sub-pools — clearing/settlement or
    # inbound/outbound split per counterparty so cross-scope transfers
    # have realistic counter-leg targets.
    ("ext-frb-sub-inbound",                 "FRB Master — Inbound",                 "ext-frb-snb-master"),
    ("ext-frb-sub-outbound",                "FRB Master — Outbound",                "ext-frb-snb-master"),
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
# Ledger drift: stored ledger balance vs Σ sub-ledgers' stored balances
# + Σ direct ledger postings. Spread across the three ledgers most
# active in the demo (DDA Control gets customer activity; Cash
# Concentration Master gets ZBA sweeps; Cash & Due From FRB gets
# funding batches and cash sweeps).
_LEDGER_DRIFT_PLANT: list[tuple[str, int, str]] = [
    # (ledger_account_id, days_ago, delta as decimal string)
    ("gl-2010-dda-control",               3,  "125.00"),
    ("gl-1850-cash-concentration-master", 7,  "-80.50"),
    ("gl-1010-cash-due-frb",              14, "310.00"),
]

# Sub-ledger drift: stored sub-ledger balance vs Σ that sub-ledger's
# posted transactions. Mix of customer DDAs and a ZBA operating sub-
# account so both layers of the new structure surface in the drift view.
_SUBLEDGER_DRIFT_PLANT: list[tuple[str, int, str]] = [
    # (subledger_account_id, days_ago, delta as decimal string)
    ("cust-900-0001-bigfoot-brews",        5,  "200.00"),
    ("cust-700-0001-big-meadow-dairy",     2,  "-75.00"),
    ("gl-1850-sub-big-meadow-dairy-main",  10, "-150.50"),
    ("cust-800-0001-cascade-timber-mill",  20, "450.00"),
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
# In the new SNB model, customer DDAs sit under DDA Control and inherit
# its per-transfer-type daily limits. ZBA sub-accounts under Cash
# Concentration Master have no enforced limits (sweeps are uncapped in
# normal operation). GL control accounts without sub-ledgers (suspense,
# settlement) carry no limits — they're hit by direct ledger postings
# governed by other controls.
#
# Absence of a row means "no limit enforced" (e.g., DDA Control ×
# internal carries no limit so on-us transfer plants don't accidentally
# breach). External ledgers have no rows — their sub-pools are filtered
# out of the limit check (outbound view: internal only).
_LEDGER_LIMITS: list[tuple[str, str, str]] = [
    # (ledger_account_id, transfer_type, daily_limit)
    ("gl-2010-dda-control", "ach",  "12000.00"),
    ("gl-2010-dda-control", "wire", "15000.00"),
    ("gl-2010-dda-control", "cash", "10000.00"),
]


# Limit breach plants: one extra outbound transfer per (sub-ledger, day,
# type). Each plant amount is chosen to exceed the corresponding
# ledger-limit entry so the breach view reliably surfaces the cell.
# Disjoint from _SUBLEDGER_DRIFT_PLANT (different cells) — each exception
# table surfaces a different set of rows.
_LIMIT_BREACH_PLANT: list[tuple[str, int, str, str, str]] = [
    # (subledger_account_id, days_ago, transfer_type, debit_amount, memo)
    ("cust-900-0001-bigfoot-brews",       8,  "wire", "22000.00", "Bulk wire payout to roaster supplier"),
    ("cust-800-0002-pinecrest-vineyards", 12, "ach",  "16000.00", "Oversize ACH batch — bottling supplies"),
    ("cust-700-0001-big-meadow-dairy",    18, "cash", "13000.00", "Large cash disbursement — feed lot payment"),
]


# Overdraft plants: one extra outbound transfer per (sub-ledger, day)
# that drives the sub-ledger's running balance negative. The overdraft
# view picks up every day where stored balance < 0 — after the plant,
# the sub-ledger may stay negative for several days until a compensating
# credit is emitted, which is the realistic operational shape for a
# short-lived overdraft. Disjoint from drift and breach plant cells.
_OVERDRAFT_PLANT: list[tuple[str, int, str, str]] = [
    # (subledger_account_id, days_ago, debit_amount, memo)
    # Amounts are sized large enough to drive the planted sub-ledger's
    # running balance below zero given its prior day's stored balance —
    # otherwise the overdraft check has nothing to surface.
    ("cust-900-0002-sasquatch-sips",      6, "45000.00", "Emergency outbound — covered next day"),
    ("cust-700-0002-harvest-moon-bakery", 4, "40000.00", "Overnight sweep reversal pending"),
    ("gl-1850-sub-cascade-timber-mill-a", 9, "35000.00", "Equipment purchase — funding pending"),
]


# External sub-ledger accounts used as counter-legs for planted breach/
# overdraft transfers. The counter-leg doesn't affect any tracked balance.
_EXTERNAL_COUNTER_LEG_POOL: list[str] = [
    "ext-valley-grain-sub-clearing",
    "ext-valley-grain-sub-settlement",
    "ext-harvest-credit-sub-inbound",
    "ext-harvest-credit-sub-outbound",
]


# ---------------------------------------------------------------------------
# Telling-transfer scenarios (Phase F.4) — see docs/Training_Story.md
# ---------------------------------------------------------------------------

# F.4.1: ZBA / Cash Concentration sweep cycle.
#
# Operating sub-accounts under Cash Concentration Master sweep their EOD
# running balance to the master ledger daily — operating ends day at
# zero. The training story uses Big Meadow Dairy as the canonical
# example (multiple operating locations sweep to one master).
_ZBA_SWEEP_CUSTOMERS: list[str] = [
    "gl-1850-sub-big-meadow-dairy-main",
    "gl-1850-sub-big-meadow-dairy-north",
]

# Cells where the daily sweep is intentionally skipped — the operating
# sub-account ends day non-zero, surfaced by F.5.1 "Sweep target
# non-zero EOD". Days_ago picked to land on different aging buckets.
# Each plant pairs with a guaranteed deposit (see _ZBA_SWEEP_PLANT_AMOUNT)
# so the EOD balance is reliably non-zero regardless of whether existing
# random activity touched the cell that day.
_ZBA_SWEEP_FAIL_PLANT: list[tuple[str, int]] = [
    # (subledger_account_id, days_ago)
    ("gl-1850-sub-big-meadow-dairy-main",  3),   # bucket 2 (2-3 days)
    ("gl-1850-sub-big-meadow-dairy-north", 14),  # bucket 4 (8-30 days)
]

_ZBA_SWEEP_PLANT_AMOUNT = Decimal("875.00")


# F.5.2: Sweep leg mismatch plants. On these (sub_id, days_ago) cells the
# sweep is emitted normally on the sub-ledger side, but the offsetting
# Cash Concentration Master ledger-direct posting is short (or long) by
# ``master_delta``. The transfer ends non-zero (also surfaces in the
# existing non-zero-transfer check) AND the daily sweep aggregate at the
# Master ledger drifts away from the sub-account aggregate — that's what
# F.5.2 surfaces as concentration master vs sub-account sweep drift.
# Mixed signs so the timeline shows both upward and downward spikes.
_ZBA_SWEEP_LEG_MISMATCH_PLANT: list[tuple[str, int, str]] = [
    # (subledger_account_id, days_ago, master_leg_delta)
    # Both sub-accounts must appear in _ZBA_SWEEP_CUSTOMERS so the sweep
    # is actually emitted; days_ago must be disjoint from F.5.1 fail-plant
    # cells (otherwise no sweep posts at all).
    ("gl-1850-sub-big-meadow-dairy-main",  6,  "120.00"),   # master long
    ("gl-1850-sub-big-meadow-dairy-north", 11, "-95.50"),   # master short
]


# F.4.2: ACH origination sweep cycle.
#
# Each business day, customers initiate ACH originations — debits land
# on ACH Origination Settlement (gl-1810), credits on the customer DDA.
# At EOD the day's net is swept to Cash & Due From FRB (gl-1010),
# zeroing 1810. A Fed-side confirmation (external_force_posted) attests
# the FRB master account moved by the same amount.
_ACH_ORIG_DAYS = 14
_ACH_ORIG_CUSTOMERS: list[str] = [
    "cust-900-0001-bigfoot-brews",
    "cust-900-0002-sasquatch-sips",
    "cust-900-0003-yeti-espresso",
    "cust-800-0001-cascade-timber-mill",
    "cust-800-0002-pinecrest-vineyards",
    "cust-700-0001-big-meadow-dairy",
    "cust-700-0002-harvest-moon-bakery",
]
_ACH_ORIG_AMOUNTS = [
    Decimal("450.00"), Decimal("1280.00"), Decimal("675.00"),
    Decimal("2100.00"), Decimal("890.00"),
]

# Days where the EOD sweep is intentionally skipped — gl-1810 ends day
# non-zero. Drives F.5.3 "ACH Origination Settlement non-zero EOD".
_ACH_SWEEP_SKIP_PLANT: list[int] = [4]   # bucket 3 (4-7 days)

# Days where the EOD sweep posts but the Fed confirmation never lands.
# Drives F.5.4 "Internal sweep posted but no Fed confirmation".
_ACH_FED_CONFIRMATION_MISSING: list[int] = [
    8,    # bucket 4 (8-30 days)
    12,   # bucket 4 (8-30 days)
]

_ACH_ORIG_LEDGER = "gl-1810-ach-orig-settlement"
_FRB_CASH_LEDGER = "gl-1010-cash-due-frb"
_FRB_EXT_LEDGER = "ext-frb-snb-master"
_FRB_SUB_OUTBOUND = "ext-frb-sub-outbound"
_FRB_SUB_INBOUND = "ext-frb-sub-inbound"


# F.4.3: External force-posted card settlement.
#
# Payment Gateway Processor settles a day's card sales into a merchant's
# DDA via the Fed master account. The Fed posts first; SNB's books
# follow with a force-posted internal entry. Two transfers per
# settlement event:
#  - Fed-side observation (parent): 2-leg external (DR processor
#    clearing, CR FRB inbound). origin='external_force_posted'. No
#    internal balance impact — this is SNB observing the Fed posting.
#  - SNB internal catch-up (child, parent=Fed observation): mixed-level
#    (DR gl-1815 ledger-direct, CR merchant DDA sub-ledger).
#    origin='external_force_posted' (triggered externally).
_CARD_SETTLEMENT_DAYS = 10
_CARD_SETTLEMENT_MERCHANTS: list[str] = [
    "cust-900-0001-bigfoot-brews",
    "cust-900-0002-sasquatch-sips",
    "cust-900-0003-yeti-espresso",
]
_CARD_SETTLEMENT_AMOUNTS = [
    Decimal("4200.00"), Decimal("3650.00"), Decimal("5180.00"),
    Decimal("2890.00"), Decimal("4475.00"),
]

# Days where Fed posted but SNB internal catch-up never landed —
# drives the F.5.X "Fed activity with no matching internal post" check.
_CARD_INTERNAL_MISSING_PLANT: list[int] = [
    4,    # bucket 3 (4-7 days)
    9,    # bucket 4 (8-30 days)
]

_CARD_ACQUIRING_LEDGER = "gl-1815-card-acquiring-settlement"
_PROCESSOR_EXT_LEDGER = "ext-payment-gateway-processor"
_PROCESSOR_SUB_CLEARING = "ext-payment-gateway-sub-clearing"


# F.4.4: On-Us Internal Transfer with fail / reversal.
#
# Originator initiates a transfer to a recipient (both SNB customers).
# Each event has up to two transfers: Step 1 originate (DR ``gl-1830``
# Internal Transfer Suspense ledger-direct, CR originator DDA
# sub-ledger). Step 2 either settles to recipient (DR recipient DDA
# sub-ledger, CR ``gl-1830`` ledger-direct) or reverses to the
# originator (DR originator DDA sub-ledger, CR ``gl-1830``).
#
# Plant kinds:
# - ``success``: both steps post; suspense nets to zero, money lands at
#   recipient.
# - ``stuck``: only Step 1 posts; no Step 2 — suspense holds non-zero
#   EOD (F.5.X "Stuck in Internal Transfer Suspense").
# - ``reversed_not_credited``: Step 2 reversal has the originator's
#   credit-back leg failed but the suspense leg posted — suspense
#   clears but originator never recovers their money (F.5.X
#   "Reversed-but-not-credited / double spend").
_INTERNAL_TRANSFER_PLANT: list[tuple[str, str, int, str, str]] = [
    # (originator_id, recipient_id, days_ago, plant_kind, amount_str)
    ("cust-700-0001-big-meadow-dairy",     "cust-800-0001-cascade-timber-mill",  2,  "success",                "3500.00"),
    ("cust-700-0002-harvest-moon-bakery",  "cust-800-0002-pinecrest-vineyards",  6,  "success",                "1250.00"),
    ("cust-800-0001-cascade-timber-mill",  "cust-700-0001-big-meadow-dairy",     11, "stuck",                  "4275.00"),
    ("cust-800-0002-pinecrest-vineyards",  "cust-700-0002-harvest-moon-bakery",  23, "stuck",                  "1880.00"),
    ("cust-700-0001-big-meadow-dairy",     "cust-800-0002-pinecrest-vineyards",  17, "reversed_not_credited",  "2940.00"),
]

_INTERNAL_TRANSFER_SUSPENSE_LEDGER = "gl-1830-internal-transfer-suspense"


# ---------------------------------------------------------------------------
# Phase G: shared-base-table denormalization
# ---------------------------------------------------------------------------

# account_type per G.0.12: role only, structural level derives from
# control_account_id IS NULL.  See docs/Schema_v3.md for the canonical
# value list.
LEDGER_ACCOUNT_TYPES: dict[str, str] = {
    "gl-1010-cash-due-frb":               "gl_control",
    "gl-1810-ach-orig-settlement":        "gl_control",
    "gl-1815-card-acquiring-settlement":  "gl_control",
    "gl-1820-wire-settlement-suspense":   "gl_control",
    "gl-1830-internal-transfer-suspense": "gl_control",
    "gl-1850-cash-concentration-master":  "concentration_master",
    "gl-1899-internal-suspense-recon":    "gl_control",
    "gl-2010-dda-control":                "gl_control",
    "ext-frb-snb-master":                 "external_counter",
    "ext-payment-gateway-processor":      "external_counter",
    "ext-coffee-shop-supply-co":          "external_counter",
    "ext-valley-grain-coop":              "external_counter",
    "ext-harvest-credit-exchange":        "external_counter",
}


def _subledger_account_type(sub_id: str) -> str:
    # cust-900-* are the three coffee retailers shared with PR; they
    # carry the merchant role from AR's perspective too.
    if sub_id.startswith("cust-900-"):
        return "merchant_dda"
    if sub_id.startswith("cust-"):
        return "dda"
    if sub_id.startswith("gl-1850-sub-"):
        return "concentration_master"
    if sub_id.startswith("ext-"):
        return "external_counter"
    raise KeyError(f"No account_type rule for sub-ledger {sub_id!r}")


def _provenance_source(transfer_type: str, origin: str) -> str:
    if transfer_type == "clearing_sweep":
        return "sweep_engine"
    if origin == "external_force_posted":
        return "manual_force_post"
    return "core_banking"


def _json_metadata(payload: dict) -> str:
    # sort_keys for deterministic output across runs.
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _ledger_limits_payload(ledger_id: str) -> dict[str, float]:
    # Per G.0.4 Locked: limits live in daily_balances.metadata on the
    # ledger row.  Float so JSON serializes without quotes (the consumer
    # uses JSON_VALUE(... AS NUMERIC)).
    return {
        xtype: float(Decimal(amt))
        for lid, xtype, amt in _LEDGER_LIMITS
        if lid == ledger_id
    }


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

    # 1. Funding batches — credit to ledger, debits to sub-ledgers.
    # Only eligible for internal ledgers that actually have sub-ledgers
    # (DDA Control, Cash Concentration Master in the SNB structure).
    # Pure-control ledgers (suspense/settlement) get no funding batches.
    funding_eligible_ledgers = [
        lid for lid in internal_ledgers
        if internal_subledgers_by_ledger.get(lid)
    ]
    for i in range(_FUNDING_BATCH_COUNT):
        ledger_id = rng.choice(funding_eligible_ledgers)
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
        # Distribute debits across sub-ledgers using a random
        # proportional split. Every sub-ledger gets a non-zero share
        # (the prior cumulative-min approach could exhaust `remaining`
        # before the last sub-ledgers, leaving them with $0 legs which
        # tripped posting_fields_populated).
        weights = [rng.uniform(0.1, 1.0) for _ in subs]
        total_w = sum(weights)
        shares: list[Decimal] = [
            (total * Decimal(str(w / total_w))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            )
            for w in weights[:-1]
        ]
        shares.append(total - sum(shares, Decimal("0")))  # last absorbs rounding
        for sub_id, share in zip(subs, shares):
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
# Telling-transfer generators (Phase F.4)
# ---------------------------------------------------------------------------

_CASH_CONCENTRATION_MASTER_LEDGER = "gl-1850-cash-concentration-master"


def _subledger_name(sub_id: str) -> str:
    for sid, name, _ in SUBLEDGER_ACCOUNTS:
        if sid == sub_id:
            return name
    raise KeyError(sub_id)


def _generate_ach_origination_cycle(
    today: date,
) -> tuple[list[dict], list[tuple], list[tuple]]:
    """Generate the ACH origination → EOD sweep → Fed confirmation cycle.

    Daily for ``_ACH_ORIG_DAYS`` business days:
    - 3 customers each emit one ACH origination — DR ``gl-1810`` ledger-
      direct, CR customer DDA sub-ledger. Per-day customer set + amount
      rotate deterministically through the pools.
    - EOD (18:30): the day's net debit on ``gl-1810`` is swept to
      ``gl-1010`` by a 2-leg ledger-only ``clearing_sweep`` transfer,
      zeroing 1810.
    - EOD+1m (18:31): a Fed-side confirmation (``external_force_posted``,
      parent = sweep transfer) attests the same amount cleared the FRB
      master account. Realized as 2 external sub-ledger legs (outbound /
      inbound) so it nets to zero without touching internal balances.

    Plants:
    - Days in ``_ACH_SWEEP_SKIP_PLANT`` skip both the EOD sweep and the
      Fed confirmation — ``gl-1810`` ends day non-zero (F.5.3 surfaces).
    - Days in ``_ACH_FED_CONFIRMATION_MISSING`` post the EOD sweep but
      omit the Fed confirmation — internal sweep with no Fed-side
      attestation (F.5.4 surfaces).

    Returns ``(extra_transactions, extra_postings, extra_transfer_rows)``.
    Customer DDA legs flow through ``transactions`` (so daily balances
    pick them up via the existing path); ledger-direct + Fed external
    legs are crafted directly into ``posting_rows``; EOD-sweep and Fed-
    confirmation transfer rows are crafted into ``transfer_rows`` (no
    sub-ledger leg to derive from).
    """
    extra_transactions: list[dict] = []
    extra_postings: list[tuple] = []
    extra_transfer_rows: list[tuple] = []

    skip_set = set(_ACH_SWEEP_SKIP_PLANT)
    miss_fed_set = set(_ACH_FED_CONFIRMATION_MISSING)

    for day_idx in range(_ACH_ORIG_DAYS):
        days_ago = day_idx + 1
        bdate = today - timedelta(days=days_ago)
        customers_today = [
            _ACH_ORIG_CUSTOMERS[(day_idx + k) % len(_ACH_ORIG_CUSTOMERS)]
            for k in range(3)
        ]
        day_total = Decimal("0.00")
        for orig_idx, cust_id in enumerate(customers_today):
            amount = _ACH_ORIG_AMOUNTS[
                (day_idx + orig_idx) % len(_ACH_ORIG_AMOUNTS)
            ]
            ts = datetime(bdate.year, bdate.month, bdate.day,
                          10 + orig_idx, 15, 0)
            tid = f"ar-ach-orig-{day_idx + 1:02d}-{orig_idx + 1}"

            extra_transactions.append({
                "transaction_id": f"ar-ach-cust-{day_idx + 1:02d}-{orig_idx + 1}",
                "subledger_account_id": cust_id,
                "transfer_id": tid,
                "amount": -amount,
                "posted_at": ts,
                "status": "posted",
                "transfer_type": "ach",
                "origin": "internal_initiated",
                "memo": "ACH origination — supplier payment",
            })
            extra_postings.append((
                f"ar-ach-ledger-{day_idx + 1:02d}-{orig_idx + 1}",
                tid, _ACH_ORIG_LEDGER, None,
                amount, ts, "success",
            ))
            day_total += amount

        if days_ago in skip_set:
            continue

        sweep_ts = datetime(bdate.year, bdate.month, bdate.day, 18, 30, 0)
        sweep_tid = f"ar-ach-sweep-{day_idx + 1:02d}"
        extra_transfer_rows.append((
            sweep_tid, None, "clearing_sweep", "internal_initiated",
            day_total, "posted", sweep_ts,
            "ACH net settlement to FRB Master",
        ))
        extra_postings.append((
            f"ar-ach-sweep-cash-{day_idx + 1:02d}",
            sweep_tid, _FRB_CASH_LEDGER, None,
            day_total, sweep_ts, "success",
        ))
        extra_postings.append((
            f"ar-ach-sweep-orig-{day_idx + 1:02d}",
            sweep_tid, _ACH_ORIG_LEDGER, None,
            -day_total, sweep_ts, "success",
        ))

        if days_ago in miss_fed_set:
            continue

        fed_ts = datetime(bdate.year, bdate.month, bdate.day, 18, 31, 0)
        fed_tid = f"ar-ach-fed-{day_idx + 1:02d}"
        extra_transfer_rows.append((
            fed_tid, sweep_tid, "ach", "external_force_posted",
            day_total, "posted", fed_ts,
            "FRB confirmation — ACH net settlement",
        ))
        extra_postings.append((
            f"ar-ach-fed-out-{day_idx + 1:02d}",
            fed_tid, _FRB_EXT_LEDGER, _FRB_SUB_OUTBOUND,
            day_total, fed_ts, "success",
        ))
        extra_postings.append((
            f"ar-ach-fed-in-{day_idx + 1:02d}",
            fed_tid, _FRB_EXT_LEDGER, _FRB_SUB_INBOUND,
            -day_total, fed_ts, "success",
        ))

    return extra_transactions, extra_postings, extra_transfer_rows


def _generate_card_settlement_cycle(
    today: date,
) -> tuple[list[dict], list[tuple], list[tuple], dict[str, str]]:
    """Generate Fed-side card settlement + SNB internal catch-up cycle.

    Per day for ``_CARD_SETTLEMENT_DAYS`` business days, one merchant
    rotates through the pool. Two transfers per settlement event:

    - Fed observation (parent, no parent_transfer_id): 2-leg external
      transfer DR ``ext-payment-gateway-sub-clearing``,
      CR ``ext-frb-sub-inbound``. ``origin='external_force_posted'``.
      No internal balance impact — SNB observing the Fed's posting.
    - SNB internal catch-up (child, parent = Fed observation): 2-leg
      mixed-level DR ``gl-1815`` ledger-direct, CR merchant DDA
      sub-ledger. ``origin='external_force_posted'``.

    Plants:
    - Days in ``_CARD_INTERNAL_MISSING_PLANT`` skip the SNB catch-up
      entirely — Fed observation has no child, drives the F.5.X "Fed
      activity with no matching internal post" check.

    Returns ``(extra_transactions, extra_postings, extra_transfer_rows,
    parent_map)``. The catch-up's customer DDA leg flows through
    ``transactions`` (so daily DDA balances pick up the credit and
    ``_derive_unified_tables`` synthesizes the catch-up transfer row);
    its ``gl-1815`` ledger-direct leg + both Fed-side legs feed
    ``extra_postings``; only the Fed observation transfer rows feed
    ``extra_transfer_rows`` directly. ``parent_map`` carries the
    catch-up → Fed parent linkage for the derive step.
    """
    extra_transactions: list[dict] = []
    extra_postings: list[tuple] = []
    extra_transfer_rows: list[tuple] = []
    parent_map: dict[str, str] = {}

    miss_internal_set = set(_CARD_INTERNAL_MISSING_PLANT)

    for day_idx in range(_CARD_SETTLEMENT_DAYS):
        days_ago = day_idx + 1
        bdate = today - timedelta(days=days_ago)
        merchant_id = _CARD_SETTLEMENT_MERCHANTS[
            day_idx % len(_CARD_SETTLEMENT_MERCHANTS)
        ]
        amount = _CARD_SETTLEMENT_AMOUNTS[
            day_idx % len(_CARD_SETTLEMENT_AMOUNTS)
        ]

        fed_ts = datetime(bdate.year, bdate.month, bdate.day, 9, 0, 0)
        fed_tid = f"ar-card-fed-{day_idx + 1:02d}"
        extra_transfer_rows.append((
            fed_tid, None, "ach", "external_force_posted",
            amount, "posted", fed_ts,
            "Card processor settlement — Fed posting",
        ))
        extra_postings.append((
            f"ar-card-fed-out-{day_idx + 1:02d}",
            fed_tid, _PROCESSOR_EXT_LEDGER, _PROCESSOR_SUB_CLEARING,
            amount, fed_ts, "success",
        ))
        extra_postings.append((
            f"ar-card-fed-in-{day_idx + 1:02d}",
            fed_tid, _FRB_EXT_LEDGER, _FRB_SUB_INBOUND,
            -amount, fed_ts, "success",
        ))

        if days_ago in miss_internal_set:
            continue

        catchup_ts = datetime(bdate.year, bdate.month, bdate.day, 11, 30, 0)
        catchup_tid = f"ar-card-internal-{day_idx + 1:02d}"
        parent_map[catchup_tid] = fed_tid

        extra_postings.append((
            f"ar-card-internal-ledger-{day_idx + 1:02d}",
            catchup_tid, _CARD_ACQUIRING_LEDGER, None,
            amount, catchup_ts, "success",
        ))
        extra_transactions.append({
            "transaction_id": f"ar-card-cust-{day_idx + 1:02d}",
            "subledger_account_id": merchant_id,
            "transfer_id": catchup_tid,
            "amount": -amount,
            "posted_at": catchup_ts,
            "status": "posted",
            "transfer_type": "ach",
            "origin": "external_force_posted",
            "memo": "Card settlement — internal catch-up",
        })

    return extra_transactions, extra_postings, extra_transfer_rows, parent_map


def _generate_internal_transfer_cycle(
    today: date,
) -> tuple[list[dict], list[tuple], dict[str, str]]:
    """Generate on-us internal transfer originate / settle / reverse cycle.

    For each row in ``_INTERNAL_TRANSFER_PLANT`` emit Step 1 (originate)
    and, depending on plant kind, Step 2 (settle, or reversal-not-
    credited, or no Step 2 at all for ``stuck``):

    - Step 1 originate: DR ``gl-1830`` ledger-direct +amt, CR originator
      DDA sub-ledger -amt. Both legs posted.
    - Step 2 settle (success): DR recipient DDA sub-ledger +amt, CR
      ``gl-1830`` ledger-direct -amt. Both legs posted. parent = Step 1.
    - Step 2 reversal-not-credited: DR originator DDA sub-ledger +amt
      with status='failed', CR ``gl-1830`` ledger-direct -amt with
      status='posted'. Suspense clears but originator never recovers.

    All sub-ledger legs flow through ``transactions`` (so daily
    balances and transfer derivation pick them up); ledger-direct
    suspense legs feed ``extra_postings``. Step-2 transfers chain to
    Step 1 via the returned ``parent_map``.

    Returns ``(extra_transactions, extra_postings, parent_map)``. No
    ``extra_transfer_rows`` — every transfer here has a sub-ledger leg
    in ``transactions``, so it is created by ``_derive_unified_tables``.
    """
    extra_transactions: list[dict] = []
    extra_postings: list[tuple] = []
    parent_map: dict[str, str] = {}

    for plant_idx, (originator, recipient, days_ago, kind, amount_str) in enumerate(
        _INTERNAL_TRANSFER_PLANT, 1,
    ):
        amount = Decimal(amount_str)
        bdate = today - timedelta(days=days_ago)
        orig_ts = datetime(bdate.year, bdate.month, bdate.day, 9, 30, 0)
        step2_ts = datetime(bdate.year, bdate.month, bdate.day, 14, 45, 0)

        orig_tid = f"ar-on-us-orig-{plant_idx:02d}"
        # Step 1 originate — customer leg through transactions
        extra_transactions.append({
            "transaction_id": f"ar-on-us-orig-cust-{plant_idx:02d}",
            "subledger_account_id": originator,
            "transfer_id": orig_tid,
            "amount": -amount,
            "posted_at": orig_ts,
            "status": "posted",
            "transfer_type": "internal",
            "origin": "internal_initiated",
            "memo": "On-us transfer — originate",
        })
        extra_postings.append((
            f"ar-on-us-orig-susp-{plant_idx:02d}",
            orig_tid, _INTERNAL_TRANSFER_SUSPENSE_LEDGER, None,
            amount, orig_ts, "success",
        ))

        if kind == "stuck":
            continue

        step2_tid = f"ar-on-us-step2-{plant_idx:02d}"
        parent_map[step2_tid] = orig_tid

        if kind == "success":
            extra_transactions.append({
                "transaction_id": f"ar-on-us-step2-cust-{plant_idx:02d}",
                "subledger_account_id": recipient,
                "transfer_id": step2_tid,
                "amount": amount,
                "posted_at": step2_ts,
                "status": "posted",
                "transfer_type": "internal",
                "origin": "internal_initiated",
                "memo": "On-us transfer — settle to recipient",
            })
            extra_postings.append((
                f"ar-on-us-step2-susp-{plant_idx:02d}",
                step2_tid, _INTERNAL_TRANSFER_SUSPENSE_LEDGER, None,
                -amount, step2_ts, "success",
            ))
        elif kind == "reversed_not_credited":
            # Originator credit-back leg fails (status='failed' in
            # transactions → 'failed' in posting); suspense leg still
            # posts (success). Net effect: customer stays out, suspense
            # clears anyway — the F.5.X "double spend" pattern.
            extra_transactions.append({
                "transaction_id": f"ar-on-us-step2-cust-{plant_idx:02d}",
                "subledger_account_id": originator,
                "transfer_id": step2_tid,
                "amount": amount,
                "posted_at": step2_ts,
                "status": "failed",
                "transfer_type": "internal",
                "origin": "internal_initiated",
                "memo": "On-us transfer — reversal credit-back FAILED",
            })
            extra_postings.append((
                f"ar-on-us-step2-susp-{plant_idx:02d}",
                step2_tid, _INTERNAL_TRANSFER_SUSPENSE_LEDGER, None,
                -amount, step2_ts, "success",
            ))
        else:
            raise ValueError(f"Unknown plant kind: {kind}")

    return extra_transactions, extra_postings, parent_map


def _generate_zba_sweeps(
    today: date,
    transactions: list[dict],
) -> tuple[list[dict], list[tuple]]:
    """Generate ZBA / Cash Concentration EOD sweep cycles.

    Each operating sub-account in ``_ZBA_SWEEP_CUSTOMERS`` sweeps its
    EOD running balance to the Cash Concentration Master ledger daily.
    The sub-ledger leg is appended to the ``transactions`` stream (so
    the existing daily balance computation picks it up); the offsetting
    ledger-direct posting is returned separately to be appended to
    posting_rows after ``_derive_unified_tables`` runs.

    Failure plants from ``_ZBA_SWEEP_FAIL_PLANT`` are realized in two
    steps: a guaranteed deposit lands on the plant cell first, then the
    sweep is intentionally skipped that day — so the operating
    sub-account's stored balance ends non-zero. F.5.1 surfaces these.

    Returns ``(extra_transactions, ledger_direct_postings)``.
    """
    fail_set = {(sid, da) for sid, da in _ZBA_SWEEP_FAIL_PLANT}
    mismatch_map = {
        (sid, da): Decimal(delta_str)
        for sid, da, delta_str in _ZBA_SWEEP_LEG_MISMATCH_PLANT
    }
    extra_transactions: list[dict] = []
    extra_postings: list[tuple] = []

    # ---- Step 0: plant guaranteed deposits on mismatch-plant days so a
    # sweep is reliably emitted (otherwise random activity may leave
    # ``running == 0`` and the sweep would be skipped, defeating the
    # mismatch plant). The mismatch is applied to the master leg of that
    # day's sweep in step 2.
    for plant_idx, (sub_id, days_ago, _delta) in enumerate(
        _ZBA_SWEEP_LEG_MISMATCH_PLANT, 1,
    ):
        plant_day = today - timedelta(days=days_ago)
        plant_time = datetime(plant_day.year, plant_day.month, plant_day.day,
                              13, 0, plant_idx)
        external_leg = _EXTERNAL_COUNTER_LEG_POOL[
            plant_idx % len(_EXTERNAL_COUNTER_LEG_POOL)
        ]
        tid = f"ar-zba-mismatch-deposit-{plant_idx:02d}"
        extra_transactions.append({
            "transaction_id": f"ar-zba-mismatch-{plant_idx:03d}-a",
            "subledger_account_id": sub_id,
            "transfer_id": tid,
            "amount": _ZBA_SWEEP_PLANT_AMOUNT,
            "posted_at": plant_time,
            "status": "posted",
            "transfer_type": "internal",
            "origin": "internal_initiated",
            "memo": "ZBA deposit (mismatch plant)",
        })
        extra_transactions.append({
            "transaction_id": f"ar-zba-mismatch-{plant_idx:03d}-b",
            "subledger_account_id": external_leg,
            "transfer_id": tid,
            "amount": -_ZBA_SWEEP_PLANT_AMOUNT,
            "posted_at": plant_time,
            "status": "posted",
            "transfer_type": "internal",
            "origin": "internal_initiated",
            "memo": "ZBA deposit (mismatch plant)",
        })

    # ---- Step 1: plant guaranteed deposits on fail-plant days ----
    # These are 2-leg cross-scope transfers (operating sub-account
    # debit + external counter-leg credit). Since the sweep is skipped
    # on these days, the deposits persist to EOD as non-zero balance.
    for plant_idx, (sub_id, days_ago) in enumerate(_ZBA_SWEEP_FAIL_PLANT, 1):
        plant_day = today - timedelta(days=days_ago)
        plant_time = datetime(plant_day.year, plant_day.month, plant_day.day,
                              14, 30, plant_idx)
        external_leg = _EXTERNAL_COUNTER_LEG_POOL[
            plant_idx % len(_EXTERNAL_COUNTER_LEG_POOL)
        ]
        tid = f"ar-zba-fail-{plant_idx:02d}"
        extra_transactions.append({
            "transaction_id": f"ar-zba-fail-{plant_idx:03d}-a",
            "subledger_account_id": sub_id,
            "transfer_id": tid,
            "amount": _ZBA_SWEEP_PLANT_AMOUNT,
            "posted_at": plant_time,
            "status": "posted",
            "transfer_type": "internal",
            "origin": "internal_initiated",
            "memo": "ZBA deposit pending sweep",
        })
        extra_transactions.append({
            "transaction_id": f"ar-zba-fail-{plant_idx:03d}-b",
            "subledger_account_id": external_leg,
            "transfer_id": tid,
            "amount": -_ZBA_SWEEP_PLANT_AMOUNT,
            "posted_at": plant_time,
            "status": "posted",
            "transfer_type": "internal",
            "origin": "internal_initiated",
            "memo": "ZBA deposit pending sweep",
        })

    # ---- Step 2: emit a sweep on every (sub, day) where the post-plant
    # running balance is non-zero, except fail-plant cells which are
    # intentionally skipped.
    all_txns = transactions + extra_transactions
    sweep_idx = 0
    for sub_id in _ZBA_SWEEP_CUSTOMERS:
        running = Decimal("0.00")
        for days_ago in range(_DAYS_OF_HISTORY, -1, -1):
            bdate = today - timedelta(days=days_ago)
            for t in all_txns:
                if (
                    t["status"] == "posted"
                    and t["subledger_account_id"] == sub_id
                    and t["posted_at"].date() == bdate
                ):
                    running += t["amount"]
            if (sub_id, days_ago) in fail_set:
                continue  # sweep skipped — balance persists non-zero
            if running == 0:
                continue  # nothing to sweep
            sweep_idx += 1
            sweep_amount = running
            master_delta = mismatch_map.get((sub_id, days_ago), Decimal("0"))
            master_amount = sweep_amount + master_delta
            sweep_time = datetime(bdate.year, bdate.month, bdate.day,
                                  18, 0, 0)
            tid = f"ar-zba-sweep-{sweep_idx:04d}"
            memo = f"ZBA EOD sweep — {_subledger_name(sub_id)}"
            if master_delta != 0:
                memo = (
                    f"{memo} (master leg keyed off by "
                    f"{master_delta:+,.2f})"
                )
            extra_transactions.append({
                "transaction_id": f"ar-zba-sub-{sweep_idx:05d}",
                "subledger_account_id": sub_id,
                "transfer_id": tid,
                "amount": -sweep_amount,
                "posted_at": sweep_time,
                "status": "posted",
                "transfer_type": "clearing_sweep",
                "origin": "internal_initiated",
                "memo": memo,
            })
            extra_postings.append((
                f"ar-zba-direct-{sweep_idx:05d}",
                tid,
                _CASH_CONCENTRATION_MASTER_LEDGER,
                None,
                master_amount,
                sweep_time,
                "success",
            ))
            running = Decimal("0.00")

    return extra_transactions, extra_postings


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def _derive_unified_tables(
    transactions: list[dict],
    parent_map: dict[str, str] | None = None,
) -> tuple[list[tuple], list[tuple]]:
    """Derive unified ``transfer`` + ``posting`` rows from AR transactions.

    Groups transactions by transfer_id to produce one transfer row per
    group. Each transaction maps to one posting row. ``parent_map``
    optionally supplies parent_transfer_id values for transfers that
    chain (e.g., F.4.3 force-posted catch-ups linking to their Fed
    observation parent); transfers absent from the map get NULL parent.
    """
    from collections import OrderedDict

    by_transfer: OrderedDict[str, list[dict]] = OrderedDict()
    for t in transactions:
        by_transfer.setdefault(t["transfer_id"], []).append(t)

    subledger_to_ledger = {sid: lid for sid, _n, lid in SUBLEDGER_ACCOUNTS}
    parent_map = parent_map or {}

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
            parent_map.get(tid),  # NULL unless an explicit parent was supplied
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


def _derive_shared_base_tables(
    transfer_rows: list[tuple],
    posting_rows: list[tuple],
    subledger_balances: list[dict],
    ledger_balances: list[dict],
) -> tuple[list[tuple], list[tuple]]:
    """Phase G dual-write: derive `transactions` + `daily_balances` rows.

    Account name / type / control-account are denormalized onto every
    row so a single SELECT serves common queries without joins.  Source
    provenance lands in `metadata.source` everywhere; ledger-row limits
    pack into `metadata.limits` per G.0.4.
    """
    ledger_lookup = {
        lid: (name, is_internal, LEDGER_ACCOUNT_TYPES[lid])
        for lid, name, is_internal in LEDGER_ACCOUNTS
    }
    subledger_lookup = {
        sid: (name, lid)
        for sid, name, lid in SUBLEDGER_ACCOUNTS
    }
    transfer_lookup = {row[0]: row for row in transfer_rows}

    transactions_rows: list[tuple] = []
    for row in posting_rows:
        (posting_id, transfer_id, ledger_id, sub_id,
         signed_amount, posted_at, status) = row
        xfer = transfer_lookup[transfer_id]
        (_tid, parent_tid, transfer_type, origin,
         _amount, _xfer_status, _xfer_posted, memo) = xfer

        if sub_id is not None:
            account_id = sub_id
            sub_name, sub_ledger_id = subledger_lookup[sub_id]
            account_name = sub_name
            account_type = _subledger_account_type(sub_id)
            control_account_id = sub_ledger_id
            _ln, is_internal, _lt = ledger_lookup[sub_ledger_id]
        else:
            account_id = ledger_id
            ledger_name, is_internal, ledger_type = ledger_lookup[ledger_id]
            account_name = ledger_name
            account_type = ledger_type
            control_account_id = None

        balance_date = (
            posted_at.date() if isinstance(posted_at, datetime) else posted_at
        )
        signed = (
            signed_amount if isinstance(signed_amount, Decimal)
            else Decimal(str(signed_amount))
        )
        new_status = "success" if status == "success" else "failed"
        metadata = _json_metadata(
            {"source": _provenance_source(transfer_type, origin)},
        )

        transactions_rows.append((
            posting_id,            # transaction_id (re-uses the leg-unique id)
            transfer_id,
            parent_tid,
            transfer_type,
            origin,
            account_id,
            account_name,
            control_account_id,
            account_type,
            is_internal,
            signed,
            abs(signed),
            new_status,
            posted_at,
            balance_date,
            None,                  # external_system — AR rows have none
            memo,
            metadata,
        ))

    daily_balances_rows: list[tuple] = []
    for b in subledger_balances:
        sid = b["subledger_account_id"]
        sub_name, ledger_id = subledger_lookup[sid]
        _ln, is_internal, _lt = ledger_lookup[ledger_id]
        daily_balances_rows.append((
            sid,
            sub_name,
            ledger_id,
            _subledger_account_type(sid),
            is_internal,
            b["balance_date"],
            b["balance"],
            _json_metadata({"source": "core_banking"}),
        ))
    for b in ledger_balances:
        lid = b["ledger_account_id"]
        ledger_name, is_internal, account_type = ledger_lookup[lid]
        payload: dict[str, Any] = {"source": "core_banking"}
        limits = _ledger_limits_payload(lid)
        if limits:
            payload["limits"] = limits
        daily_balances_rows.append((
            lid,
            ledger_name,
            None,                  # control_account_id NULL ⇒ ledger-level
            account_type,
            is_internal,
            b["balance_date"],
            b["balance"],
            _json_metadata(payload),
        ))

    return transactions_rows, daily_balances_rows


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

    # F.4.1: ZBA / Cash Concentration sweeps. Sub-ledger legs are merged
    # into transactions (so balance computation picks them up via the
    # existing path); ledger-direct legs are appended to posting_rows
    # after derivation and threaded into _generate_daily_balances so they
    # appear in the master ledger's direct posting totals.
    zba_extra_txns, zba_ledger_postings = _generate_zba_sweeps(
        today, transactions,
    )
    transactions.extend(zba_extra_txns)

    # F.4.2: ACH origination → EOD sweep → Fed confirmation cycle.
    # Customer DDA legs flow through transactions; ledger-direct +
    # external Fed legs feed posting_rows; sweep + Fed transfer rows
    # feed transfer_rows directly (they have no sub-ledger leg to
    # derive from).
    ach_extra_txns, ach_extra_postings, ach_extra_xfers = (
        _generate_ach_origination_cycle(today)
    )
    transactions.extend(ach_extra_txns)

    # F.4.3: External force-posted card settlement cycle. Fed-side
    # observations are emitted directly (external-only legs); SNB
    # internal catch-ups are derived from transactions but linked back
    # to their Fed observation parent via parent_map.
    card_extra_txns, card_extra_postings, card_fed_xfers, card_parent_map = (
        _generate_card_settlement_cycle(today)
    )
    transactions.extend(card_extra_txns)

    # F.4.4: On-us internal transfer originate / settle / reverse cycle.
    # Step-2 transfers (settle or reversal-not-credited) chain back to
    # their Step-1 originate via parent_map; ledger-direct suspense
    # legs feed posting_rows.
    onus_extra_txns, onus_extra_postings, onus_parent_map = (
        _generate_internal_transfer_cycle(today)
    )
    transactions.extend(onus_extra_txns)

    combined_parent_map = {**card_parent_map, **onus_parent_map}
    transfer_rows, posting_rows = _derive_unified_tables(
        transactions, parent_map=combined_parent_map,
    )
    posting_rows.extend(zba_ledger_postings)
    posting_rows.extend(ach_extra_postings)
    posting_rows.extend(card_extra_postings)
    posting_rows.extend(onus_extra_postings)

    ledger_xfer_rows, ledger_post_rows = _generate_ledger_level_transfers(
        rng, today,
    )
    transfer_rows.extend(ledger_xfer_rows)
    transfer_rows.extend(ach_extra_xfers)
    transfer_rows.extend(card_fed_xfers)
    posting_rows.extend(ledger_post_rows)

    subledger_balances, ledger_balances = _generate_daily_balances(
        today, transactions,
        ledger_posting_rows=(
            ledger_post_rows + zba_ledger_postings
            + ach_extra_postings + card_extra_postings
            + onus_extra_postings
        ),
    )

    shared_transaction_rows, shared_daily_balance_rows = (
        _derive_shared_base_tables(
            transfer_rows, posting_rows,
            subledger_balances, ledger_balances,
        )
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

        _inserts("transactions",
                 ["transaction_id", "transfer_id", "parent_transfer_id",
                  "transfer_type", "origin", "account_id", "account_name",
                  "control_account_id", "account_type", "is_internal",
                  "signed_amount", "amount", "status", "posted_at",
                  "balance_date", "external_system", "memo", "metadata"],
                 shared_transaction_rows),

        _inserts("daily_balances",
                 ["account_id", "account_name", "control_account_id",
                  "account_type", "is_internal", "balance_date", "balance",
                  "metadata"],
                 shared_daily_balance_rows),
    ]
    return "\n".join(parts) + "\n"
