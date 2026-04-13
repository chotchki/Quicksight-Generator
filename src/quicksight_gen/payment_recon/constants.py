"""Shared constants for sheet IDs and dataset identifiers.

Extracted to avoid circular imports between analysis.py and visuals.py.
"""

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
