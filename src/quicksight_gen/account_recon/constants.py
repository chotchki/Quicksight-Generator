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
DS_AR_LEDGER_ACCOUNTS = "ar-ledger-accounts-ds"
DS_AR_SUBLEDGER_ACCOUNTS = "ar-subledger-accounts-ds"
DS_AR_TRANSACTIONS = "ar-transactions-ds"
DS_AR_LEDGER_BALANCE_DRIFT = "ar-ledger-balance-drift-ds"
DS_AR_SUBLEDGER_BALANCE_DRIFT = "ar-subledger-balance-drift-ds"
DS_AR_TRANSFER_SUMMARY = "ar-transfer-summary-ds"
DS_AR_NON_ZERO_TRANSFERS = "ar-non-zero-transfers-ds"
DS_AR_LIMIT_BREACH = "ar-limit-breach-ds"
DS_AR_OVERDRAFT = "ar-overdraft-ds"
