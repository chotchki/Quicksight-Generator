"""Shared IDs for Investigation sheets, datasets, filter groups, and
visual IDs.

Phase K.4.2 shipped the 4 sheet IDs. K.4.3 adds the Recipient Fanout
sheet's dataset, filter group, parameter, and visual IDs. K.4.4 adds
the Volume Anomalies sheet's IDs. Money Trail lands in K.4.5.
"""

from quicksight_gen.common.ids import (
    FilterGroupId,
    ParameterName,
    SheetId,
    VisualId,
)

# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

SHEET_INV_GETTING_STARTED = SheetId("inv-sheet-getting-started")
SHEET_INV_FANOUT = SheetId("inv-sheet-fanout")              # K.4.3
SHEET_INV_ANOMALIES = SheetId("inv-sheet-anomalies")        # K.4.4
SHEET_INV_MONEY_TRAIL = SheetId("inv-sheet-money-trail")    # K.4.5

# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

DS_INV_RECIPIENT_FANOUT = "inv-recipient-fanout-ds"          # K.4.3
DS_INV_VOLUME_ANOMALIES = "inv-volume-anomalies-ds"          # K.4.4

# ---------------------------------------------------------------------------
# Filter groups
# ---------------------------------------------------------------------------

FG_INV_FANOUT_THRESHOLD = FilterGroupId("fg-inv-fanout-threshold")  # K.4.3
FG_INV_FANOUT_WINDOW = FilterGroupId("fg-inv-fanout-window")        # K.4.3
FG_INV_ANOMALIES_SIGMA = FilterGroupId("fg-inv-anomalies-sigma")    # K.4.4
FG_INV_ANOMALIES_WINDOW = FilterGroupId("fg-inv-anomalies-window")  # K.4.4

# ---------------------------------------------------------------------------
# Calculated fields
# ---------------------------------------------------------------------------

# Analysis-level calc field on the recipient-fanout dataset. Counts
# distinct senders per recipient over the current row scope (post date
# filter); the threshold NumericRangeFilter narrows visuals to recipients
# whose count crosses pInvFanoutThreshold.
CF_INV_FANOUT_DISTINCT_SENDERS = "recipient_distinct_sender_count"

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

P_INV_FANOUT_THRESHOLD = ParameterName("pInvFanoutThreshold")  # K.4.3
P_INV_ANOMALIES_SIGMA = ParameterName("pInvAnomaliesSigma")    # K.4.4

# ---------------------------------------------------------------------------
# Visual IDs
# ---------------------------------------------------------------------------

V_INV_FANOUT_KPI_RECIPIENTS = VisualId("inv-fanout-kpi-recipients")  # K.4.3
V_INV_FANOUT_KPI_SENDERS = VisualId("inv-fanout-kpi-senders")        # K.4.3
V_INV_FANOUT_KPI_AMOUNT = VisualId("inv-fanout-kpi-amount")          # K.4.3
V_INV_FANOUT_TABLE = VisualId("inv-fanout-table")                    # K.4.3

V_INV_ANOMALIES_KPI_FLAGGED = VisualId("inv-anomalies-kpi-flagged")  # K.4.4
V_INV_ANOMALIES_DISTRIBUTION = VisualId("inv-anomalies-distribution")  # K.4.4
V_INV_ANOMALIES_TABLE = VisualId("inv-anomalies-table")              # K.4.4
