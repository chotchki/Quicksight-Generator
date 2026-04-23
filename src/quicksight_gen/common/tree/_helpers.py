"""Internal helpers shared across tree submodules.

Title / subtitle label builders + the action lists for QuickSight
Analysis / Dashboard ResourcePermissions. Lifted from the per-app
analysis modules so visual / control / structural nodes can reach
them without re-importing across submodules.

Plus shared ``Literal`` type aliases that more than one submodule
references (e.g. ``TimeGranularity``, used by both filters and
parameters). Pyright strict on ``common/tree/`` (L.1.20) catches
out-of-set values at the wiring site; no runtime guard needed.

Plus the ``AUTO`` sentinel — distinguishes "truly optional, may stay
unset at deploy" (``T | None``) from "must be filled in by
``App._resolve_auto_ids()`` before emit" (``T | AutoResolved``). What
used to be a single ``T | None`` slot for both cases now type-encodes
the difference: pyright narrows ``T | AutoResolved`` to ``T`` after
``assert not isinstance(x, _AutoSentinel)``, and a typo'd
``visual_id=None`` (where AUTO was meant) gets a red squiggle at the
wiring site.
"""

from __future__ import annotations

import enum
from typing import Final, Literal

from quicksight_gen.common.models import (
    VisualSubtitleLabelOptions,
    VisualTitleLabelOptions,
)


# ---------------------------------------------------------------------------
# AUTO sentinel — "this field will be filled in by App._resolve_auto_ids()"
# ---------------------------------------------------------------------------

class _AutoSentinel(enum.Enum):
    """Singleton sentinel — see ``AUTO`` below.

    Internal enum so pyright can narrow ``T | AutoResolved`` cleanly
    via ``isinstance`` / ``is AUTO`` checks. Single member; the enum
    machinery only matters for type narrowing.
    """
    AUTO = "auto"

    def __repr__(self) -> str:
        return "AUTO"


# Public sentinel value. ``KPI.visual_id: VisualId | AutoResolved = AUTO``
# means "App._resolve_auto_ids fills me in"; emit() asserts the resolver
# ran (``assert not isinstance(self.visual_id, _AutoSentinel)``) which
# narrows the type to ``VisualId``.
AUTO: Final = _AutoSentinel.AUTO

# Type alias — the resolved-later half of the union. Reads cleaner at
# field declarations than the bare ``Literal[_AutoSentinel.AUTO]``.
AutoResolved = Literal[_AutoSentinel.AUTO]


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
