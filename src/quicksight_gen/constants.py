"""Shared constants for sheet IDs and dataset identifiers.

Extracted to avoid circular imports between analysis.py and visuals.py.
"""

# ---------------------------------------------------------------------------
# Sheet IDs
# ---------------------------------------------------------------------------

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
