"""Internal helpers shared across tree submodules.

Title / subtitle label builders + the action lists for QuickSight
Analysis / Dashboard ResourcePermissions. Lifted from the per-app
analysis modules so visual / control / structural nodes can reach
them without re-importing across submodules.
"""

from __future__ import annotations

from quicksight_gen.common.models import (
    VisualSubtitleLabelOptions,
    VisualTitleLabelOptions,
)


def _title_label(text: str) -> VisualTitleLabelOptions:
    return VisualTitleLabelOptions(
        Visibility="VISIBLE", FormatText={"PlainText": text},
    )


def _subtitle_label(text: str) -> VisualSubtitleLabelOptions:
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
]
