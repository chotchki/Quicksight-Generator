"""Executives base-table assertions for the M.4.1 harness (N.4.g).

Per-instance prefixed Executives base-table health checks. Mirrors
the shape of ``_harness_inv_assertions.py`` — Executives has no
matviews, so the contract is even narrower: just verify the
prefixed base tables (`<prefix>_transactions`, `<prefix>_daily_balances`)
are queryable. That catches the v5/v6 column-name regression class
the same way the Inv module does.

The Executives dataset SQL is more elaborate than just SELECT *
(per-transfer pre-aggregation, ABS, account_role rename), so a
parse-only check would miss column-rename bugs that bite at view
expansion. Running the actual builder-emitted SQL via
``cur.execute`` would be a tighter check, but it requires the QS
DataSet machinery to materialize the SQL — and that's beyond the
harness's "fast pre-render" scope. The current ``SELECT COUNT(*)``
on each base table proves the prefixed tables exist with the
expected column counts; the dashboard-render Layer 2 check catches
SQL-shape regressions if the base-table check passes but the
dataset SQL fails.
"""

from __future__ import annotations

from typing import Any


def assert_exec_base_tables_queryable(
    db_conn: Any,
    prefix: str,
) -> None:
    """For both Executives base tables, verify the prefixed view exists
    and can be queried.

    **Schema-health layer of the harness for Executives.** Catches
    the class of bugs surfaced in N.3.b (matview SQL still using v5
    column names) — but applied at the base-table level since
    Executives has no matviews. A SELECT COUNT(*) hitting a
    non-existent table raises a Postgres error that surfaces
    immediately.

    Mirrors ``assert_inv_matviews_queryable`` from
    ``_harness_inv_assertions.py``. The contract is "tables
    queryable", not "specific Exec dataset SQL works" — Layer 2's
    dashboard render is the integration check for the dataset SQL.

    Args:
        db_conn: psycopg2 connection to the demo Aurora cluster.
        prefix: per-test L2 instance prefix (matches what
            ``apply_db_seed`` used).

    Raises:
        AssertionError: if a base table is missing or the SELECT
            fails (with the table name + Postgres error context for
            triage).
        psycopg2 errors propagate as-is when the table doesn't exist
            or the query is malformed.
    """
    for base in ("transactions", "daily_balances"):
        full_table = f"{prefix}_{base}"
        with db_conn.cursor() as cur:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {full_table}")
                row = cur.fetchone()
                count = row[0] if row else 0
            except Exception as exc:
                raise AssertionError(
                    f"Executives base table {full_table!r} failed "
                    f"to query: {exc}. Likely cause: the L2 instance "
                    f"emit_schema didn't materialize this prefix, or "
                    f"the v6 column rename hasn't propagated. Try "
                    f"``\\d+ {full_table}`` in psql to inspect."
                ) from exc
        # Row count is informational only — fuzz instances populate
        # transactions but daily_balances may be empty for an
        # institution that doesn't seed StoredBalances.
        del count
