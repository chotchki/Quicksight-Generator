"""Shared constants for sheet IDs, dataset identifiers, and filter groups.

Extracted to avoid circular imports between analysis.py and visuals.py.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Sheet IDs
# ---------------------------------------------------------------------------

SHEET_GETTING_STARTED = "sheet-getting-started"
SHEET_SALES = "sheet-sales-overview"
SHEET_SETTLEMENTS = "sheet-settlements"
SHEET_PAYMENTS = "sheet-payments"
SHEET_EXCEPTIONS = "sheet-exceptions"

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

SHEET_PAYMENT_RECON = "sheet-payment-recon"

DS_EXTERNAL_TRANSACTIONS = "external-transactions-ds"
DS_PAYMENT_RECON = "payment-recon-ds"

# ---------------------------------------------------------------------------
# Filter groups — static
# ---------------------------------------------------------------------------

FG_PR_MERCHANT = "fg-merchant"
FG_PR_LOCATION = "fg-location"
FG_PR_SETTLEMENT_STATUS = "fg-settlement-status"
FG_PR_PAYMENT_STATUS = "fg-payment-status"
FG_PR_PAYMENT_METHOD = "fg-payment-method"
FG_PR_SALES_UNSETTLED = "fg-sales-unsettled"
FG_PR_SETTLEMENTS_UNPAID = "fg-settlements-unpaid"
FG_PR_PAYMENTS_UNMATCHED = "fg-payments-unmatched"
FG_PR_PAYMENTS_KPI_RETURNS_ONLY = "fg-payments-kpi-returns-only"
FG_PR_SETTLEMENTS_KPI_PENDING_ONLY = "fg-settlements-kpi-pending-only"
FG_PR_RECON_DATE_RANGE = "fg-recon-date-range"
FG_PR_RECON_MATCH_STATUS = "fg-recon-match-status"
FG_PR_RECON_EXTERNAL_SYSTEM = "fg-recon-external-system"
FG_PR_RECON_KPI_LATE_ONLY = "fg-recon-kpi-late-only"
FG_PR_RECON_KPI_MATCHED_ONLY = "fg-recon-kpi-matched-only"
FG_PR_RECON_KPI_UNMATCHED_ONLY = "fg-recon-kpi-unmatched-only"

_STATIC_FG_PR_IDS: frozenset[str] = frozenset({
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
    def fg_id(self) -> str:
        return f"fg-{self.slug}-date-range"

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
    def fg_id(self) -> str:
        return f"fg-sales-meta-{self.column}"

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
    def fg_id(self) -> str:
        return f"fg-drill-{self.kind}-on-{self.location}"

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


# Sheet slugs that carry a date-range filter — single source of truth so
# tests can enumerate the dynamic FG IDs without grepping filters.py.
PR_DATE_RANGE_SHEET_SLUGS: tuple[str, ...] = (
    "sales",
    "settlements",
    "payments",
    "exceptions",
)


def all_fg_pr_ids() -> frozenset[str]:
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
