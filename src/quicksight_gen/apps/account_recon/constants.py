"""Shared IDs for Account Recon sheets, datasets, filter groups, and
drill parameters.

Extracted to avoid circular imports between analysis.py and visuals.py.
"""

from quicksight_gen.common.dataset_contract import ColumnShape
from quicksight_gen.common.drill import DrillParam
from quicksight_gen.common.ids import (
    FilterGroupId,
    ParameterName,
    SheetId,
    VisualId,
)

# Sheets
SHEET_AR_GETTING_STARTED = SheetId("ar-sheet-getting-started")
SHEET_AR_BALANCES = SheetId("ar-sheet-balances")
SHEET_AR_TRANSFERS = SheetId("ar-sheet-transfers")
SHEET_AR_TRANSACTIONS = SheetId("ar-sheet-transactions")
SHEET_AR_TODAYS_EXCEPTIONS = SheetId("ar-sheet-todays-exceptions")
SHEET_AR_EXCEPTIONS_TRENDS = SheetId("ar-sheet-exceptions-trends")
SHEET_AR_DAILY_STATEMENT = SheetId("ar-sheet-daily-statement")

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
FG_AR_DATE_RANGE = FilterGroupId("fg-ar-date-range")
FG_AR_LEDGER_ACCOUNT = FilterGroupId("fg-ar-ledger-account")
FG_AR_SUBLEDGER_ACCOUNT = FilterGroupId("fg-ar-subledger-account")
FG_AR_TRANSFER_STATUS = FilterGroupId("fg-ar-transfer-status")
FG_AR_TRANSACTION_STATUS = FilterGroupId("fg-ar-transaction-status")
FG_AR_TRANSFER_TYPE = FilterGroupId("fg-ar-transfer-type")
FG_AR_POSTING_LEVEL = FilterGroupId("fg-ar-posting-level")
FG_AR_ORIGIN = FilterGroupId("fg-ar-origin")
FG_AR_BALANCES_LEDGER_DRIFT = FilterGroupId("fg-ar-balances-ledger-drift")
FG_AR_BALANCES_SUBLEDGER_DRIFT = FilterGroupId("fg-ar-balances-subledger-drift")
FG_AR_BALANCES_OVERDRAFT = FilterGroupId("fg-ar-balances-overdraft")
FG_AR_TRANSACTIONS_FAILED = FilterGroupId("fg-ar-transactions-failed")
FG_AR_DRILL_SUBLEDGER_ON_TXN = FilterGroupId("fg-ar-drill-subledger-on-txn")
FG_AR_DRILL_TRANSFER_ON_TXN = FilterGroupId("fg-ar-drill-transfer-on-txn")
FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER = FilterGroupId("fg-ar-drill-ledger-on-balances-subledger")
FG_AR_DRILL_ACTIVITY_DATE_ON_TXN = FilterGroupId("fg-ar-drill-activity-date-on-txn")
FG_AR_DRILL_TRANSFER_TYPE_ON_TXN = FilterGroupId("fg-ar-drill-transfer-type-on-txn")
FG_AR_DRILL_ACCOUNT_ON_TXN = FilterGroupId("fg-ar-drill-account-on-txn")
FG_AR_DS_ACCOUNT = FilterGroupId("fg-ar-ds-account")
FG_AR_DS_BALANCE_DATE = FilterGroupId("fg-ar-ds-balance-date")
FG_AR_TODAYS_EXC_CHECK_TYPE = FilterGroupId("fg-ar-todays-exc-check-type")
FG_AR_TODAYS_EXC_ACCOUNT = FilterGroupId("fg-ar-todays-exc-account")
FG_AR_TODAYS_EXC_AGING = FilterGroupId("fg-ar-todays-exc-aging")
FG_AR_TODAYS_EXC_IS_LATE = FilterGroupId("fg-ar-todays-exc-is-late")

# L.3.9 — `ALL_FG_AR_IDS` aggregate dropped. The source of truth for
# "every filter group registered" is now the tree itself: walk
# ``build_account_recon_app(cfg).analysis.filter_groups`` post-resolve.
# Tests that need the canonical set call into the tree builder.

# ---------------------------------------------------------------------------
# Drill / cross-sheet parameters
#
# Each ``DrillParam`` colocates the QuickSight parameter name with the
# expected value shape so ``cross_sheet_drill`` can refuse a wiring
# whose source-field shape doesn't match. Read ``.name`` when you need
# the bare string for a CategoryFilter, parameter declaration, etc.
# ---------------------------------------------------------------------------

P_AR_SUBLEDGER = DrillParam(ParameterName("pArSubledgerAccountId"),
                            ColumnShape.SUBLEDGER_ACCOUNT_ID)
P_AR_LEDGER = DrillParam(ParameterName("pArLedgerAccountId"),
                         ColumnShape.LEDGER_ACCOUNT_ID)
P_AR_TRANSFER = DrillParam(ParameterName("pArTransferId"), ColumnShape.TRANSFER_ID)
P_AR_ACTIVITY_DATE = DrillParam(ParameterName("pArActivityDate"),
                                ColumnShape.DATE_YYYY_MM_DD_TEXT)
P_AR_TRANSFER_TYPE = DrillParam(ParameterName("pArTransferType"),
                                ColumnShape.TRANSFER_TYPE)
P_AR_ACCOUNT = DrillParam(ParameterName("pArAccountId"), ColumnShape.ACCOUNT_ID)
P_AR_DS_ACCOUNT = DrillParam(ParameterName("pArDsAccountId"), ColumnShape.ACCOUNT_ID)
P_AR_DS_BALANCE_DATE = DrillParam(ParameterName("pArDsBalanceDate"),
                                  ColumnShape.DATETIME_DAY)

# L.3.9 — `ALL_P_AR` aggregate dropped. Walk the tree's parameters
# instead: ``build_account_recon_app(cfg).analysis.parameters``.

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
V_AR_BALANCES_KPI_LEDGERS = VisualId("ar-balances-kpi-ledgers")
V_AR_BALANCES_KPI_SUBLEDGERS = VisualId("ar-balances-kpi-subledgers")
V_AR_BALANCES_LEDGER_TABLE = VisualId("ar-balances-ledger-table")
V_AR_BALANCES_SUBLEDGER_TABLE = VisualId("ar-balances-subledger-table")

# Transfers sheet
V_AR_TRANSFERS_KPI_COUNT = VisualId("ar-transfers-kpi-count")
V_AR_TRANSFERS_KPI_UNHEALTHY = VisualId("ar-transfers-kpi-unhealthy")
V_AR_TRANSFERS_BAR_STATUS = VisualId("ar-transfers-bar-status")
V_AR_TRANSFERS_SUMMARY_TABLE = VisualId("ar-transfers-summary-table")

# Transactions sheet
V_AR_TXN_KPI_COUNT = VisualId("ar-txn-kpi-count")
V_AR_TXN_KPI_FAILED = VisualId("ar-txn-kpi-failed")
V_AR_TXN_BAR_BY_STATUS = VisualId("ar-txn-bar-by-status")
V_AR_TXN_BAR_BY_DAY = VisualId("ar-txn-bar-by-day")
V_AR_TXN_DETAIL_TABLE = VisualId("ar-txn-detail-table")

# Daily Statement sheet
V_AR_DS_KPI_OPENING = VisualId("ar-ds-kpi-opening")
V_AR_DS_KPI_DEBITS = VisualId("ar-ds-kpi-debits")
V_AR_DS_KPI_CREDITS = VisualId("ar-ds-kpi-credits")
V_AR_DS_KPI_CLOSING = VisualId("ar-ds-kpi-closing")
V_AR_DS_KPI_DRIFT = VisualId("ar-ds-kpi-drift")
V_AR_DS_TRANSACTIONS_TABLE = VisualId("ar-ds-transactions-table")

# Today's Exceptions sheet
V_AR_TODAYS_EXC_KPI_TOTAL = VisualId("ar-todays-exc-kpi-total")
V_AR_TODAYS_EXC_BREAKDOWN = VisualId("ar-todays-exc-breakdown")
V_AR_TODAYS_EXC_TABLE = VisualId("ar-todays-exc-table")

# Exceptions Trends sheet
V_AR_EXC_DRIFT_TIMELINES_ROLLUP = VisualId("ar-exc-drift-timelines-rollup")
V_AR_EXC_KPI_TWO_SIDED_ROLLUP = VisualId("ar-exc-kpi-two-sided-rollup")
V_AR_EXC_TWO_SIDED_ROLLUP_TABLE = VisualId("ar-exc-two-sided-rollup-table")
V_AR_EXC_KPI_EXPECTED_ZERO_ROLLUP = VisualId("ar-exc-kpi-expected-zero-rollup")
V_AR_EXC_EXPECTED_ZERO_ROLLUP_TABLE = VisualId("ar-exc-expected-zero-rollup-table")
V_AR_EXC_TRENDS_AGING_MATRIX = VisualId("ar-exc-trends-aging-matrix")
V_AR_EXC_TRENDS_PER_CHECK = VisualId("ar-exc-trends-per-check")

# L.3.9 — `ALL_V_AR` aggregate dropped. Walk the tree's emitted visuals
# instead: `[v.visual_id for s in app.analysis.sheets for v in s.visuals]`
# (post-emit, after auto-IDs resolve).
