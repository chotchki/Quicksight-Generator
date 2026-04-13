"""Shared IDs for Account Recon sheets and datasets.

Extracted to avoid circular imports between analysis.py and visuals.py.
"""

# Sheets
SHEET_AR_GETTING_STARTED = "ar-sheet-getting-started"
SHEET_AR_BALANCES = "ar-sheet-balances"
SHEET_AR_TRANSFERS = "ar-sheet-transfers"
SHEET_AR_TRANSACTIONS = "ar-sheet-transactions"
SHEET_AR_EXCEPTIONS = "ar-sheet-exceptions"

# Datasets
DS_AR_PARENT_ACCOUNTS = "ar-parent-accounts-ds"
DS_AR_ACCOUNTS = "ar-accounts-ds"
DS_AR_TRANSACTIONS = "ar-transactions-ds"
DS_AR_PARENT_BALANCE_DRIFT = "ar-parent-balance-drift-ds"
DS_AR_ACCOUNT_BALANCE_DRIFT = "ar-account-balance-drift-ds"
DS_AR_TRANSFER_SUMMARY = "ar-transfer-summary-ds"
DS_AR_NON_ZERO_TRANSFERS = "ar-non-zero-transfers-ds"
