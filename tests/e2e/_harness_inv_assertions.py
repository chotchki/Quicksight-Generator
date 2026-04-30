"""Investigation matview assertions for the M.4.1 harness (N.3.l-bis).

Per-instance prefixed Investigation matview health checks. Mirrors
the shape of ``_harness_l1_assertions.py`` but the contract is
narrower: Investigation has no planted-scenario manifest in the
harness fuzz instances (the Cascadia/Juniper-flavored Investigation
demo scenarios live in ``apps/investigation/demo_data.py`` and
weren't lifted to common/l2/seed.py — that's a deferred Phase O
candidate). So this module checks **schema health** rather than
**plant-row visibility**:

- Both Investigation matviews exist for the L2 instance prefix
  (``<prefix>_inv_pair_rolling_anomalies`` and
  ``<prefix>_inv_money_trail_edges``).
- Each matview can be queried (SELECT COUNT(*) succeeds — proves
  the matview body parses + executes against the prefixed base
  tables, catching v6 column-name regressions like the one
  surfaced in N.3.b).
- Returns the row count in the failure message for triage.

When the seed-data lift lands in a future phase, this module gains
a parallel ``assert_inv_plants_visible(...)`` that takes a planted
manifest and verifies specific Cascadia/Juniper-flavored rows
surface in the matviews. Until then, "matviews queryable" is the
bar.

Why this is a separate module: same shape as the L1 split — pure
DB-side assertions live alongside the L1 ones, browser/Playwright
assertions would land in a sibling module if/when Investigation
visibility checks are added.
"""

from __future__ import annotations

from typing import Any


# Investigation matview names without the L2 instance prefix.
# These mirror the CREATE MATERIALIZED VIEW names emitted by
# ``common.l2.schema._emit_inv_views`` (N.3.b).
INV_MATVIEW_NAMES: tuple[str, ...] = (
    "inv_pair_rolling_anomalies",
    "inv_money_trail_edges",
)


def assert_inv_matviews_queryable(
    db_conn: Any,
    prefix: str,
) -> None:
    """For every Investigation matview, verify the prefixed view
    exists and can be queried against the prefixed base tables.

    **Schema-health layer of the harness.** Catches the class of bugs
    surfaced in N.3.b (Inv matview SQL still using v5 column names
    like ``signed_amount`` against a v6 base table that has
    ``amount_money``). A SELECT COUNT(*) hitting a non-existent
    column raises a Postgres error that surfaces immediately, with
    the matview name in the error path so triage points straight at
    the schema layer.

    Mirrors the ``assert_l1_matview_rows_present`` shape from
    ``_harness_l1_assertions.py`` but the contract is narrower —
    we don't have planted Investigation scenarios in the fuzz
    manifests yet, so we can't assert "specific account_id surfaces".
    Once the demo seed lift to common/l2/seed.py lands (deferred
    Phase O), a parallel ``assert_inv_plants_visible`` joins this
    module.

    Args:
        db_conn: psycopg2 connection to the demo Aurora cluster.
        prefix: per-test L2 instance prefix (matches what
            ``apply_db_seed`` used).

    Raises:
        AssertionError: if a matview is missing or its body fails to
            execute against the prefixed base tables (with the
            matview name + Postgres error context for triage).
        psycopg2 errors propagate as-is when the matview SQL is
            structurally broken (e.g., missing column references).
    """
    for matview in INV_MATVIEW_NAMES:
        full_view = f"{prefix}_{matview}"
        with db_conn.cursor() as cur:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {full_view}")
                row = cur.fetchone()
                count = row[0] if row else 0
            except Exception as exc:
                raise AssertionError(
                    f"Investigation matview {full_view!r} failed to "
                    f"query: {exc}. Likely cause: matview body "
                    f"references a column that doesn't exist on the "
                    f"prefixed base table (v5/v6 column rename "
                    f"regression, see N.3.b for the canonical case). "
                    f"Try ``\\d+ {full_view}`` in psql to inspect."
                ) from exc
        # Row count is purely informational — Investigation matviews
        # may legitimately have zero rows on a fuzz instance whose
        # transactions don't satisfy the matview filter (e.g. no
        # leaf-internal recipient on any pair → empty
        # inv_pair_rolling_anomalies). The assertion is "the SELECT
        # works", not "rows are present".
        del count
