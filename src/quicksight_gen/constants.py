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

# ---------------------------------------------------------------------------
# Reconciliation analysis
# ---------------------------------------------------------------------------

SHEET_RECON_OVERVIEW = "sheet-recon-overview"
SHEET_SALES_RECON = "sheet-sales-recon"
SHEET_SETTLEMENT_RECON = "sheet-settlement-recon"
SHEET_PAYMENT_RECON = "sheet-payment-recon"

DS_EXTERNAL_TRANSACTIONS = "external-transactions-ds"
DS_SALES_RECON = "sales-recon-ds"
DS_SETTLEMENT_RECON = "settlement-recon-ds"
DS_PAYMENT_RECON = "payment-recon-ds"
DS_RECON_EXCEPTIONS = "recon-exceptions-ds"
