"""AA.A.6 — generic additive-pickers row-survival infrastructure.

Picker-anchor pattern for sheets with ≥2 pickers: open the sheet,
query the DB for a known-good row that satisfies every picker's bound
column, drive each picker to that row's values *additively* (i.e.
without clearing between picks), assert the anchor row survives in
the target table visual.

Why DB-direct instead of "pick first option from each dropdown":
some pickers bind columns that aren't in the displayed table (Daily
Statement's Role narrows the account dropdown's source; Today's
Exceptions' Check Type filters a UNION-shape). Reading the anchor
value from the displayed table cells works only when every picker's
column is on-table; the DB-query path generalizes across both cases
without depending on seed luck (the AA.B.5.followon calendar-luck
regression is the precedent — picking ``options[0]`` and inheriting
the date picker's default produced a thin-data combination on chains
that crossed UTC midnight). Spike resolution locked 2026-05-17 at
PLAN.md AA.A.6.

The shape mirrors `_daily_statement_pick.py::find_account_day_with_data`
generalized — that helper is Daily-Statement-specific and predates this
infra; the generic helper here covers sheets where we don't already
have a bespoke picker. Daily Statement keeps its dedicated helper for
the cascade-pick flow it tests; new sheets without bespoke coverage
land here.

Dialect-aware via the existing ``Dialect`` enum on cfg; only PG +
Oracle are wired (matches the runner's `aw` target shape — QS can't
reach a sqlite tempfile).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import psycopg

from recon_gen.common.config import Config
from recon_gen.common.sql.dialect import Dialect


PickerKind = Literal["dropdown", "datetime", "date_from", "date_to", "slider"]


@dataclass(frozen=True)
class PickerSpec:
    """One picker's wiring on a sheet.

    ``label`` matches the UI control title (``ParameterDropdown.title``
    or equivalent) — what the driver sees as the picker name.

    ``kind`` selects how the picker is driven:

    - ``"dropdown"`` — single-value pick via ``driver.pick_filter``.
    - ``"date_from"`` / ``"date_to"`` — bounds of the universal date
      range; both drive the same row's date column. Both must appear
      in the spec when the sheet has a universal date range; one alone
      would set an open-bound which isn't what "narrow to the anchor's
      day" means.
    - ``"datetime"`` — single-value date picker via ``driver.set_date``
      (e.g. Daily Statement's Business Day).
    - ``"slider"`` — single-value slider via ``driver.set_slider``. The
      anchor value sets both bounds (lo == hi == value) so the slider
      narrows to exactly the anchor's value.

    ``column`` is the source column in the anchor row (a key into the
    dict returned by ``fetch_anchor_row``). For the typical "picker's
    bound column == anchor source column" shape this is just the column
    name; for derived values (e.g. account_display concat) use
    ``format`` to derive the picker value from multiple anchor columns.

    ``format`` (optional) maps the anchor dict to the picker's expected
    value. Default = ``str(anchor[column])``. Use it for:

    - Account-display dropdowns: ``f"{row['account_name']} ({row['account_id']})"``
    - Dates that need ISO formatting: ``row['business_day'].isoformat()``
    - Any other anchor-to-picker-value transformation.
    """
    label: str
    kind: PickerKind
    column: str
    format: object = field(default=None)  # Callable[[Mapping[str, Any]], str] | None — typed as object to avoid pyright generic-callable infer noise


@dataclass(frozen=True)
class SheetAnchorSpec:
    """A sheet's anchor + pickers config for the generic survival test.

    ``sheet_name`` matches the L1/L2FT/Inv/Exec sheet's display name
    (== ``Sheet.name`` from the tree).

    ``target_visual`` is the table whose row-count we assert ``>= 1``
    after all pickers are driven. Pick the canonical detail table —
    the Drift sheet has two (Leaf + Parent), use the dominant one
    most analysts land on.

    ``anchor_table`` is the SQL table the anchor row comes from (the
    matview the target visual reads from, formatted with ``{p}`` for
    the cfg's ``db_table_prefix``). The query selects ``anchor_columns``
    from this table ordered by ``anchor_order`` and takes the first row.

    ``anchor_columns`` are the columns the anchor SELECT projects —
    one per ``PickerSpec.column`` plus any auxiliary columns the
    formatters need.

    ``anchor_order`` biases the anchor pick: typically
    ``"business_day_start DESC"`` so the anchor lands on a recent day
    (matches what an analyst would naturally see open). Empty string =
    arbitrary first row.

    ``pickers`` is the tuple of picker wirings. All must be drivable
    from the anchor row (i.e. ``column`` in ``anchor_columns``).
    """
    sheet_name: str
    target_visual: str
    anchor_table: str  # ``"{p}_drift"`` — formatted with cfg.db_table_prefix
    anchor_columns: tuple[str, ...]
    anchor_order: str
    pickers: tuple[PickerSpec, ...]


def fetch_anchor_row(cfg: Config, spec: SheetAnchorSpec) -> Mapping[str, Any]:
    """Run ``spec``'s anchor SELECT against ``cfg.demo_database_url``
    and return the first row as a column→value dict.

    Raises ``RuntimeError`` when the anchor table is empty (deploy step
    skipped? wrong cfg? wrong prefix?) — refusing to silently return
    a useless tuple, same shape as ``find_account_day_with_data``.

    Only Postgres + Oracle are wired; the AW-target browser e2e cells
    only run against those two dialects.
    """
    if cfg.dialect not in (Dialect.POSTGRES, Dialect.ORACLE):
        raise RuntimeError(
            f"fetch_anchor_row: unsupported dialect {cfg.dialect!r} — "
            f"only Postgres + Oracle wired"
        )
    if not cfg.demo_database_url:
        raise RuntimeError("fetch_anchor_row: cfg.demo_database_url is unset")

    table = spec.anchor_table.format(p=cfg.db_table_prefix)
    cols = ", ".join(spec.anchor_columns)
    order_clause = f"ORDER BY {spec.anchor_order} " if spec.anchor_order else ""
    limit_clause = (
        "LIMIT 1" if cfg.dialect is Dialect.POSTGRES else "FETCH FIRST 1 ROWS ONLY"
    )
    sql = f"SELECT {cols} FROM {table} {order_clause}{limit_clause}"

    with psycopg.connect(cfg.demo_database_url, connect_timeout=60) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            f"fetch_anchor_row: {table} returned zero rows. Deploy "
            f"skipped? Wrong cfg? Wrong prefix? Check the chain's "
            f"seed/db layers — the matview may legitimately be empty "
            f"if the scenario plants no violations for this sheet."
        )
    return dict(zip(spec.anchor_columns, row, strict=True))


def picker_value(
    spec: PickerSpec, anchor: Mapping[str, Any],
) -> str:
    """Resolve a picker's drive-value from the anchor row.

    Calls ``spec.format(anchor)`` when set; otherwise stringifies
    ``anchor[spec.column]``. ISO-formats date/datetime values for the
    driver protocol (which expects ``YYYY-MM-DD``).
    """
    if spec.format is not None:
        return spec.format(anchor)  # type: ignore[operator,no-any-return]: format is callable-shaped at the call site

    value = anchor[spec.column]
    if hasattr(value, "isoformat"):  # date / datetime
        iso: str = value.isoformat()
        # date_from/date_to/datetime want YYYY-MM-DD; trim time part if present
        return iso.split("T")[0]
    return str(value)


def apply_anchor_to_pickers(
    driver: Any, spec: SheetAnchorSpec, anchor: Mapping[str, Any],
) -> None:
    """Drive every picker in ``spec.pickers`` to the anchor's values,
    *additively* (don't clear between picks).

    The driver verb depends on each picker's ``kind``:

    - ``dropdown`` → ``driver.pick_filter(label, [value])``
    - ``date_from`` / ``date_to`` → batched into one
      ``driver.set_date_range(from_, to)`` call after both bounds are
      collected (the protocol takes both bounds at once).
    - ``datetime`` → ``driver.set_date(label, iso)``
    - ``slider`` → ``driver.set_slider(label, value, value)`` (lo==hi
      narrows to exactly the anchor value).

    Blocks until each affected visual re-fetches (the driver verbs all
    do their own WS-settle waits — see ``DashboardDriver`` docstring).
    """
    date_from: str | None = None
    date_to: str | None = None

    for p in spec.pickers:
        value = picker_value(p, anchor)
        if p.kind == "dropdown":
            driver.pick_filter(p.label, [value])
        elif p.kind == "datetime":
            driver.set_date(p.label, value)
        elif p.kind == "slider":
            num = float(value)
            driver.set_slider(p.label, num, num)
        elif p.kind == "date_from":
            date_from = value
        elif p.kind == "date_to":
            date_to = value
        else:  # pragma: no cover — Literal exhausted above
            raise ValueError(f"unknown picker kind: {p.kind!r}")

    # Universal date range collapses to one call; date_from + date_to
    # must arrive together (an open-bound on one side wouldn't narrow
    # to the anchor's day).
    if date_from is not None or date_to is not None:
        if date_from is None or date_to is None:
            raise ValueError(
                f"spec {spec.sheet_name!r} has only one of "
                f"date_from / date_to. Both required for the anchor "
                f"narrow to be well-defined."
            )
        driver.set_date_range(date_from, date_to)
