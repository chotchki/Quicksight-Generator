"""App Info ("i") sheet — diagnostic canary on every shipped dashboard.

Every L3 dashboard's last sheet is named "i" (App Info). It carries
three things:

1. **Liveness KPI** — `SELECT COUNT(*) FROM information_schema.tables
   WHERE table_schema = 'public'`. Real query, hits Aurora, never QS-
   cached (Direct Query). KPI shows a number → QS rendering pipeline
   works. KPI blank → QS itself is broken.
2. **Per-matview row count table** — caller-supplied list of matview
   names UNION'd into one dataset. Freshly-loaded matviews showing 0
   means the ETL hasn't refreshed them.
3. **Deploy stamp text box** — git short SHA + ISO timestamp baked
   at generate time so a viewer can tell which build of the dashboard
   they're looking at.

Diagnostic value: collapses the QS spinner-footgun ladder (Aurora
returns rows → describe_data_set CREATION_SUCCESSFUL → fresh incognito
→ assume QS broken; CLAUDE.md ops footgun) to a single glance at "i".

Usage from an app's `build_*_app(cfg, ...)`:

```python
from quicksight_gen.common.sheets.app_info import (
    APP_INFO_SHEET_NAME, APP_INFO_SHEET_TITLE, APP_INFO_SHEET_DESCRIPTION,
    DS_APP_INFO_LIVENESS, DS_APP_INFO_MATVIEWS,
    build_liveness_dataset, build_matview_status_dataset,
    populate_app_info_sheet,
)

# In _l1_datasets (or equivalent):
liveness_aws = build_liveness_dataset(cfg, app_segment="l1")
matviews_aws = build_matview_status_dataset(
    cfg, app_segment="l1",
    view_names=[f"{l2_prefix}_drift", f"{l2_prefix}_overdraft", ...],
)
liveness_ds = Dataset(identifier=DS_APP_INFO_LIVENESS,
                     arn=cfg.dataset_arn(liveness_aws.DataSetId))
matviews_ds = Dataset(identifier=DS_APP_INFO_MATVIEWS,
                     arn=cfg.dataset_arn(matviews_aws.DataSetId))

# As LAST sheet on the analysis:
app_info_sheet = analysis.add_sheet(Sheet(
    sheet_id=SheetId("<app>-sheet-app-info"),
    name=APP_INFO_SHEET_NAME,
    title=APP_INFO_SHEET_TITLE,
    description=APP_INFO_SHEET_DESCRIPTION,
))
populate_app_info_sheet(
    cfg, app_info_sheet,
    liveness_ds=liveness_ds, matview_status_ds=matviews_ds,
)
```
"""

from __future__ import annotations

import datetime as _dt
import subprocess

from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import (
    ColumnSpec,
    DatasetContract,
    build_dataset,
)
from quicksight_gen.common.models import DataSet
from quicksight_gen.common.l2 import ThemePreset
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.tree.datasets import Dataset
from quicksight_gen.common.tree.structure import Sheet
from quicksight_gen.common.tree.text_boxes import TextBox


APP_INFO_SHEET_NAME = "Info"  # Renamed from "i" — testing whether QS hides single-char tab names
APP_INFO_SHEET_TITLE = "App Info"
APP_INFO_SHEET_DESCRIPTION = (
    "Diagnostic canary. The Liveness KPI runs a real query against "
    "the database — if it shows a number, the QuickSight rendering "
    "pipeline is healthy and any blank visual on another sheet "
    "indicates a data or SQL issue. If the KPI is blank, QuickSight "
    "itself is broken."
)


# Visual identifiers — same string used by every app, registered once
# per process via the contract registry's identity-equality check.
DS_APP_INFO_LIVENESS = "app-info-liveness-ds"
DS_APP_INFO_MATVIEWS = "app-info-matviews-ds"


# Module-level contract instances — must be the same object every time
# `build_dataset()` is called, otherwise the registry rejects the
# second call with a different-instance error. Module-level singletons
# satisfy that.
LIVENESS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("table_count", "INTEGER"),
])

LIVENESS_SQL = (
    "SELECT COUNT(*) AS table_count "
    "FROM information_schema.tables "
    "WHERE table_schema = 'public'"
)


MATVIEW_STATUS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("view_name", "STRING"),
    ColumnSpec("row_count", "INTEGER"),
])


def _matview_status_sql(view_names: list[str]) -> str:
    """Build a UNION ALL query: one row per matview with its row count.

    Empty ``view_names`` returns a single placeholder row so the
    dataset always has rows — keeps the table from rendering blank
    on apps with zero monitored matviews (Executives today).
    """
    if not view_names:
        return (
            "SELECT '(no matviews registered)'::text AS view_name, "
            "0::integer AS row_count"
        )
    parts = [
        f"SELECT '{name}'::text AS view_name, "
        f"COUNT(*)::integer AS row_count FROM {name}"
        for name in view_names
    ]
    return "\nUNION ALL\n".join(parts)


def build_liveness_dataset(cfg: Config, *, app_segment: str) -> DataSet:
    """Trivial liveness query against information_schema.

    SQL is universal -- same bytes for every app. Returns one row
    with the count of public-schema tables.

    ``app_segment``: short kebab-case tag identifying which app owns
    this Dataset (e.g., ``"l1"``, ``"exec"``, ``"inv"``, ``"l2ft"``).
    Becomes part of the AWS DataSetId so each app gets its own
    physical dataset and ``deploy <single-app>`` doesn't delete-then-
    create another app's App Info dataset out from under it (M.4.4.7).
    The visual_identifier (``DS_APP_INFO_LIVENESS``) stays shared
    because it's analysis-internal — every app's analysis JSON has
    its own ``DataSetIdentifierDeclaration`` mapping the same logical
    name to its own per-app ARN.
    """
    return build_dataset(
        cfg,
        cfg.prefixed(f"{app_segment}-app-info-liveness-dataset"),
        "App Info -- Liveness",  # ASCII-only — testing QS em-dash hypothesis
        "app-info-liveness",
        LIVENESS_SQL,
        LIVENESS_CONTRACT,
        visual_identifier=DS_APP_INFO_LIVENESS,
    )


def build_matview_status_dataset(
    cfg: Config, *, app_segment: str, view_names: list[str],
) -> DataSet:
    """Per-matview row count table.

    ``view_names`` is the list of fully-qualified matview names to
    monitor (caller decides which ones matter for this app — typically
    the L1 invariant matviews + any app-specific ones, e.g. the L2-
    instance-prefixed names like ``sasquatch_ar_drift``).

    ``app_segment``: see ``build_liveness_dataset``.
    """
    return build_dataset(
        cfg,
        cfg.prefixed(f"{app_segment}-app-info-matviews-dataset"),
        "App Info -- Matview Status",  # ASCII-only
        "app-info-matviews",
        _matview_status_sql(view_names),
        MATVIEW_STATUS_CONTRACT,
        visual_identifier=DS_APP_INFO_MATVIEWS,
    )


def _git_short_sha() -> str:
    """Best-effort git short SHA at generate time. Returns ``"unknown"``
    if not in a repo or git unavailable.

    Intentionally swallows errors — the deploy stamp is informational
    and shouldn't block dashboard generation if the build environment
    lacks git (e.g., a wheel install on a server without source)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    return "unknown"


def _deploy_stamp() -> tuple[str, str]:
    """Return ``(git_short_sha, iso_timestamp)`` baked at generate time."""
    return (
        _git_short_sha(),
        _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
    )


# Layout constants — match the L1 dashboard's grid scale (36-col grid).
_FULL = 36
_HALF = 18
_TABLE_HEIGHT = 12
_TEXT_HEIGHT = 6


def populate_app_info_sheet(
    cfg: Config,
    sheet: Sheet,
    *,
    liveness_ds: Dataset,
    matview_status_ds: Dataset,
    theme: ThemePreset | None = None,
) -> None:
    """Populate the "i" sheet with three visuals (KPI + table + text box).

    Caller is responsible for registering the datasets on the App and
    for adding ``sheet`` to the Analysis as the LAST sheet (this helper
    doesn't enforce position because ``analysis.add_sheet`` order is
    the position).

    ``theme`` (N.1.e/f path): L2-fed apps (L1 + L2FT) pass the resolved
    L2 theme so the App Info accent matches the rest of the dashboard.
    Inv + Exec still call without the kwarg → fallback to
    ``cfg.theme_preset`` resolution. **TODO (N.3 / N.4):** drop the
    fallback once Inv + Exec migrate; ``theme`` becomes required.
    """
    accent = (theme or get_preset(cfg.theme_preset)).accent
    sha, ts = _deploy_stamp()

    # Row 1: liveness KPI (left half) + matview status table (right half).
    top = sheet.layout.row(height=_TABLE_HEIGHT)
    top.add_kpi(
        width=_HALF,
        title="Liveness",
        subtitle=(
            "Count of public-schema tables. Real query against the "
            "database via Direct Query -- if this shows a number, "
            "QuickSight's rendering pipeline is healthy. Blank means "
            "QuickSight itself is broken (not the data, not the SQL)."
        ),
        values=[liveness_ds["table_count"].sum()],
    )
    top.add_table(
        width=_HALF,
        title="Matview Status",
        subtitle=(
            "Row counts for materialized views the dashboard reads. "
            "Freshly-loaded matviews showing 0 means the ETL has not "
            "refreshed them yet."
        ),
        columns=[
            matview_status_ds["view_name"].dim(),
            matview_status_ds["row_count"].numerical(),
        ],
    )

    # Row 2: deploy stamp text box.
    sheet.layout.row(height=_TEXT_HEIGHT).add_text_box(
        TextBox(
            text_box_id="app-info-deploy-stamp",
            content=rt.text_box(
                rt.subheading("Deploy Stamp", color=accent),
                rt.BR,
                rt.body(f"git: {sha}"),
                rt.body(f"generated: {ts}"),
            ),
        ),
        width=_FULL,
    )
