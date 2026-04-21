"""Shared IDs for Account Recon sheets and datasets.

Extracted to avoid circular imports between analysis.py and visuals.py.
"""

# Sheets
SHEET_AR_GETTING_STARTED = "ar-sheet-getting-started"
SHEET_AR_BALANCES = "ar-sheet-balances"
SHEET_AR_TRANSFERS = "ar-sheet-transfers"
SHEET_AR_TRANSACTIONS = "ar-sheet-transactions"
SHEET_AR_TODAYS_EXCEPTIONS = "ar-sheet-todays-exceptions"
SHEET_AR_EXCEPTIONS_TRENDS = "ar-sheet-exceptions-trends"
SHEET_AR_DAILY_STATEMENT = "ar-sheet-daily-statement"

# Datasets
DS_AR_LEDGER_ACCOUNTS = "ar-ledger-accounts-ds"
DS_AR_SUBLEDGER_ACCOUNTS = "ar-subledger-accounts-ds"
DS_AR_TRANSACTIONS = "ar-transactions-ds"
DS_AR_LEDGER_BALANCE_DRIFT = "ar-ledger-balance-drift-ds"
DS_AR_SUBLEDGER_BALANCE_DRIFT = "ar-subledger-balance-drift-ds"
DS_AR_TRANSFER_SUMMARY = "ar-transfer-summary-ds"
DS_AR_NON_ZERO_TRANSFERS = "ar-non-zero-transfers-ds"
DS_AR_EXPECTED_ZERO_EOD_ROLLUP = "ar-expected-zero-eod-rollup-ds"
DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP = "ar-two-sided-post-mismatch-rollup-ds"
DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP = "ar-balance-drift-timelines-rollup-ds"
DS_AR_DAILY_STATEMENT_SUMMARY = "ar-daily-statement-summary-ds"
DS_AR_DAILY_STATEMENT_TRANSACTIONS = "ar-daily-statement-transactions-ds"
DS_AR_UNIFIED_EXCEPTIONS = "ar-unified-exceptions-ds"
