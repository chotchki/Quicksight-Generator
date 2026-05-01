"""DB-side seeding helpers for the M.4.1 end-to-end harness (M.4.1.b).

Two surfaces:

1. ``apply_db_seed(conn, instance, *, mode, today)`` — runs the full
   DB-side flow against an open psycopg2 connection: emit_schema
   (drop + create), emit_seed (insert plants), refresh_matviews_sql
   (recompute every L1 + L2 dashboard matview). Returns the
   ``ScenarioPlant`` so the caller can build the planted_manifest.

2. ``build_planted_manifest(scenario)`` — walks the scenario's plant
   tuples and produces a triage-friendly dict whose entries are the
   key columns Playwright assertions need to find the planted row on
   the right dashboard sheet (drift account_id + delta_money,
   stuck_pending account_id + transfer_type + posted_age, etc.).
   Lifted to a separate function so M.4.1.f's failure manifest dump
   has the same shape the assertions consume.

Why this is its own module instead of inline-in-the-harness: both
helpers are unit-testable against mock psycopg2 / pure-data scenarios
without spinning up Aurora. The real-DB integration smoke happens via
the harness fixture itself (M.4.1.b), gated behind QS_GEN_E2E=1.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from quicksight_gen.common.db import execute_script
from quicksight_gen.common.l2 import (
    L2Instance,
    emit_schema,
    refresh_matviews_sql,
)
from quicksight_gen.common.l2.auto_scenario import (
    ScenarioMode,
    add_broken_rail_plants,
    boost_inv_fanout_plants,
    default_scenario_for,
    densify_scenario,
)
from quicksight_gen.common.l2.seed import (
    ScenarioPlant,
    emit_full_seed,
    emit_seed,
)
from quicksight_gen.common.sql import Dialect


# Canonical reference date pinned across harness runs so the seed's
# day-staggered timestamps land at the same point in the dashboard's
# rolling 7-day window every time. M.2a.8's hash-lock convention.
DEFAULT_HARNESS_TODAY = date(2030, 1, 1)


def apply_db_seed(
    conn: Any,
    instance: L2Instance,
    *,
    mode: ScenarioMode = "l1_plus_broad",
    today: date | None = None,
    dialect: Dialect = Dialect.POSTGRES,
    include_baseline: bool = False,
) -> ScenarioPlant:
    """Apply schema + seed + matview refresh against ``conn``.

    Three DB-side steps in order, each committed independently so a
    mid-flow failure leaves the prefixed objects in a known state for
    the harness teardown to drop cleanly. Routes every multi-statement
    script through ``common/db.execute_script`` so Oracle's per-statement
    + PL/SQL-block execution works alongside Postgres's atomic-script
    behavior (P.9d).

    Returns the ``ScenarioPlant`` so the caller can pass it to
    ``build_planted_manifest`` for the harness's per-test triage
    manifest (M.4.1.f).

    Args:
      include_baseline (R.5.b): when True, the seed step uses
        ``emit_full_seed`` + the densify+broken+boost pipeline that the
        CLI's ``demo apply`` uses. Adds ~60k baseline rows on top of
        the lean planted scenarios. Required for R.5.d coverage tests
        that assert per-Rail / per-Chain runtime evidence (the lean
        scenario only fires the rails it explicitly plants on). Default
        False preserves the legacy harness behavior — fast feedback,
        plants only.
    """
    today_ref = today or DEFAULT_HARNESS_TODAY

    # 1. Schema.
    schema_sql = emit_schema(instance, dialect=dialect)
    with conn.cursor() as cur:
        execute_script(cur, schema_sql, dialect=dialect)
    conn.commit()

    # 2. Seed (mode-aware via M.4.2).
    report = default_scenario_for(instance, today=today_ref, mode=mode)
    if include_baseline:
        # Match what cli._apply_demo does so harness assertions see the
        # full demo pipeline (densify → broken-rail → boost → baseline).
        scenario = boost_inv_fanout_plants(
            add_broken_rail_plants(
                densify_scenario(report.scenario, factor=5),
                instance, broken_count=15,
            ),
            amount_multiplier=5,
        )
        seed_sql = emit_full_seed(
            instance, scenario, anchor=today_ref, dialect=dialect,
        )
    else:
        scenario = report.scenario
        seed_sql = emit_seed(instance, scenario, dialect=dialect)
    with conn.cursor() as cur:
        execute_script(cur, seed_sql, dialect=dialect)
    conn.commit()

    # 3. Refresh matviews.
    refresh_sql = refresh_matviews_sql(instance, dialect=dialect)
    with conn.cursor() as cur:
        execute_script(cur, refresh_sql, dialect=dialect)
    conn.commit()

    return scenario


# ---------------------------------------------------------------------------
# planted_manifest builder
# ---------------------------------------------------------------------------


# A planted_manifest is a dict keyed by plant-kind name; each value is
# a list of dicts capturing the columns Playwright needs to find the
# planted row in the deployed dashboard. Listed plant-kind names match
# the attribute names on ScenarioPlant for one-to-one cross-reference.
PlantManifestEntry = dict[str, str | int | Decimal | tuple[str, ...] | None]
PlantedManifest = dict[str, list[PlantManifestEntry]]

_AllPlantKinds = Literal[
    "drift_plants",
    "overdraft_plants",
    "limit_breach_plants",
    "stuck_pending_plants",
    "stuck_unbundled_plants",
    "supersession_plants",
    "transfer_template_plants",
    "rail_firing_plants",
]


def build_planted_manifest(scenario: ScenarioPlant) -> PlantedManifest:
    """Walk ``scenario`` and produce the per-plant-kind row-finder dict.

    Each plant-kind list contains the minimum columns a Playwright
    assertion needs to assert "this row appeared on the right sheet".
    Field names match the dataclass attributes on the source plant
    types in ``common/l2/seed.py`` for one-to-one cross-reference.

    Plants the scenario didn't materialize map to empty lists — the
    M.4.1.b–e harness substeps can iterate every entry with
    ``for entry in manifest.get('drift_plants', []): ...`` and
    naturally skip missing kinds.
    """
    return {
        "drift_plants": [
            {
                "account_id": str(p.account_id),
                "days_ago": p.days_ago,
                "delta_money": p.delta_money,
                "rail_name": str(p.rail_name),
            }
            for p in scenario.drift_plants
        ],
        "overdraft_plants": [
            {
                "account_id": str(p.account_id),
                "days_ago": p.days_ago,
                "money": p.money,
            }
            for p in scenario.overdraft_plants
        ],
        "limit_breach_plants": [
            {
                "account_id": str(p.account_id),
                "days_ago": p.days_ago,
                "transfer_type": p.transfer_type,
                "rail_name": str(p.rail_name),
                "amount": p.amount,
            }
            for p in scenario.limit_breach_plants
        ],
        "stuck_pending_plants": [
            {
                "account_id": str(p.account_id),
                "days_ago": p.days_ago,
                "transfer_type": p.transfer_type,
                "rail_name": str(p.rail_name),
                "amount": p.amount,
            }
            for p in scenario.stuck_pending_plants
        ],
        "stuck_unbundled_plants": [
            {
                "account_id": str(p.account_id),
                "days_ago": p.days_ago,
                "transfer_type": p.transfer_type,
                "rail_name": str(p.rail_name),
                "amount": p.amount,
            }
            for p in scenario.stuck_unbundled_plants
        ],
        "supersession_plants": [
            {
                "account_id": str(p.account_id),
                "days_ago": p.days_ago,
                "transfer_type": p.transfer_type,
                "rail_name": str(p.rail_name),
                "original_amount": p.original_amount,
                "corrected_amount": p.corrected_amount,
            }
            for p in scenario.supersession_plants
        ],
        "transfer_template_plants": [
            {
                "template_name": str(p.template_name),
                "days_ago": p.days_ago,
                "firing_seq": p.firing_seq,
                "amount": p.amount,
            }
            for p in scenario.transfer_template_plants
        ],
        "rail_firing_plants": [
            {
                "rail_name": str(p.rail_name),
                "days_ago": p.days_ago,
                "firing_seq": p.firing_seq,
                "transfer_parent_id": p.transfer_parent_id,
                "template_name": (
                    str(p.template_name) if p.template_name is not None
                    else None
                ),
            }
            for p in scenario.rail_firing_plants
        ],
        "inv_fanout_plants": [
            {
                "recipient_account_id": str(p.recipient_account_id),
                "sender_account_ids": tuple(
                    str(sid) for sid in p.sender_account_ids
                ),
                "days_ago": p.days_ago,
                "transfer_type": p.transfer_type,
                "rail_name": str(p.rail_name),
                "amount_per_transfer": p.amount_per_transfer,
            }
            for p in scenario.inv_fanout_plants
        ],
    }
