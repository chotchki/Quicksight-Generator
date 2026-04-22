"""Shared IDs for Account Recon sheets, datasets, filter groups, and
drill parameters.

Extracted to avoid circular imports between analysis.py and visuals.py.
"""

from quicksight_gen.common.dataset_contract import ColumnShape
from quicksight_gen.common.drill import DrillParam

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

# Filter groups
FG_AR_DATE_RANGE = "fg-ar-date-range"
FG_AR_LEDGER_ACCOUNT = "fg-ar-ledger-account"
FG_AR_SUBLEDGER_ACCOUNT = "fg-ar-subledger-account"
FG_AR_TRANSFER_STATUS = "fg-ar-transfer-status"
FG_AR_TRANSACTION_STATUS = "fg-ar-transaction-status"
FG_AR_TRANSFER_TYPE = "fg-ar-transfer-type"
FG_AR_POSTING_LEVEL = "fg-ar-posting-level"
FG_AR_ORIGIN = "fg-ar-origin"
FG_AR_BALANCES_LEDGER_DRIFT = "fg-ar-balances-ledger-drift"
FG_AR_BALANCES_SUBLEDGER_DRIFT = "fg-ar-balances-subledger-drift"
FG_AR_BALANCES_OVERDRAFT = "fg-ar-balances-overdraft"
FG_AR_TRANSACTIONS_FAILED = "fg-ar-transactions-failed"
FG_AR_DRILL_SUBLEDGER_ON_TXN = "fg-ar-drill-subledger-on-txn"
FG_AR_DRILL_TRANSFER_ON_TXN = "fg-ar-drill-transfer-on-txn"
FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER = "fg-ar-drill-ledger-on-balances-subledger"
FG_AR_DRILL_ACTIVITY_DATE_ON_TXN = "fg-ar-drill-activity-date-on-txn"
FG_AR_DRILL_TRANSFER_TYPE_ON_TXN = "fg-ar-drill-transfer-type-on-txn"
FG_AR_DRILL_ACCOUNT_ON_TXN = "fg-ar-drill-account-on-txn"
FG_AR_DS_ACCOUNT = "fg-ar-ds-account"
FG_AR_DS_BALANCE_DATE = "fg-ar-ds-balance-date"
FG_AR_TODAYS_EXC_CHECK_TYPE = "fg-ar-todays-exc-check-type"
FG_AR_TODAYS_EXC_ACCOUNT = "fg-ar-todays-exc-account"
FG_AR_TODAYS_EXC_AGING = "fg-ar-todays-exc-aging"

# Source of truth for tests asserting "every filter group is registered here".
# Add new FG_AR_* constants and remember to extend this set.
ALL_FG_AR_IDS: frozenset[str] = frozenset({
    FG_AR_DATE_RANGE,
    FG_AR_LEDGER_ACCOUNT,
    FG_AR_SUBLEDGER_ACCOUNT,
    FG_AR_TRANSFER_STATUS,
    FG_AR_TRANSACTION_STATUS,
    FG_AR_TRANSFER_TYPE,
    FG_AR_POSTING_LEVEL,
    FG_AR_ORIGIN,
    FG_AR_BALANCES_LEDGER_DRIFT,
    FG_AR_BALANCES_SUBLEDGER_DRIFT,
    FG_AR_BALANCES_OVERDRAFT,
    FG_AR_TRANSACTIONS_FAILED,
    FG_AR_DRILL_SUBLEDGER_ON_TXN,
    FG_AR_DRILL_TRANSFER_ON_TXN,
    FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER,
    FG_AR_DRILL_ACTIVITY_DATE_ON_TXN,
    FG_AR_DRILL_TRANSFER_TYPE_ON_TXN,
    FG_AR_DRILL_ACCOUNT_ON_TXN,
    FG_AR_DS_ACCOUNT,
    FG_AR_DS_BALANCE_DATE,
    FG_AR_TODAYS_EXC_CHECK_TYPE,
    FG_AR_TODAYS_EXC_ACCOUNT,
    FG_AR_TODAYS_EXC_AGING,
})

# ---------------------------------------------------------------------------
# Drill / cross-sheet parameters
#
# Each ``DrillParam`` colocates the QuickSight parameter name with the
# expected value shape so ``cross_sheet_drill`` can refuse a wiring
# whose source-field shape doesn't match. Read ``.name`` when you need
# the bare string for a CategoryFilter, parameter declaration, etc.
# ---------------------------------------------------------------------------

P_AR_SUBLEDGER = DrillParam("pArSubledgerAccountId",
                            ColumnShape.SUBLEDGER_ACCOUNT_ID)
P_AR_LEDGER = DrillParam("pArLedgerAccountId", ColumnShape.LEDGER_ACCOUNT_ID)
P_AR_TRANSFER = DrillParam("pArTransferId", ColumnShape.TRANSFER_ID)
P_AR_ACTIVITY_DATE = DrillParam("pArActivityDate",
                                ColumnShape.DATE_YYYY_MM_DD_TEXT)
P_AR_TRANSFER_TYPE = DrillParam("pArTransferType", ColumnShape.TRANSFER_TYPE)
P_AR_ACCOUNT = DrillParam("pArAccountId", ColumnShape.ACCOUNT_ID)
P_AR_DS_ACCOUNT = DrillParam("pArDsAccountId", ColumnShape.ACCOUNT_ID)
P_AR_DS_BALANCE_DATE = DrillParam("pArDsBalanceDate", ColumnShape.DATETIME_DAY)

ALL_P_AR: tuple[DrillParam, ...] = (
    P_AR_SUBLEDGER,
    P_AR_LEDGER,
    P_AR_TRANSFER,
    P_AR_ACTIVITY_DATE,
    P_AR_TRANSFER_TYPE,
    P_AR_ACCOUNT,
    P_AR_DS_ACCOUNT,
    P_AR_DS_BALANCE_DATE,
)

# ---------------------------------------------------------------------------
# Visual IDs
#
# Promoted to constants so a typo in a FilterGroup's VisualId scope or a
# drill action's target visual fails at the import line, not silently
# in the deployed dashboard. Visual IDs flow into
# ``SheetVisualScopingConfigurations.VisualIds`` and a typo there
# silently widens the filter's scope to ALL_VISUALS without raising.
# ---------------------------------------------------------------------------

# Balances sheet
V_AR_BALANCES_KPI_LEDGERS = "ar-balances-kpi-ledgers"
V_AR_BALANCES_KPI_SUBLEDGERS = "ar-balances-kpi-subledgers"
V_AR_BALANCES_LEDGER_TABLE = "ar-balances-ledger-table"
V_AR_BALANCES_SUBLEDGER_TABLE = "ar-balances-subledger-table"

# Transfers sheet
V_AR_TRANSFERS_KPI_COUNT = "ar-transfers-kpi-count"
V_AR_TRANSFERS_KPI_UNHEALTHY = "ar-transfers-kpi-unhealthy"
V_AR_TRANSFERS_BAR_STATUS = "ar-transfers-bar-status"
V_AR_TRANSFERS_SUMMARY_TABLE = "ar-transfers-summary-table"

# Transactions sheet
V_AR_TXN_KPI_COUNT = "ar-txn-kpi-count"
V_AR_TXN_KPI_FAILED = "ar-txn-kpi-failed"
V_AR_TXN_BAR_BY_STATUS = "ar-txn-bar-by-status"
V_AR_TXN_BAR_BY_DAY = "ar-txn-bar-by-day"
V_AR_TXN_DETAIL_TABLE = "ar-txn-detail-table"

# Daily Statement sheet
V_AR_DS_KPI_OPENING = "ar-ds-kpi-opening"
V_AR_DS_KPI_DEBITS = "ar-ds-kpi-debits"
V_AR_DS_KPI_CREDITS = "ar-ds-kpi-credits"
V_AR_DS_KPI_CLOSING = "ar-ds-kpi-closing"
V_AR_DS_KPI_DRIFT = "ar-ds-kpi-drift"
V_AR_DS_TRANSACTIONS_TABLE = "ar-ds-transactions-table"

# Today's Exceptions sheet
V_AR_TODAYS_EXC_KPI_TOTAL = "ar-todays-exc-kpi-total"
V_AR_TODAYS_EXC_BREAKDOWN = "ar-todays-exc-breakdown"
V_AR_TODAYS_EXC_TABLE = "ar-todays-exc-table"

# Exceptions Trends sheet
V_AR_EXC_DRIFT_TIMELINES_ROLLUP = "ar-exc-drift-timelines-rollup"
V_AR_EXC_KPI_TWO_SIDED_ROLLUP = "ar-exc-kpi-two-sided-rollup"
V_AR_EXC_TWO_SIDED_ROLLUP_TABLE = "ar-exc-two-sided-rollup-table"
V_AR_EXC_KPI_EXPECTED_ZERO_ROLLUP = "ar-exc-kpi-expected-zero-rollup"
V_AR_EXC_EXPECTED_ZERO_ROLLUP_TABLE = "ar-exc-expected-zero-rollup-table"
V_AR_EXC_TRENDS_AGING_MATRIX = "ar-exc-trends-aging-matrix"
V_AR_EXC_TRENDS_PER_CHECK = "ar-exc-trends-per-check"

ALL_V_AR: frozenset[str] = frozenset({
    V_AR_BALANCES_KPI_LEDGERS,
    V_AR_BALANCES_KPI_SUBLEDGERS,
    V_AR_BALANCES_LEDGER_TABLE,
    V_AR_BALANCES_SUBLEDGER_TABLE,
    V_AR_TRANSFERS_KPI_COUNT,
    V_AR_TRANSFERS_KPI_UNHEALTHY,
    V_AR_TRANSFERS_BAR_STATUS,
    V_AR_TRANSFERS_SUMMARY_TABLE,
    V_AR_TXN_KPI_COUNT,
    V_AR_TXN_KPI_FAILED,
    V_AR_TXN_BAR_BY_STATUS,
    V_AR_TXN_BAR_BY_DAY,
    V_AR_TXN_DETAIL_TABLE,
    V_AR_DS_KPI_OPENING,
    V_AR_DS_KPI_DEBITS,
    V_AR_DS_KPI_CREDITS,
    V_AR_DS_KPI_CLOSING,
    V_AR_DS_KPI_DRIFT,
    V_AR_DS_TRANSACTIONS_TABLE,
    V_AR_TODAYS_EXC_KPI_TOTAL,
    V_AR_TODAYS_EXC_BREAKDOWN,
    V_AR_TODAYS_EXC_TABLE,
    V_AR_EXC_DRIFT_TIMELINES_ROLLUP,
    V_AR_EXC_KPI_TWO_SIDED_ROLLUP,
    V_AR_EXC_TWO_SIDED_ROLLUP_TABLE,
    V_AR_EXC_KPI_EXPECTED_ZERO_ROLLUP,
    V_AR_EXC_EXPECTED_ZERO_ROLLUP_TABLE,
    V_AR_EXC_TRENDS_AGING_MATRIX,
    V_AR_EXC_TRENDS_PER_CHECK,
})
