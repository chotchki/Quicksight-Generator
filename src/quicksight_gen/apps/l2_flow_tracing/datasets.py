"""QuickSight DataSet builders for the L2 Flow Tracing app.

The Rails / Chains / L2 Exceptions tabs join L2-declared values
(static, from the L2 instance) to runtime activity (from the prefixed
``<prefix>_current_transactions`` matview). The L2 declarations are
inlined into the SQL as a CTE of literal rows — no per-rail dataset
proliferation, no per-instance database table.

Substep landmarks:

- M.3.4 — skeleton (no datasets)
- M.3.5 — Rails dataset (this commit)
- M.3.6 — Chains dataset
- M.3.7 — L2 Exceptions datasets (six small KPI-backers)
- M.3.8 — Auto metadata-driven filter dropdown sources
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import (
    ColumnSpec,
    DatasetContract,
    build_dataset,
)
from quicksight_gen.common.l2 import (
    L2Instance,
    SingleLegRail,
    TwoLegRail,
    posted_requirements_for,
)
from quicksight_gen.common.models import DataSet
from quicksight_gen.common.tree import Dataset


# Visual identifiers — keys for the Dataset registry on App.
DS_RAILS = "l2ft-rails-ds"


# Per-Rail row table — declared L2 columns + runtime activity counts.
RAILS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("rail_name", "STRING"),
    ColumnSpec("transfer_type", "STRING"),
    ColumnSpec("leg_shape", "STRING"),
    ColumnSpec("source_role", "STRING"),
    ColumnSpec("destination_role", "STRING"),
    ColumnSpec("leg_role", "STRING"),
    ColumnSpec("max_pending_age", "STRING"),
    ColumnSpec("max_unbundled_age", "STRING"),
    ColumnSpec("posted_requirements", "STRING"),
    ColumnSpec("total_postings", "INTEGER"),
    ColumnSpec("pending_count", "INTEGER"),
    ColumnSpec("unbundled_count", "INTEGER"),
])


# -- Builders ----------------------------------------------------------------


def build_all_l2_flow_tracing_datasets(
    cfg: Config, l2_instance: L2Instance,
) -> list[Dataset]:
    """Return every Dataset the L2 Flow Tracing app needs.

    Mirrors `build_all_l1_dashboard_datasets`: derives an L2-aware
    ``cfg`` (so dataset IDs carry the L2 instance prefix as their
    middle segment per M.2d.3) when the caller hasn't pre-stamped it.
    Idempotent — re-deriving an already-L2-aware cfg is a no-op.

    M.3.5 ships the Rails dataset; M.3.6+ adds Chains + L2 Exceptions.
    """
    if cfg.l2_instance_prefix is None:
        cfg = replace(cfg, l2_instance_prefix=str(l2_instance.instance))
    return [build_rails_dataset(cfg, l2_instance)]


def build_rails_dataset(cfg: Config, l2_instance: L2Instance) -> DataSet:
    """One row per declared Rail in the L2 instance.

    Static columns come from the L2 declaration (inlined as a VALUES CTE
    so the L2 stays out of the database). Runtime columns come from the
    ``<prefix>_current_transactions`` matview, aggregated per
    ``rail_name``. LEFT JOIN preserves Rails with zero activity in the
    window — those surface as L2.3 'Dead rails' on the Exceptions tab.

    Note: if multiple Rails share a ``transfer_type``, runtime counts
    on each row reflect the activity the matview attributes to THAT
    Rail's name (the schema's per-leg ``rail_name`` column makes the
    attribution unambiguous regardless of transfer_type sharing).
    """
    prefix = l2_instance.instance
    declared = _declared_rails_cte(l2_instance)
    sql = (
        f"WITH declared AS (\n{declared}\n),\n"
        f"runtime AS (\n"
        f"  SELECT\n"
        f"    rail_name,\n"
        f"    COUNT(*) AS total_postings,\n"
        f"    SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) AS pending_count,\n"
        f"    SUM(CASE WHEN bundle_id IS NULL THEN 1 ELSE 0 END) AS unbundled_count\n"
        f"  FROM {prefix}_current_transactions\n"
        f"  GROUP BY rail_name\n"
        f")\n"
        f"SELECT\n"
        f"  d.rail_name,\n"
        f"  d.transfer_type,\n"
        f"  d.leg_shape,\n"
        f"  d.source_role,\n"
        f"  d.destination_role,\n"
        f"  d.leg_role,\n"
        f"  d.max_pending_age,\n"
        f"  d.max_unbundled_age,\n"
        f"  d.posted_requirements,\n"
        f"  COALESCE(r.total_postings, 0) AS total_postings,\n"
        f"  COALESCE(r.pending_count, 0) AS pending_count,\n"
        f"  COALESCE(r.unbundled_count, 0) AS unbundled_count\n"
        f"FROM declared d\n"
        f"LEFT JOIN runtime r ON r.rail_name = d.rail_name\n"
        f"ORDER BY d.rail_name"
    )
    return build_dataset(
        cfg, cfg.prefixed("l2ft-rails-dataset"),
        "L2FT Rails", "l2ft-rails",
        sql, RAILS_CONTRACT,
        visual_identifier=DS_RAILS,
    )


# -- Internals ---------------------------------------------------------------


def _declared_rails_cte(l2_instance: L2Instance) -> str:
    """Render the L2-declared rails as a UNION ALL of SELECT-literal rows.

    UNION ALL of single-row SELECTs is used instead of ``VALUES (...)``
    so each column gets a CAST (or naked literal) that's resolved per
    row, avoiding the "type of column N is text but row M is null"
    inference problem PostgreSQL's planner sometimes hits with VALUES
    when most rows have NULL for a column.
    """
    if not l2_instance.rails:
        # Should not happen for a valid L2 (there must be some rails);
        # the validator would catch it. Return a safe empty CTE that
        # produces zero rows so the LEFT JOIN works.
        return (
            "  SELECT\n"
            "    NULL::TEXT AS rail_name,\n"
            "    NULL::TEXT AS transfer_type,\n"
            "    NULL::TEXT AS leg_shape,\n"
            "    NULL::TEXT AS source_role,\n"
            "    NULL::TEXT AS destination_role,\n"
            "    NULL::TEXT AS leg_role,\n"
            "    NULL::TEXT AS max_pending_age,\n"
            "    NULL::TEXT AS max_unbundled_age,\n"
            "    NULL::TEXT AS posted_requirements\n"
            "  WHERE FALSE"
        )
    rows: list[str] = []
    for r in l2_instance.rails:
        leg_shape = _leg_shape(r)
        if isinstance(r, TwoLegRail):
            source_role = _role_str(r.source_role)
            destination_role = _role_str(r.destination_role)
            leg_role = None
        else:
            source_role = None
            destination_role = None
            leg_role = _role_str(r.leg_role)
        max_pending = _duration_label(r.max_pending_age)
        max_unbundled = _duration_label(r.max_unbundled_age)
        posted_reqs = ",".join(
            sorted(str(k) for k in posted_requirements_for(l2_instance, r.name))
        )
        rows.append(
            "  SELECT "
            f"{_sql_str(str(r.name))} AS rail_name, "
            f"{_sql_str(str(r.transfer_type))} AS transfer_type, "
            f"{_sql_str(leg_shape)} AS leg_shape, "
            f"{_sql_nullable_str(source_role)} AS source_role, "
            f"{_sql_nullable_str(destination_role)} AS destination_role, "
            f"{_sql_nullable_str(leg_role)} AS leg_role, "
            f"{_sql_nullable_str(max_pending)} AS max_pending_age, "
            f"{_sql_nullable_str(max_unbundled)} AS max_unbundled_age, "
            f"{_sql_str(posted_reqs)} AS posted_requirements"
        )
    return "\n  UNION ALL\n".join(rows)


def _leg_shape(rail: TwoLegRail | SingleLegRail) -> str:
    """Compact label combining leg arity + aggregating flag.

    Examples: "1-leg" / "2-leg" / "1-leg-aggregating" / "2-leg-aggregating".
    """
    arity = "2-leg" if isinstance(rail, TwoLegRail) else "1-leg"
    return f"{arity}-aggregating" if rail.aggregating else arity


def _role_str(role: tuple) -> str:
    """Render a RoleExpression (tuple of Identifiers) as a display string.

    Single-role: the name. UNION (multi-role): joined with " | " (the
    SPEC's union-set notation)."""
    parts = [str(r) for r in role]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return " | ".join(parts)


def _duration_label(td: timedelta | None) -> str | None:
    """Render a timedelta as a compact label ("24h", "1d", "30m").

    None → None (the SQL emits NULL). Non-evenly-divisible durations
    fall back to seconds.
    """
    if td is None:
        return None
    s = int(td.total_seconds())
    if s == 0:
        return "0s"
    if s % 86400 == 0:
        return f"{s // 86400}d"
    if s % 3600 == 0:
        return f"{s // 3600}h"
    if s % 60 == 0:
        return f"{s // 60}m"
    return f"{s}s"


def _sql_str(value: str) -> str:
    """Escape a Python string for embedding as a SQL string literal.

    Doubles single quotes per SQL standard (works on PostgreSQL +
    portable to other RDBMS per the project's portability constraint)."""
    return "'" + value.replace("'", "''") + "'"


def _sql_nullable_str(value: str | None) -> str:
    """SQL literal for an optional string — emits NULL when None."""
    if value is None:
        return "NULL"
    return _sql_str(value)
