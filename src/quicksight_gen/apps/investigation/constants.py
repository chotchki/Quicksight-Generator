"""Shared IDs for Investigation sheets, datasets, filter groups, and
visual IDs.

Phase K.4.2 shipped the 4 sheet IDs. K.4.3 adds the Recipient Fanout
sheet's dataset, filter group, parameter, and visual IDs. K.4.4 adds
the Volume Anomalies sheet's IDs. K.4.5 adds the Money Trail sheet's
IDs (chain root parameter, max-hops slider, min-hop-amount slider,
Sankey + hop-by-hop table visuals). K.4.8 adds the Account Network
sheet (5th sheet) — two Sankeys side-by-side over the K.4.5 matview,
viewed account-centrically: left Sankey shows inbound edges
(counterparties → anchor), right Sankey shows outbound edges (anchor
→ counterparties), with the anchor visually meeting in the middle. A
full-width touching-edges table sits below for the unambiguous
walk-the-flow drill.
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
SHEET_INV_FANOUT = SheetId("inv-sheet-fanout")                # K.4.3
SHEET_INV_ANOMALIES = SheetId("inv-sheet-anomalies")          # K.4.4
SHEET_INV_MONEY_TRAIL = SheetId("inv-sheet-money-trail")      # K.4.5
SHEET_INV_ACCOUNT_NETWORK = SheetId("inv-sheet-account-network")  # K.4.8

# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

DS_INV_RECIPIENT_FANOUT = "inv-recipient-fanout-ds"          # K.4.3
DS_INV_VOLUME_ANOMALIES = "inv-volume-anomalies-ds"          # K.4.4
DS_INV_MONEY_TRAIL = "inv-money-trail-ds"                    # K.4.5
DS_INV_ACCOUNT_NETWORK = "inv-account-network-ds"            # K.4.8
# Narrow accounts dataset for the anchor dropdown only — K.4.8k. The
# main DS_INV_ACCOUNT_NETWORK wraps the matview with per-row concat
# (source_account_name||'('||source_account_id||')'); when QuickSight
# runs SELECT DISTINCT source_display against that wrapper the planner
# computes the concat over every matview row before dedupe — fine for a
# few hundred rows, slow enough to time out the dropdown as the matview
# grows. This dataset pushes the DISTINCT inside so PG dedupes the
# (id, name) pairs first and concats once per distinct account.
DS_INV_ANETWORK_ACCOUNTS = "inv-anetwork-accounts-ds"        # K.4.8k

# ---------------------------------------------------------------------------
# Filter groups
# ---------------------------------------------------------------------------

FG_INV_FANOUT_THRESHOLD = FilterGroupId("fg-inv-fanout-threshold")  # K.4.3
FG_INV_FANOUT_WINDOW = FilterGroupId("fg-inv-fanout-window")        # K.4.3
FG_INV_ANOMALIES_SIGMA = FilterGroupId("fg-inv-anomalies-sigma")    # K.4.4
FG_INV_ANOMALIES_WINDOW = FilterGroupId("fg-inv-anomalies-window")  # K.4.4
FG_INV_MONEY_TRAIL_ROOT = FilterGroupId("fg-inv-money-trail-root")  # K.4.5
FG_INV_MONEY_TRAIL_HOPS = FilterGroupId("fg-inv-money-trail-hops")  # K.4.5
FG_INV_MONEY_TRAIL_AMOUNT = FilterGroupId("fg-inv-money-trail-amount")  # K.4.5
FG_INV_ANETWORK_ANCHOR = FilterGroupId("fg-inv-anetwork-anchor")        # K.4.8 — table only
FG_INV_ANETWORK_INBOUND = FilterGroupId("fg-inv-anetwork-inbound")      # K.4.8 — inbound Sankey only
FG_INV_ANETWORK_OUTBOUND = FilterGroupId("fg-inv-anetwork-outbound")    # K.4.8 — outbound Sankey only
FG_INV_ANETWORK_AMOUNT = FilterGroupId("fg-inv-anetwork-amount")        # K.4.8

# ---------------------------------------------------------------------------
# Calculated fields
# ---------------------------------------------------------------------------

# Analysis-level calc field on the recipient-fanout dataset. Counts
# distinct senders per recipient over the current row scope (post date
# filter); the threshold NumericRangeFilter narrows visuals to recipients
# whose count crosses pInvFanoutThreshold.
CF_INV_FANOUT_DISTINCT_SENDERS = "recipient_distinct_sender_count"

# Analysis-level calc field on the account-network dataset. True when
# the edge's source OR target equals pInvANetworkAnchor — the way we
# express "any edge touching the anchor" in a single CategoryFilter.
# Scoped to the touching-edges table only; the two directional Sankeys
# each use their own direction-specific calc field below.
CF_INV_ANETWORK_IS_ANCHOR_EDGE = "is_anchor_edge"

# Direction-specific edge-touching calc fields. Each scoped to its own
# Sankey so the inbound/outbound layout does the direction-encoding
# visually rather than asking the analyst to read it off a node's
# position inside one big Sankey.
#   is_inbound_edge  — 'yes' when the edge's TARGET equals the anchor
#                      (the anchor received the money)
#   is_outbound_edge — 'yes' when the edge's SOURCE equals the anchor
#                      (the anchor sent the money)
CF_INV_ANETWORK_IS_INBOUND_EDGE = "is_inbound_edge"
CF_INV_ANETWORK_IS_OUTBOUND_EDGE = "is_outbound_edge"

# Analysis-level calc field on the account-network dataset. For any edge
# touching the anchor, one side IS the anchor by definition; this picks
# the OTHER side. Lets the table wire a single, unambiguous "Walk to
# other account" drill. Walking no longer happens from the Sankeys —
# each Sankey now shows only one direction, so the walk-from-node
# ambiguity is gone, and QuickSight's Sankey right-click drill isn't
# functional in practice anyway.
CF_INV_ANETWORK_COUNTERPARTY_DISPLAY = "counterparty_display"

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

P_INV_FANOUT_THRESHOLD = ParameterName("pInvFanoutThreshold")  # K.4.3
P_INV_ANOMALIES_SIGMA = ParameterName("pInvAnomaliesSigma")    # K.4.4
P_INV_MONEY_TRAIL_ROOT = ParameterName("pInvMoneyTrailRoot")   # K.4.5
P_INV_MONEY_TRAIL_MAX_HOPS = ParameterName("pInvMoneyTrailMaxHops")  # K.4.5
P_INV_MONEY_TRAIL_MIN_AMOUNT = ParameterName("pInvMoneyTrailMinAmount")  # K.4.5
P_INV_ANETWORK_ANCHOR = ParameterName("pInvANetworkAnchor")              # K.4.8
P_INV_ANETWORK_MIN_AMOUNT = ParameterName("pInvANetworkMinAmount")       # K.4.8

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

V_INV_MONEY_TRAIL_SANKEY = VisualId("inv-money-trail-sankey")        # K.4.5
V_INV_MONEY_TRAIL_TABLE = VisualId("inv-money-trail-table")          # K.4.5

V_INV_ANETWORK_SANKEY_INBOUND = VisualId("inv-anetwork-sankey-inbound")    # K.4.8
V_INV_ANETWORK_SANKEY_OUTBOUND = VisualId("inv-anetwork-sankey-outbound")  # K.4.8
V_INV_ANETWORK_TABLE = VisualId("inv-anetwork-table")                      # K.4.8
