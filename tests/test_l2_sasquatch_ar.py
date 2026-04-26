"""Smoke + structural tests for ``tests/l2/sasquatch_ar.yaml`` — the
first real-app L2 instance (M.2.1 — port of today's AR CMS demo).

These are intentionally narrow: load + validate + assert the structural
shape M.2's downstream substeps depend on (account count, rail set,
limit set, every primitive carries a description). Behavioural
correctness (does drift / overdraft / limit-breach actually surface
on the deployed dashboard?) lives in M.2.6's integration test against
real Postgres.

The fixture is loaded once via ``functools.cache``; every test reads
the same in-memory ``L2Instance``.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pytest

from quicksight_gen.common.l2 import (
    L2Instance,
    SingleLegRail,
    TwoLegRail,
    load_instance,
    validate,
)


YAML_PATH = Path(__file__).parent / "l2" / "sasquatch_ar.yaml"


@functools.cache
def _instance() -> L2Instance:
    """Cached load — tests share one in-memory instance."""
    return load_instance(YAML_PATH)


def test_loads_and_validates_cleanly() -> None:
    """The fixture passes the full validator suite (24 rules)."""
    inst = _instance()
    validate(inst)
    assert inst.instance == "sasquatch_ar"


def test_top_level_description_present() -> None:
    """Top-level instance prose powers the M.7 handbook overview page."""
    inst = _instance()
    assert inst.description is not None
    assert "Sasquatch National Bank" in inst.description
    assert "Cash Management Suite" in inst.description


# -- Account topology --------------------------------------------------------


def test_eight_internal_gl_singletons_present() -> None:
    """The eight-GL chart-of-accounts shape per CLAUDE.md / today's AR demo."""
    inst = _instance()
    internals = [a for a in inst.accounts if a.scope == "internal"]
    assert len(internals) == 8
    expected_roles = {
        "CashDueFRB",
        "ACHOrigSettlement",
        "CardAcquiringSettlement",
        "WireSettlementSuspense",
        "InternalTransferSuspense",
        "ConcentrationMaster",
        "InternalSuspenseRecon",
        "DDAControl",
    }
    actual_roles = {a.role for a in internals}
    assert actual_roles == expected_roles


def test_five_external_counterparties_share_role() -> None:
    """All externals share one Role — AR doesn't functionally distinguish them."""
    inst = _instance()
    externals = [a for a in inst.accounts if a.scope == "external"]
    assert len(externals) == 5
    assert all(a.role == "ExternalCounterparty" for a in externals)


def test_two_account_templates_with_singleton_parents() -> None:
    """CustomerDDA + ZBASubAccount; each parent_role resolves to a singleton (R3)."""
    inst = _instance()
    template_roles = {t.role for t in inst.account_templates}
    assert template_roles == {"CustomerDDA", "ZBASubAccount"}
    template_by_role = {t.role: t for t in inst.account_templates}
    assert template_by_role["CustomerDDA"].parent_role == "DDAControl"
    assert template_by_role["ZBASubAccount"].parent_role == "ConcentrationMaster"


# -- Rails -------------------------------------------------------------------


def test_sixteen_rails_covering_known_flows() -> None:
    """The full rail set covering 6 directional Customer<->External rails,
    on-us internal cycle (3 single-leg rails wrapped in a TransferTemplate),
    ZBA sweep, Concentration→FRB, fee accrual + monthly settlement
    (aggregating), ACH origination daily sweep (aggregating), and 2 ACH
    return rails (XOR group)."""
    inst = _instance()
    expected = {
        # Customer <-> External
        "CustomerInboundACH",
        "CustomerOutboundACH",
        "CustomerInboundWire",
        "CustomerOutboundWire",
        "CustomerCashDeposit",
        "CustomerCashWithdrawal",
        # On-us internal cycle (3 single-leg rails, joined by template)
        "InternalTransferDebit",
        "InternalTransferCredit",
        "InternalTransferSuspenseClose",
        # Operational sweeps
        "ZBASweep",
        "ConcentrationToFRBSweep",
        # Aggregating rails
        "ACHOriginationDailySweep",
        "CustomerFeeMonthlySettlement",
        # Single-leg bundled by aggregating
        "CustomerFeeAccrual",
        # ACH return XOR-group children
        "CustomerInboundACHReturnNSF",
        "CustomerInboundACHReturnStopPay",
    }
    actual = {r.name for r in inst.rails}
    assert actual == expected


def test_inbound_rails_use_per_leg_origin_overrides() -> None:
    """External-driven rails set ``source_origin: ExternalForcePosted`` on
    the external leg and ``destination_origin: InternalInitiated`` on the
    internal leg — NOT a rail-level ``origin``. Validator's O1 rule
    accepts this because both legs resolve via per-leg overrides."""
    inst = _instance()
    by_name = {r.name: r for r in inst.rails}
    inbound = by_name["CustomerInboundACH"]
    assert isinstance(inbound, TwoLegRail)
    assert inbound.origin is None
    assert inbound.source_origin == "ExternalForcePosted"
    assert inbound.destination_origin == "InternalInitiated"


def test_outbound_rails_use_rail_level_origin() -> None:
    """SNB-driven outbound rails set rail-level ``origin: InternalInitiated`` —
    both legs are SNB-initiated until the Fed eventually force-posts a
    later settlement. The settlement isn't modeled as the same rail."""
    inst = _instance()
    by_name = {r.name: r for r in inst.rails}
    outbound = by_name["CustomerOutboundACH"]
    assert isinstance(outbound, TwoLegRail)
    assert outbound.origin == "InternalInitiated"
    assert outbound.source_origin is None
    assert outbound.destination_origin is None


def test_wire_rails_have_short_pending_age_window() -> None:
    """Fedwire is real-time — same-day reconciliation is the policy."""
    from datetime import timedelta
    inst = _instance()
    by_name = {r.name: r for r in inst.rails}
    for wire_rail in (
        by_name["CustomerInboundWire"],
        by_name["CustomerOutboundWire"],
        by_name["ConcentrationToFRBSweep"],
    ):
        assert wire_rail.max_pending_age == timedelta(hours=4), (
            f"{wire_rail.name}: expected PT4H wire window"
        )


def test_ach_rails_have_24h_pending_age_window() -> None:
    """ACH is overnight-batched — 24h reconciliation window matches policy."""
    from datetime import timedelta
    inst = _instance()
    by_name = {r.name: r for r in inst.rails}
    assert by_name["CustomerInboundACH"].max_pending_age == timedelta(hours=24)
    assert by_name["CustomerOutboundACH"].max_pending_age == timedelta(hours=24)


# -- LimitSchedules ----------------------------------------------------------


def test_three_limit_schedules_match_today_ar() -> None:
    """Mirrors today's `ar_ledger_transfer_limits` shape: per-type cap on
    DDA Control. Internal type uncapped (sweeps are uncapped in normal ops)."""
    inst = _instance()
    assert len(inst.limit_schedules) == 3
    by_type = {ls.transfer_type: ls for ls in inst.limit_schedules}
    assert set(by_type) == {"ach", "wire", "cash"}
    assert all(ls.parent_role == "DDAControl" for ls in inst.limit_schedules)
    assert by_type["ach"].cap == 12000
    assert by_type["wire"].cap == 15000
    assert by_type["cash"].cap == 10000


# -- Description coverage ----------------------------------------------------


def test_every_primitive_has_a_description() -> None:
    """M.7's handbook render pipeline reads every primitive's description.
    Missing prose means the rendered handbook page has gaps — cheap to
    catch at unit level rather than at deploy time."""
    inst = _instance()

    missing: list[str] = []
    for a in inst.accounts:
        if not a.description:
            missing.append(f"Account[{a.id}]")
    for t in inst.account_templates:
        if not t.description:
            missing.append(f"AccountTemplate[{t.role}]")
    for r in inst.rails:
        if not r.description:
            missing.append(f"Rail[{r.name}]")
    for ls in inst.limit_schedules:
        if not ls.description:
            missing.append(
                f"LimitSchedule[{ls.parent_role},{ls.transfer_type}]"
            )

    assert not missing, (
        "Primitives without descriptions (handbook prose source):\n  "
        + "\n  ".join(missing)
    )


# -- PostedRequirements (M.1a.4 derivation) ----------------------------------


def test_posted_requirements_for_standalone_inbound_ach() -> None:
    """Standalone rail (not in template, not Required-true child): integrator
    declaration IS the whole computed set."""
    from quicksight_gen.common.l2 import (
        Identifier,
        posted_requirements_for,
    )
    inst = _instance()
    result = posted_requirements_for(inst, Identifier("CustomerInboundACH"))
    assert result == (
        Identifier("customer_id"),
        Identifier("external_reference"),
    )


# -- TransferTemplate (M.1a primitive) ---------------------------------------


def test_internal_transfer_cycle_template_structure() -> None:
    """Three-leg shared-Transfer template using the
    `business_day_end+Nd` Completion vocabulary form."""
    inst = _instance()
    assert len(inst.transfer_templates) == 1
    t = inst.transfer_templates[0]
    assert t.name == "InternalTransferCycle"
    assert t.expected_net == 0
    assert t.transfer_key == ("internal_transfer_id",)
    assert t.completion == "business_day_end+1d"
    assert t.leg_rails == (
        "InternalTransferDebit",
        "InternalTransferCredit",
        "InternalTransferSuspenseClose",
    )


def test_variable_direction_closing_leg_present() -> None:
    """The InternalTransferSuspenseClose leg is the Variable closing leg
    that absorbs the cycle's imbalance to net zero."""
    inst = _instance()
    by_name = {r.name: r for r in inst.rails}
    closing_leg = by_name["InternalTransferSuspenseClose"]
    assert isinstance(closing_leg, SingleLegRail)
    assert closing_leg.leg_direction == "Variable"


def test_template_legs_auto_derive_transfer_key_posted_requirements() -> None:
    """The template's TransferKey field auto-projects onto every leg
    rail's PostedRequirements via derived.posted_requirements_for."""
    from quicksight_gen.common.l2 import (
        Identifier,
        posted_requirements_for,
    )
    inst = _instance()
    for leg in (
        "InternalTransferDebit",
        "InternalTransferCredit",
        "InternalTransferSuspenseClose",
    ):
        result = posted_requirements_for(inst, Identifier(leg))
        assert "internal_transfer_id" in result, (
            f"{leg}: TransferKey field should be auto-derived"
        )


# -- AggregatingRails (M.1a primitive variant) -------------------------------


def test_two_aggregating_rails_with_distinct_shapes() -> None:
    """One 2-leg internal aggregating + one 1-leg external-landing
    aggregating. Different cadences from kitchen-sink (daily-eod + monthly-eom
    vs kitchen-sink's intraday-2h + daily-eod)."""
    inst = _instance()
    aggregating = [r for r in inst.rails if r.aggregating]
    assert len(aggregating) == 2
    by_name = {r.name: r for r in aggregating}

    daily = by_name["ACHOriginationDailySweep"]
    assert isinstance(daily, TwoLegRail)
    assert daily.cadence == "daily-eod"
    assert daily.bundles_activity == ("CustomerOutboundACH",)

    monthly = by_name["CustomerFeeMonthlySettlement"]
    assert isinstance(monthly, SingleLegRail)
    assert monthly.cadence == "monthly-eom"
    assert monthly.bundles_activity == ("CustomerFeeAccrual",)


def test_single_leg_aggregating_lands_in_external() -> None:
    """Per SPEC: single-leg aggregating rails are the reconciliation
    mechanism — drift sweeps out into an External counterparty by design."""
    inst = _instance()
    by_name = {r.name: r for r in inst.rails}
    monthly = by_name["CustomerFeeMonthlySettlement"]
    assert isinstance(monthly, SingleLegRail)
    assert monthly.leg_role == ("ExternalCounterparty",)


def test_customer_fee_accrual_bundled_with_max_unbundled_age() -> None:
    """The single-leg fee rail sets max_unbundled_age (R8 requires it
    appear in some aggregating rail's BundlesActivity — satisfied by
    CustomerFeeMonthlySettlement)."""
    from datetime import timedelta
    inst = _instance()
    by_name = {r.name: r for r in inst.rails}
    fee = by_name["CustomerFeeAccrual"]
    assert isinstance(fee, SingleLegRail)
    assert fee.max_unbundled_age == timedelta(days=31)


# -- Union role (M.1a primitive variant) -------------------------------------


def test_customer_fee_accrual_uses_union_leg_role() -> None:
    """Single-leg union role (kitchen-sink's union role is on a 2-leg rail —
    different exercise of the same primitive)."""
    inst = _instance()
    by_name = {r.name: r for r in inst.rails}
    fee = by_name["CustomerFeeAccrual"]
    assert isinstance(fee, SingleLegRail)
    assert fee.leg_role == ("CustomerDDA", "InternalSuspenseRecon")


# -- Chains (M.1a primitive) -------------------------------------------------


def test_three_chain_entries_across_two_shapes() -> None:
    """1 Required:true (ACH origination → FRB sweep) + 2 XOR-group
    (ACH return reasons)."""
    inst = _instance()
    assert len(inst.chains) == 3


def test_required_true_chain_orphan_protection() -> None:
    """Required:true chain auto-derives parent_transfer_id onto the child
    rail's PostedRequirements (per derived.posted_requirements_for)."""
    from quicksight_gen.common.l2 import (
        Identifier,
        posted_requirements_for,
    )
    inst = _instance()
    by_name = {c.parent: c for c in inst.chains if c.required}
    assert "ACHOriginationDailySweep" in by_name
    required_chain = by_name["ACHOriginationDailySweep"]
    assert required_chain.child == "ConcentrationToFRBSweep"
    assert required_chain.xor_group is None

    # Auto-derivation: child rail gets parent_transfer_id
    child_pr = posted_requirements_for(inst, Identifier("ConcentrationToFRBSweep"))
    assert "parent_transfer_id" in child_pr


def test_xor_group_at_most_one_semantics() -> None:
    """Both ACH return reasons share xor_group=ACHReturnReason and have
    required=false → 'at most one fires per parent' per SPEC."""
    inst = _instance()
    xor_chains = [c for c in inst.chains if c.xor_group == "ACHReturnReason"]
    assert len(xor_chains) == 2
    children = {c.child for c in xor_chains}
    assert children == {
        "CustomerInboundACHReturnNSF",
        "CustomerInboundACHReturnStopPay",
    }
    assert all(c.parent == "CustomerInboundACH" for c in xor_chains)
    assert all(c.required is False for c in xor_chains)


# -- Vocabulary form coverage (validator V1+V2) ------------------------------


def test_completion_vocabulary_form_distinct_from_kitchen_sink() -> None:
    """SPEC-vocabulary spread: this fixture exercises `business_day_end+Nd`;
    kitchen-sink uses `metadata.<key>` and `business_day_end`. Together
    the two fixtures cover 3 of 4 v1 Completion forms (`month_end` is the
    fourth — exercised by the V1 vocabulary acceptance tests)."""
    inst = _instance()
    completions = {t.completion for t in inst.transfer_templates}
    assert completions == {"business_day_end+1d"}


def test_cadence_vocabulary_form_distinct_from_kitchen_sink() -> None:
    """SPEC-vocabulary spread: this fixture uses `daily-eod` + `monthly-eom`;
    kitchen-sink uses `intraday-2h` + `daily-eod`. Combined coverage:
    3 of 7 v1 Cadence forms (the rest exercised by V2 acceptance tests)."""
    inst = _instance()
    cadences = {r.cadence for r in inst.rails if r.cadence is not None}
    assert cadences == {"daily-eod", "monthly-eom"}
