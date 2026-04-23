"""Internal helpers shared across tree submodules.

Title / subtitle label builders + the action lists for QuickSight
Analysis / Dashboard ResourcePermissions. Lifted from the per-app
analysis modules so visual / control / structural nodes can reach
them without re-importing across submodules.

Plus shared ``Literal`` type aliases that more than one submodule
references (e.g. ``TimeGranularity``, used by both filters and
parameters). Pyright strict on ``common/tree/`` (L.1.20) catches
out-of-set values at the wiring site; no runtime guard needed.
"""

from __future__ import annotations

from typing import Literal

from quicksight_gen.common.models import (
    VisualSubtitleLabelOptions,
    VisualTitleLabelOptions,
)


# ---------------------------------------------------------------------------
# Shared Literal aliases
# ---------------------------------------------------------------------------

# QuickSight TimeGranularity — accepted on TimeRangeFilter, DateTimeParam,
# and a handful of date-binned visual config fields. Listed in the API
# docs for ColumnHierarchy / ParameterControlDateTimePicker / etc.; this
# codebase only uses "DAY" today, but the typed alias future-proofs the
# wrapper without locking us in.
TimeGranularity = Literal[
    "YEAR", "QUARTER", "MONTH", "WEEK",
    "DAY", "HOUR", "MINUTE", "SECOND", "MILLISECOND",
]


def title_label(text: str) -> VisualTitleLabelOptions:
    return VisualTitleLabelOptions(
        Visibility="VISIBLE", FormatText={"PlainText": text},
    )


def subtitle_label(text: str) -> VisualSubtitleLabelOptions:
    return VisualSubtitleLabelOptions(
        Visibility="VISIBLE", FormatText={"PlainText": text},
    )


# ResourcePermission action lists — match the per-app
# `_ANALYSIS_ACTIONS` / `_DASHBOARD_ACTIONS` lists used by the
# existing imperative builders.
ANALYSIS_ACTIONS = [
    "quicksight:DescribeAnalysis",
    "quicksight:DescribeAnalysisPermissions",
    "quicksight:UpdateAnalysis",
    "quicksight:UpdateAnalysisPermissions",
    "quicksight:DeleteAnalysis",
    "quicksight:QueryAnalysis",
    "quicksight:RestoreAnalysis",
]

DASHBOARD_ACTIONS = [
    "quicksight:DescribeDashboard",
    "quicksight:ListDashboardVersions",
    "quicksight:UpdateDashboardPermissions",
    "quicksight:QueryDashboard",
    "quicksight:UpdateDashboard",
    "quicksight:DeleteDashboard",
    "quicksight:DescribeDashboardPermissions",
    "quicksight:UpdateDashboardPublishedVersion",
    "quicksight:UpdateDashboardLinks",
]
