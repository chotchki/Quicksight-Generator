"""Sasquatch AR demo scenarios — data-only fixture (M.2d.5 split).

The generic emit machinery (plant dataclasses, ``emit_seed``, every
``_emit_*_rows`` helper) lives in ``quicksight_gen.common.l2.seed`` so
M.3's ``sasquatch_pr_seed.py`` (and integrator-authored fixtures) can
reuse it. This file shrinks to one function: the canonical AR scenario
that pins the SHA256 hash test, names concrete customer DDA slugs, and
plants exactly enough to exercise each L1 invariant view.

Customer IDs reuse today's ``apps/account_recon/demo_data.py`` slugs
(``cust-900-0001-bigfoot-brews`` etc.) so cross-checking against the
existing AR demo's row counts stays straightforward.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from quicksight_gen.common.l2 import Identifier, Name
from quicksight_gen.common.l2.seed import (
    DriftPlant,
    LimitBreachPlant,
    OverdraftPlant,
    ScenarioPlant,
    StuckPendingPlant,
    StuckUnbundledPlant,
    SupersessionPlant,
    TemplateInstance,
)


def default_ar_scenario(today: date | None = None) -> ScenarioPlant:
    """The default M.2.2 scenario: one materialized DDA per planted
    exception, exactly enough to verify each L1 exception query surfaces
    a known row.

    Customer IDs reuse today's ``apps/account_recon/demo_data.py`` slugs
    (``cust-900-0001-bigfoot-brews`` etc.) so cross-checking against the
    existing AR demo's row counts stays straightforward.
    """
    today_ref = today or datetime.now(tz=timezone.utc).date()
    instances = (
        TemplateInstance(
            template_role=Identifier("CustomerDDA"),
            account_id=Identifier("cust-900-0001-bigfoot-brews"),
            name=Name("Bigfoot Brews — DDA"),
        ),
        TemplateInstance(
            template_role=Identifier("CustomerDDA"),
            account_id=Identifier("cust-900-0002-sasquatch-sips"),
            name=Name("Sasquatch Sips — DDA"),
        ),
        TemplateInstance(
            template_role=Identifier("CustomerDDA"),
            account_id=Identifier("cust-700-0001-big-meadow-dairy"),
            name=Name("Big Meadow Dairy — DDA"),
        ),
    )
    return ScenarioPlant(
        template_instances=instances,
        drift_plants=(
            DriftPlant(
                account_id=Identifier("cust-900-0001-bigfoot-brews"),
                days_ago=5,
                delta_money=Decimal("75.00"),  # +$75: stored is $75 too high
                rail_name=Identifier("CustomerInboundACH"),
                counter_account_id=Identifier("ext-frb-snb-master"),
            ),
        ),
        overdraft_plants=(
            OverdraftPlant(
                account_id=Identifier("cust-900-0002-sasquatch-sips"),
                days_ago=6,
                money=Decimal("-1500.00"),  # $1.5k overdrawn
            ),
        ),
        limit_breach_plants=(
            LimitBreachPlant(
                account_id=Identifier("cust-700-0001-big-meadow-dairy"),
                # Land inside the dashboard's default 7-day date-range
                # filter so the breach surfaces without the analyst
                # having to widen the picker. Drift = 5d, Overdraft =
                # 6d; staying under both keeps the bigger violation at
                # the recent end of the window.
                days_ago=4,
                transfer_type="wire",
                rail_name=Identifier("CustomerOutboundWire"),
                amount=Decimal("22000.00"),  # > $15k wire cap
                counter_account_id=Identifier("ext-frb-snb-master"),
            ),
        ),
        stuck_pending_plants=(
            # CustomerInboundACH carries `max_pending_age: PT24H`
            # (86400 seconds). Plant 2 days ago = 172800 seconds old =
            # comfortably past the cap, surfaces in stuck_pending.
            StuckPendingPlant(
                account_id=Identifier("cust-900-0001-bigfoot-brews"),
                days_ago=2,
                transfer_type="ach",
                rail_name=Identifier("CustomerInboundACH"),
                amount=Decimal("450.00"),
            ),
        ),
        stuck_unbundled_plants=(
            # CustomerFeeAccrual carries `max_unbundled_age: P31D`
            # (~2.68M seconds). Plant 35 days ago = comfortably past
            # the cap, surfaces in stuck_unbundled with bundle_id NULL.
            StuckUnbundledPlant(
                account_id=Identifier("cust-900-0002-sasquatch-sips"),
                days_ago=35,
                transfer_type="fee",
                rail_name=Identifier("CustomerFeeAccrual"),
                amount=Decimal("12.50"),
            ),
        ),
        supersession_plants=(
            # TechnicalCorrection on a recent posting — same logical id,
            # two entries (BIGSERIAL auto-versions). Surfaces in M.2b.12
            # Supersession Audit's transactions table.
            SupersessionPlant(
                account_id=Identifier("cust-900-0001-bigfoot-brews"),
                days_ago=3,
                transfer_type="ach",
                rail_name=Identifier("CustomerOutboundACH"),
                original_amount=Decimal("250.00"),
                corrected_amount=Decimal("275.00"),
            ),
        ),
        today=today_ref,
    )
