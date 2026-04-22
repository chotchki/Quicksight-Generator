"""Shared constants for sheet IDs, dataset identifiers, filter groups,
and drill parameters.

Extracted to avoid circular imports between analysis.py and visuals.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from quicksight_gen.common.dataset_contract import ColumnShape
from quicksight_gen.common.drill import DrillParam
from quicksight_gen.common.ids import (
    FilterGroupId,
    ParameterName,
    SheetId,
    VisualId,
)

# ---------------------------------------------------------------------------
# Sheet IDs
# ---------------------------------------------------------------------------

SHEET_GETTING_STARTED = SheetId("sheet-getting-started")
SHEET_SALES = SheetId("sheet-sales-overview")
SHEET_SETTLEMENTS = SheetId("sheet-settlements")
SHEET_PAYMENTS = SheetId("sheet-payments")
SHEET_EXCEPTIONS = SheetId("sheet-exceptions")

# ---------------------------------------------------------------------------
# Dataset identifiers (used in DataSetIdentifierDeclarations and visuals)
# ---------------------------------------------------------------------------

DS_MERCHANTS = "merchants-ds"
DS_SALES = "sales-ds"
DS_SETTLEMENTS = "settlements-ds"
DS_PAYMENTS = "payments-ds"
DS_SETTLEMENT_EXCEPTIONS = "settlement-exceptions-ds"
DS_PAYMENT_RETURNS = "payment-returns-ds"

# New exception datasets (SPEC 2.4)
DS_SALE_SETTLEMENT_MISMATCH = "sale-settlement-mismatch-ds"
DS_SETTLEMENT_PAYMENT_MISMATCH = "settlement-payment-mismatch-ds"
DS_UNMATCHED_EXTERNAL_TXNS = "unmatched-external-txns-ds"

# ---------------------------------------------------------------------------
# Reconciliation (consolidated into the financial analysis)
# ---------------------------------------------------------------------------

SHEET_PAYMENT_RECON = SheetId("sheet-payment-recon")

DS_EXTERNAL_TRANSACTIONS = "external-transactions-ds"
DS_PAYMENT_RECON = "payment-recon-ds"

# ---------------------------------------------------------------------------
# Filter groups — static
# ---------------------------------------------------------------------------

FG_PR_MERCHANT = FilterGroupId("fg-merchant")
FG_PR_LOCATION = FilterGroupId("fg-location")
FG_PR_SETTLEMENT_STATUS = FilterGroupId("fg-settlement-status")
FG_PR_PAYMENT_STATUS = FilterGroupId("fg-payment-status")
FG_PR_PAYMENT_METHOD = FilterGroupId("fg-payment-method")
FG_PR_SALES_UNSETTLED = FilterGroupId("fg-sales-unsettled")
FG_PR_SETTLEMENTS_UNPAID = FilterGroupId("fg-settlements-unpaid")
FG_PR_PAYMENTS_UNMATCHED = FilterGroupId("fg-payments-unmatched")
FG_PR_PAYMENTS_KPI_RETURNS_ONLY = FilterGroupId("fg-payments-kpi-returns-only")
FG_PR_SETTLEMENTS_KPI_PENDING_ONLY = FilterGroupId("fg-settlements-kpi-pending-only")
FG_PR_RECON_DATE_RANGE = FilterGroupId("fg-recon-date-range")
FG_PR_RECON_MATCH_STATUS = FilterGroupId("fg-recon-match-status")
FG_PR_RECON_EXTERNAL_SYSTEM = FilterGroupId("fg-recon-external-system")
FG_PR_RECON_KPI_LATE_ONLY = FilterGroupId("fg-recon-kpi-late-only")
FG_PR_RECON_KPI_MATCHED_ONLY = FilterGroupId("fg-recon-kpi-matched-only")
FG_PR_RECON_KPI_UNMATCHED_ONLY = FilterGroupId("fg-recon-kpi-unmatched-only")

_STATIC_FG_PR_IDS: frozenset[FilterGroupId] = frozenset({
    FG_PR_MERCHANT,
    FG_PR_LOCATION,
    FG_PR_SETTLEMENT_STATUS,
    FG_PR_PAYMENT_STATUS,
    FG_PR_PAYMENT_METHOD,
    FG_PR_SALES_UNSETTLED,
    FG_PR_SETTLEMENTS_UNPAID,
    FG_PR_PAYMENTS_UNMATCHED,
    FG_PR_PAYMENTS_KPI_RETURNS_ONLY,
    FG_PR_SETTLEMENTS_KPI_PENDING_ONLY,
    FG_PR_RECON_DATE_RANGE,
    FG_PR_RECON_MATCH_STATUS,
    FG_PR_RECON_EXTERNAL_SYSTEM,
    FG_PR_RECON_KPI_LATE_ONLY,
    FG_PR_RECON_KPI_MATCHED_ONLY,
    FG_PR_RECON_KPI_UNMATCHED_ONLY,
})


# ---------------------------------------------------------------------------
# Filter groups — slug/column-parameterized
#
# Two PR families build the FG ID and the bound FilterId from the same
# slug, so a typo in one without the other silently de-syncs the wiring.
# Encode the format in a small dataclass and let the call site read
# ``.fg_id`` / ``.filter_id`` instead of f-strings.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SheetDateRange:
    """Per-sheet date-range filter group on the PR pipeline tabs.

    Each pipeline sheet has its own date filter because each detail
    dataset carries a different timestamp column. The slug also names
    the bound FilterControl (``ctrl-{sheet}-date-range``).
    """

    slug: str

    @property
    def fg_id(self) -> FilterGroupId:
        return FilterGroupId(f"fg-{self.slug}-date-range")

    @property
    def filter_id(self) -> str:
        return f"filter-{self.slug}-date-range"


@dataclass(frozen=True)
class SalesMeta:
    """Per-metadata-column filter group on the Sales sheet.

    Built from each entry in ``OPTIONAL_SALE_METADATA`` (datasets.py).
    """

    column: str

    @property
    def fg_id(self) -> FilterGroupId:
        return FilterGroupId(f"fg-sales-meta-{self.column}")

    @property
    def filter_id(self) -> str:
        return f"filter-sales-meta-{self.column}"


@dataclass(frozen=True)
class DrillBinding:
    """Cross-sheet drill-down filter group.

    A drill action sets a parameter (settlement-id / payment-id /
    ext-txn-id), which a SINGLE_DATASET filter group on the destination
    sheet then consumes. ``kind`` names the parameter family,
    ``location`` names where the filter is bound (sheet slug or column
    qualifier when two bindings on the same sheet need to be distinct).
    """

    kind: str
    location: str

    @property
    def fg_id(self) -> FilterGroupId:
        return FilterGroupId(f"fg-drill-{self.kind}-on-{self.location}")

    @property
    def filter_id(self) -> str:
        return f"filter-drill-{self.kind}-on-{self.location}"


# Cross-sheet drill bindings — single source of truth so analysis.py
# wiring and tests asserting "all PR drill FGs are registered" stay
# in sync.
PR_DRILL_BINDINGS: tuple[DrillBinding, ...] = (
    DrillBinding("settlement", "sales"),
    DrillBinding("settlement", "settlements"),
    DrillBinding("payment", "payments"),
    DrillBinding("ext-txn", "recon"),
    DrillBinding("ext-txn", "payments"),
)


# ---------------------------------------------------------------------------
# Drill / cross-sheet parameters
#
# Same pattern as account_recon — the parameter name + shape are
# colocated so cross_sheet_drill can refuse a wiring whose source-field
# shape doesn't match. Read ``.name`` when you need the bare string.
# ---------------------------------------------------------------------------

P_PR_SETTLEMENT = DrillParam(ParameterName("pSettlementId"),
                             ColumnShape.SETTLEMENT_ID)
P_PR_PAYMENT = DrillParam(ParameterName("pPaymentId"), ColumnShape.PAYMENT_ID)
P_PR_EXTERNAL_TXN = DrillParam(ParameterName("pExternalTransactionId"),
                               ColumnShape.EXTERNAL_TXN_ID)

ALL_P_PR: tuple[DrillParam, ...] = (
    P_PR_SETTLEMENT,
    P_PR_PAYMENT,
    P_PR_EXTERNAL_TXN,
)


# Sheet slugs that carry a date-range filter — single source of truth so
# tests can enumerate the dynamic FG IDs without grepping filters.py.
PR_DATE_RANGE_SHEET_SLUGS: tuple[str, ...] = (
    "sales",
    "settlements",
    "payments",
    "exceptions",
)


def all_fg_pr_ids() -> frozenset[FilterGroupId]:
    """Source of truth for tests asserting "every PR filter group is registered".

    Composed lazily because the per-metadata-column IDs are derived from
    ``OPTIONAL_SALE_METADATA`` which lives in datasets.py (would be a
    circular import at module load).
    """
    from quicksight_gen.payment_recon.datasets import OPTIONAL_SALE_METADATA
    return frozenset({
        *_STATIC_FG_PR_IDS,
        *(SheetDateRange(slug).fg_id for slug in PR_DATE_RANGE_SHEET_SLUGS),
        *(SalesMeta(col).fg_id for col, *_ in OPTIONAL_SALE_METADATA),
        *(b.fg_id for b in PR_DRILL_BINDINGS),
    })


# ---------------------------------------------------------------------------
# Visual IDs
#
# Promoted to constants so a typo in a FilterGroup's VisualId scope or a
# drill action's target visual fails at the import line, not silently
# in the deployed dashboard. Visual IDs flow into
# ``SheetVisualScopingConfigurations.VisualIds`` and a typo there
# silently widens the filter's scope to ALL_VISUALS without raising.
# ---------------------------------------------------------------------------

# Sales sheet
V_PR_SALES_KPI_COUNT = VisualId("sales-kpi-count")
V_PR_SALES_KPI_AMOUNT = VisualId("sales-kpi-amount")
V_PR_SALES_BAR_BY_MERCHANT = VisualId("sales-bar-by-merchant")
V_PR_SALES_BAR_BY_LOCATION = VisualId("sales-bar-by-location")
V_PR_SALES_DETAIL_TABLE = VisualId("sales-detail-table")

# Settlements sheet
V_PR_SETTLEMENTS_KPI_AMOUNT = VisualId("settlements-kpi-amount")
V_PR_SETTLEMENTS_KPI_PENDING = VisualId("settlements-kpi-pending")
V_PR_SETTLEMENTS_BAR_BY_TYPE = VisualId("settlements-bar-by-type")
V_PR_SETTLEMENTS_DETAIL_TABLE = VisualId("settlements-detail-table")

# Payments sheet
V_PR_PAYMENTS_KPI_AMOUNT = VisualId("payments-kpi-amount")
V_PR_PAYMENTS_KPI_RETURNS = VisualId("payments-kpi-returns")
V_PR_PAYMENTS_BAR_STATUS = VisualId("payments-bar-status")
V_PR_PAYMENTS_DETAIL_TABLE = VisualId("payments-detail-table")

# Exceptions sheet
V_PR_EXC_KPI_UNSETTLED = VisualId("exceptions-kpi-unsettled")
V_PR_EXC_KPI_RETURNS = VisualId("exceptions-kpi-returns")
V_PR_EXC_UNSETTLED_TABLE = VisualId("exceptions-unsettled-table")
V_PR_EXC_RETURNS_TABLE = VisualId("exceptions-returns-table")
V_PR_EXC_SALE_SETTLEMENT_MISMATCH_TABLE = VisualId("exceptions-sale-settlement-mismatch-table")
V_PR_EXC_SETTLEMENT_PAYMENT_MISMATCH_TABLE = VisualId("exceptions-settlement-payment-mismatch-table")
V_PR_EXC_UNMATCHED_EXT_TXN_TABLE = VisualId("exceptions-unmatched-ext-txn-table")
V_PR_EXC_AGING_UNSETTLED = VisualId("exceptions-aging-unsettled")
V_PR_EXC_AGING_RETURNS = VisualId("exceptions-aging-returns")
V_PR_EXC_AGING_SALE_STL_MISMATCH = VisualId("exceptions-aging-sale-stl-mismatch")
V_PR_EXC_AGING_STL_PAY_MISMATCH = VisualId("exceptions-aging-stl-pay-mismatch")
V_PR_EXC_AGING_UNMATCHED_EXT = VisualId("exceptions-aging-unmatched-ext")

# Payment Reconciliation sheet
V_PR_RECON_KPI_MATCHED_AMOUNT = VisualId("recon-kpi-matched-amount")
V_PR_RECON_KPI_UNMATCHED_AMOUNT = VisualId("recon-kpi-unmatched-amount")
V_PR_RECON_KPI_LATE_COUNT = VisualId("recon-kpi-late-count")
V_PR_RECON_BAR_BY_SYSTEM = VisualId("recon-bar-by-system")
V_PR_RECON_EXT_TXN_TABLE = VisualId("recon-ext-txn-table")
V_PR_RECON_PAYMENTS_TABLE = VisualId("recon-payments-table")
V_PR_RECON_AGING_BAR = VisualId("recon-aging-bar")

ALL_V_PR: frozenset[VisualId] = frozenset({
    V_PR_SALES_KPI_COUNT,
    V_PR_SALES_KPI_AMOUNT,
    V_PR_SALES_BAR_BY_MERCHANT,
    V_PR_SALES_BAR_BY_LOCATION,
    V_PR_SALES_DETAIL_TABLE,
    V_PR_SETTLEMENTS_KPI_AMOUNT,
    V_PR_SETTLEMENTS_KPI_PENDING,
    V_PR_SETTLEMENTS_BAR_BY_TYPE,
    V_PR_SETTLEMENTS_DETAIL_TABLE,
    V_PR_PAYMENTS_KPI_AMOUNT,
    V_PR_PAYMENTS_KPI_RETURNS,
    V_PR_PAYMENTS_BAR_STATUS,
    V_PR_PAYMENTS_DETAIL_TABLE,
    V_PR_EXC_KPI_UNSETTLED,
    V_PR_EXC_KPI_RETURNS,
    V_PR_EXC_UNSETTLED_TABLE,
    V_PR_EXC_RETURNS_TABLE,
    V_PR_EXC_SALE_SETTLEMENT_MISMATCH_TABLE,
    V_PR_EXC_SETTLEMENT_PAYMENT_MISMATCH_TABLE,
    V_PR_EXC_UNMATCHED_EXT_TXN_TABLE,
    V_PR_EXC_AGING_UNSETTLED,
    V_PR_EXC_AGING_RETURNS,
    V_PR_EXC_AGING_SALE_STL_MISMATCH,
    V_PR_EXC_AGING_STL_PAY_MISMATCH,
    V_PR_EXC_AGING_UNMATCHED_EXT,
    V_PR_RECON_KPI_MATCHED_AMOUNT,
    V_PR_RECON_KPI_UNMATCHED_AMOUNT,
    V_PR_RECON_KPI_LATE_COUNT,
    V_PR_RECON_BAR_BY_SYSTEM,
    V_PR_RECON_EXT_TXN_TABLE,
    V_PR_RECON_PAYMENTS_TABLE,
    V_PR_RECON_AGING_BAR,
})
