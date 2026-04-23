"""Internal helpers shared across tree submodules.

Title / subtitle label builders + the action lists for QuickSight
Analysis / Dashboard ResourcePermissions. Lifted from the per-app
analysis modules so visual / control / structural nodes can reach
them without re-importing across submodules.

Plus shared ``Literal`` type aliases that more than one submodule
references (e.g. ``TimeGranularity``, used by both filters and
parameters), and the ``_validate_literal`` runtime guard that backs
them — this codebase has no pyright/mypy configured, so a typed
``Literal`` field alone wouldn't catch typos at construction time.
``_validate_literal`` closes that gap by checking ``typing.get_args``
in ``__post_init__``.
"""

from __future__ import annotations

import typing
from typing import Any, Literal

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


# ---------------------------------------------------------------------------
# Runtime Literal validation
# ---------------------------------------------------------------------------

def _validate_literal(value: Any, literal_type: Any, *, field_name: str) -> None:
    """Reject ``value`` if it isn't one of ``literal_type``'s allowed args.

    Pass ``None`` through (callers can declare ``Literal[...] | None`` and
    leave the field optional). Use in ``__post_init__`` for tree wrappers
    whose field type is a ``Literal`` — the runtime check substitutes for
    the absent type checker.

    Example::

        def __post_init__(self) -> None:
            _validate_literal(
                self.time_granularity, TimeGranularity,
                field_name="time_granularity",
            )
    """
    if value is None:
        return
    args = typing.get_args(literal_type)
    if value not in args:
        raise ValueError(
            f"{field_name}={value!r} not in {list(args)}"
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
    "quicksight:UpdateDashboardLinks",
]
