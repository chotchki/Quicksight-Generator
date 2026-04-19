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
DS_AR_SWEEP_TARGET_NONZERO = "ar-sweep-target-nonzero-ds"
DS_AR_CONCENTRATION_MASTER_SWEEP_DRIFT = "ar-concentration-master-sweep-drift-ds"
DS_AR_ACH_ORIG_SETTLEMENT_NONZERO = "ar-ach-orig-settlement-nonzero-ds"
DS_AR_ACH_SWEEP_NO_FED_CONFIRMATION = "ar-ach-sweep-no-fed-confirmation-ds"
DS_AR_FED_CARD_NO_INTERNAL_CATCHUP = "ar-fed-card-no-internal-catchup-ds"
DS_AR_GL_VS_FED_MASTER_DRIFT = "ar-gl-vs-fed-master-drift-ds"
DS_AR_INTERNAL_TRANSFER_STUCK = "ar-internal-transfer-stuck-ds"
DS_AR_INTERNAL_TRANSFER_SUSPENSE_NONZERO = "ar-internal-transfer-suspense-nonzero-ds"
DS_AR_INTERNAL_REVERSAL_UNCREDITED = "ar-internal-reversal-uncredited-ds"
DS_AR_EXPECTED_ZERO_EOD_ROLLUP = "ar-expected-zero-eod-rollup-ds"
DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP = "ar-two-sided-post-mismatch-rollup-ds"
DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP = "ar-balance-drift-timelines-rollup-ds"
