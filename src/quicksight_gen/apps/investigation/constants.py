"""Shared IDs for Investigation sheets, datasets, filter groups, and
drill parameters.

Phase K.4.2 ships the skeleton: 4 sheet IDs (Getting Started + 3 stubs
named for K.4.3 / K.4.4 / K.4.5). Datasets, filter groups, visual IDs,
and drill parameters land per-sheet in K.4.3 onwards.
"""

from quicksight_gen.common.ids import SheetId

# Sheets
SHEET_INV_GETTING_STARTED = SheetId("inv-sheet-getting-started")
SHEET_INV_FANOUT = SheetId("inv-sheet-fanout")              # K.4.3
SHEET_INV_ANOMALIES = SheetId("inv-sheet-anomalies")        # K.4.4
SHEET_INV_MONEY_TRAIL = SheetId("inv-sheet-money-trail")    # K.4.5
