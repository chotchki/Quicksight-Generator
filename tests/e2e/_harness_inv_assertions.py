"""Investigation matview assertions for the M.4.1 harness (N.3.l-bis / N.4.h).

Per-instance prefixed Investigation matview health checks. Mirrors
the shape of ``_harness_l1_assertions.py``:

- ``assert_inv_matviews_queryable`` — schema-health layer. Both
  Investigation matviews (``<prefix>_inv_pair_rolling_anomalies``
  and ``<prefix>_inv_money_trail_edges``) exist for the L2 instance
  prefix and can be queried. Catches v6 column-name regressions
  like the one surfaced in N.3.b — the SELECT fails immediately
  with the matview name in the error path.
- ``assert_inv_planted_rows_visible`` — plant-row visibility layer
  (N.4.h). Walks the manifest's ``inv_fanout_plants`` and asserts
  every (recipient, sender) edge surfaces in BOTH matviews. The
  fanout plant is the only Inv plant kind so far — adding
  InvAnomalyPlant / InvChainPlant (deferred N.4.h follow-up)
  extends this function with parallel queries against the same
  matviews.

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


def assert_inv_planted_rows_visible(
    db_conn: Any,
    prefix: str,
    planted_manifest: dict[str, list[dict[str, Any]]],
) -> None:
    """For every Investigation plant kind in the manifest, query the
    prefixed matview directly and assert the planted row surfaces.

    **Plant-row visibility layer of the harness for Investigation (N.4.h).**
    Mirrors ``assert_l1_matview_rows_present`` — fast-fail diagnostic
    that runs in <1s per plant before the Playwright dashboard render
    check. If this fails, the dashboard assertion would also fail, but
    the matview-side error message points straight at the seed/matview
    layer with the (recipient, sender) pair for triage.

    Each ``InvFanoutPlant`` produces N (sender, recipient) edges. We
    verify every edge surfaces in:

    - ``<prefix>_inv_pair_rolling_anomalies`` — at least one pair-rolling
      window row per (recipient, sender) pair. Day-grouping + rolling
      window may merge edges from the same day into one row, so the
      assertion is ``COUNT(*) >= 1`` per pair, not ``== N``.
    - ``<prefix>_inv_money_trail_edges`` — exactly one depth-0 edge per
      transfer. We assert ``COUNT(*) >= len(senders)`` since multiple
      edges per pair (multiple transfers) collapse into multiple rows.

    Args:
        db_conn: psycopg2 connection to the demo Aurora cluster.
        prefix: per-test L2 instance prefix (matches what
            ``apply_db_seed`` used).
        planted_manifest: ``build_planted_manifest`` output (from
            ``_harness_seed.build_planted_manifest``) — keyed by plant
            kind; the ``inv_fanout_plants`` entry drives this check.

    Raises:
        AssertionError: on the first planted (recipient, sender) pair
            whose row doesn't surface in the expected matview, with
            the matview name + pair + total row count for triage.
    """
    for plant in planted_manifest.get("inv_fanout_plants", []):
        recipient = plant["recipient_account_id"]
        senders = plant["sender_account_ids"]
        # Inv pair-rolling: one or more pair-window rows per (recipient, sender).
        anomalies_view = f"{prefix}_inv_pair_rolling_anomalies"
        for sender in senders:
            with db_conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM {anomalies_view} "
                    "WHERE recipient_account_id = %s AND sender_account_id = %s",
                    (recipient, sender),
                )
                row = cur.fetchone()
                count = row[0] if row else 0
                cur.execute(f"SELECT COUNT(*) FROM {anomalies_view}")
                total_row = cur.fetchone()
                total = total_row[0] if total_row else 0
            assert count >= 1, (
                f"Inv pair-rolling matview {anomalies_view!r} has no row "
                f"for planted fanout edge ({sender!r} → {recipient!r}) "
                f"— seed→matview-refresh pipeline regression. Total rows "
                f"in the matview: {total}.\n"
                f"plant: {plant!r}"
            )
        # Inv money-trail edges: each fanout transfer contributes one
        # depth-0 edge. Total rows for the recipient ≥ len(senders).
        edges_view = f"{prefix}_inv_money_trail_edges"
        with db_conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {edges_view} "
                "WHERE target_account_id = %s",
                (recipient,),
            )
            row = cur.fetchone()
            count = row[0] if row else 0
            cur.execute(f"SELECT COUNT(*) FROM {edges_view}")
            total_row = cur.fetchone()
            total = total_row[0] if total_row else 0
        assert count >= len(senders), (
            f"Inv money-trail matview {edges_view!r} has {count} rows "
            f"for planted recipient {recipient!r}, expected at least "
            f"{len(senders)} (one per fanout sender). Total rows in the "
            f"matview: {total}.\n"
            f"plant: {plant!r}"
        )
