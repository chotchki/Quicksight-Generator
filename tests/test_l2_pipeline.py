"""Per-primitive end-to-end pipeline tests (M.1.6).

For each L2 primitive shape, walk a minimal-but-valid YAML through the
full pipeline — ``load_instance`` → ``validate`` → ``emit_schema`` — and
assert the primitive is reachable + the schema is well-formed. This
catches integration breakage that per-layer tests miss (e.g. a loader
that produces a primitive the validator can't accept, or a primitive
shape the schema can't represent).

Each test corresponds to one of the SPEC's "Worked example shapes" so
this file doubles as executable SPEC documentation: if a SPEC snippet
stops parsing/validating, the named test fires.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from quicksight_gen.common.l2 import (
    SingleLegRail,
    TwoLegRail,
    emit_schema,
    load_instance,
    validate,
)


def _pipeline(yaml_text: str, tmp_path: Path):
    """load → validate → emit_schema; return (instance, sql) on success."""
    p = tmp_path / "inst.yaml"
    p.write_text(yaml_text)
    inst = load_instance(p)
    validate(inst)
    sql = emit_schema(inst)
    return inst, sql


# -- Per-primitive shapes ----------------------------------------------------


def test_pipeline_singleton_account(tmp_path: Path) -> None:
    """One singleton Account with every optional field set."""
    inst, sql = _pipeline(dedent("""\
        instance: t1
        accounts:
          - id: clearing-suspense
            name: Clearing Suspense
            role: ClearingSuspense
            scope: internal
            expected_eod_balance: 0
        rails: []
        """), tmp_path)
    a = inst.accounts[0]
    assert a.id == "clearing-suspense"
    assert a.role == "ClearingSuspense"
    assert a.expected_eod_balance == 0
    assert "CREATE TABLE t1_transactions" in sql


def test_pipeline_account_template(tmp_path: Path) -> None:
    """AccountTemplate + the singleton Account it parents under."""
    inst, sql = _pipeline(dedent("""\
        instance: t2
        accounts:
          - id: gl-control
            role: ControlAccount
            scope: internal
        account_templates:
          - role: CustomerSubledger
            scope: internal
            parent_role: ControlAccount
        rails: []
        """), tmp_path)
    assert len(inst.account_templates) == 1
    assert inst.account_templates[0].role == "CustomerSubledger"
    assert inst.account_templates[0].parent_role == "ControlAccount"


def test_pipeline_two_leg_standalone_rail(tmp_path: Path) -> None:
    """Standalone two-leg Rail with expected_net=0 and metadata keys."""
    inst, _ = _pipeline(dedent("""\
        instance: t3
        accounts:
          - id: a-int
            role: InternalDDA
            scope: internal
          - id: a-ext
            role: ExternalCounterparty
            scope: external
        rails:
          - name: ExternalRailInbound
            transfer_type: ach
            source_role: ExternalCounterparty
            destination_role: InternalDDA
            expected_net: 0
            origin: ExternalForcePosted
            metadata_keys: [external_reference, originator_id]
        """), tmp_path)
    rail = inst.rails[0]
    assert isinstance(rail, TwoLegRail)
    assert rail.metadata_keys == ("external_reference", "originator_id")
    assert rail.expected_net == 0


def test_pipeline_single_leg_rail_in_transfer_template(tmp_path: Path) -> None:
    """Single-leg rail reconciled by being in a TransferTemplate.leg_rails."""
    inst, _ = _pipeline(dedent("""\
        instance: t4
        accounts:
          - id: gl
            role: ControlAccount
            scope: internal
        account_templates:
          - role: CustomerSubledger
            scope: internal
            parent_role: ControlAccount
        rails:
          - name: SubledgerCharge
            transfer_type: charge
            leg_role: CustomerSubledger
            leg_direction: Debit
            origin: InternalInitiated
            metadata_keys: [merchant_id, settlement_period]
        transfer_templates:
          - name: ChargeCycle
            transfer_type: charge_cycle
            expected_net: 0
            transfer_key: [merchant_id, settlement_period]
            completion: business_day_end+3d
            leg_rails: [SubledgerCharge]
        """), tmp_path)
    rail = inst.rails[0]
    assert isinstance(rail, SingleLegRail)
    assert rail.leg_direction == "Debit"


def test_pipeline_single_leg_variable_direction_rail(tmp_path: Path) -> None:
    """Variable-direction closing leg of a TransferTemplate."""
    inst, _ = _pipeline(dedent("""\
        instance: t5
        accounts:
          - id: gl
            role: MerchantLedger
            scope: internal
          - id: cust
            role: CustomerSubledger
            scope: internal
            parent_role: MerchantLedger
        rails:
          - name: SubledgerCharge
            transfer_type: charge
            leg_role: CustomerSubledger
            leg_direction: Debit
            origin: InternalInitiated
            metadata_keys: [merchant_id, settlement_period]
          - name: SettlementClose
            transfer_type: settlement
            leg_role: MerchantLedger
            leg_direction: Variable
            origin: InternalInitiated
            metadata_keys: [merchant_id, settlement_period]
        transfer_templates:
          - name: MerchantSettlementCycle
            transfer_type: settlement_cycle
            expected_net: 0
            transfer_key: [merchant_id, settlement_period]
            completion: month_end
            leg_rails: [SubledgerCharge, SettlementClose]
        """), tmp_path)
    settlement = next(r for r in inst.rails if r.name == "SettlementClose")
    assert isinstance(settlement, SingleLegRail)
    assert settlement.leg_direction == "Variable"


def test_pipeline_aggregating_rail(tmp_path: Path) -> None:
    """Aggregating two-leg rail with cadence + bundles_activity."""
    inst, _ = _pipeline(dedent("""\
        instance: t6
        accounts:
          - id: north
            role: NorthPool
            scope: internal
          - id: south
            role: SouthPool
            scope: internal
        rails:
          - name: ChargeRail
            transfer_type: charge
            leg_role: NorthPool
            leg_direction: Debit
            origin: InternalInitiated
            metadata_keys: []
          - name: PoolBalancingNorthToSouth
            transfer_type: pool_balancing
            source_role: NorthPool
            destination_role: SouthPool
            expected_net: 0
            origin: InternalInitiated
            metadata_keys: [bundled_transfer_type, business_day]
            aggregating: true
            bundles_activity: [ChargeRail, charge]
            cadence: intraday-2h
        """), tmp_path)
    pool = next(r for r in inst.rails if r.name == "PoolBalancingNorthToSouth")
    assert isinstance(pool, TwoLegRail)
    assert pool.aggregating is True
    assert pool.cadence == "intraday-2h"
    assert pool.bundles_activity == ("ChargeRail", "charge")


@pytest.mark.parametrize("completion_expr", [
    "business_day_end",
    "business_day_end+1d",
    "month_end",
    "metadata.deadline",
])
def test_pipeline_transfer_template_each_completion_form(
    completion_expr: str, tmp_path: Path,
) -> None:
    """Every CompletionExpression vocabulary form parses + validates."""
    inst, _ = _pipeline(dedent(f"""\
        instance: t7
        accounts:
          - id: a
            role: A
            scope: internal
        account_templates:
          - role: CustomerSubledger
            scope: internal
            parent_role: A
        rails:
          - name: ChargeLeg
            transfer_type: charge
            leg_role: CustomerSubledger
            leg_direction: Debit
            origin: InternalInitiated
            metadata_keys: [merchant_id, deadline]
        transfer_templates:
          - name: T
            transfer_type: cycle
            expected_net: 0
            transfer_key: [merchant_id]
            completion: {completion_expr}
            leg_rails: [ChargeLeg]
        """), tmp_path)
    assert inst.transfer_templates[0].completion == completion_expr


def test_pipeline_chain_xor_group(tmp_path: Path) -> None:
    """XOR group with three child Rails sharing the same parent template."""
    inst, _ = _pipeline(dedent("""\
        instance: t8
        accounts:
          - id: m
            role: MerchantLedger
            scope: internal
          - id: e
            role: ExternalCounterparty
            scope: external
        rails:
          - name: SettlementClose
            transfer_type: settlement
            leg_role: MerchantLedger
            leg_direction: Variable
            origin: InternalInitiated
            metadata_keys: [merchant_id]
          - name: PayoutACH
            transfer_type: ach
            source_role: MerchantLedger
            destination_role: ExternalCounterparty
            expected_net: 0
            origin: InternalInitiated
            metadata_keys: [merchant_id]
          - name: PayoutVoucher
            transfer_type: voucher
            source_role: MerchantLedger
            destination_role: ExternalCounterparty
            expected_net: 0
            origin: InternalInitiated
            metadata_keys: [merchant_id]
          - name: PayoutInternal
            transfer_type: internal_transfer
            source_role: MerchantLedger
            destination_role: MerchantLedger
            expected_net: 0
            origin: InternalInitiated
            metadata_keys: [merchant_id]
        transfer_templates:
          - name: SettlementCycle
            transfer_type: cycle
            expected_net: 0
            transfer_key: [merchant_id]
            completion: business_day_end
            leg_rails: [SettlementClose]
        chains:
          - parent: SettlementCycle
            child: PayoutACH
            required: false
            xor_group: PayoutVehicle
          - parent: SettlementCycle
            child: PayoutVoucher
            required: false
            xor_group: PayoutVehicle
          - parent: SettlementCycle
            child: PayoutInternal
            required: false
            xor_group: PayoutVehicle
        """), tmp_path)
    assert len(inst.chains) == 3
    assert all(c.xor_group == "PayoutVehicle" for c in inst.chains)
    assert {c.parent for c in inst.chains} == {"SettlementCycle"}


def test_pipeline_chain_fan_out(tmp_path: Path) -> None:
    """One parent → many children (no xor_group, required=true)."""
    inst, _ = _pipeline(dedent("""\
        instance: t9
        accounts:
          - id: pool
            role: Pool
            scope: internal
          - id: ext
            role: ExternalCounterparty
            scope: external
        rails:
          - name: BatchInbound
            transfer_type: batch
            source_role: ExternalCounterparty
            destination_role: Pool
            expected_net: 0
            origin: ExternalForcePosted
            metadata_keys: []
          - name: PerRecipientCredit
            transfer_type: credit
            source_role: Pool
            destination_role: Pool
            expected_net: 0
            origin: InternalInitiated
            metadata_keys: []
        chains:
          - parent: BatchInbound
            child: PerRecipientCredit
            required: true
        """), tmp_path)
    assert inst.chains[0].required is True
    assert inst.chains[0].xor_group is None


def test_pipeline_limit_schedule(tmp_path: Path) -> None:
    """LimitSchedule with parent_role + transfer_type + cap."""
    inst, _ = _pipeline(dedent("""\
        instance: t10
        accounts:
          - id: north
            role: NorthPool
            scope: internal
          - id: child
            role: ChildPool
            scope: internal
            parent_role: NorthPool
        rails:
          # R10: every LimitSchedule.transfer_type must match some Rail.
          - name: ChildAch
            transfer_type: ach
            origin: InternalInitiated
            leg_role: ChildPool
            leg_direction: Debit
            metadata_keys: [batch_id]
        transfer_templates:
          # S3: single-leg ChildAch needs reconciliation.
          - name: AchCycle
            transfer_type: ach_cycle
            expected_net: 0
            transfer_key: [batch_id]
            completion: business_day_end
            leg_rails: [ChildAch]
        limit_schedules:
          - parent_role: NorthPool
            transfer_type: ach
            cap: 5000.00
        """), tmp_path)
    ls = inst.limit_schedules[0]
    assert ls.parent_role == "NorthPool"
    assert ls.cap == 5000


# -- Kitchen-sink fixture (M.1.8) --------------------------------------------


KITCHEN_YAML = Path(__file__).parent / "l2" / "_kitchen.yaml"


def test_kitchen_sink_loads_validates_emits() -> None:
    """The fixture YAML walks the full pipeline cleanly.

    Per M.1.8: this is the regression harness — if any primitive shape
    stops being supported by the loader / validator / emitter, this test
    fires. The fixture covers every primitive shape + every variant flag
    SPEC v1 declares.
    """
    inst = load_instance(KITCHEN_YAML)
    validate(inst)
    sql = emit_schema(inst)
    assert "CREATE TABLE kitchen_transactions" in sql
    assert "CREATE MATERIALIZED VIEW kitchen_current_transactions AS" in sql


def test_kitchen_sink_covers_every_primitive_kind() -> None:
    """Coverage gate: every primitive type + every important variant present.

    If a new primitive kind is added to the SPEC, extending it here
    enforces that the kitchen fixture is updated to exercise it.
    """
    inst = load_instance(KITCHEN_YAML)

    # Every entity bucket non-empty
    assert inst.accounts, "kitchen fixture missing singleton accounts"
    assert inst.account_templates, "kitchen fixture missing AccountTemplates"
    assert inst.rails, "kitchen fixture missing Rails"
    assert inst.transfer_templates, "kitchen fixture missing TransferTemplates"
    assert inst.chains, "kitchen fixture missing Chains"
    assert inst.limit_schedules, "kitchen fixture missing LimitSchedules"

    # Both rail shapes present
    two_legs = [r for r in inst.rails if isinstance(r, TwoLegRail)]
    single_legs = [r for r in inst.rails if isinstance(r, SingleLegRail)]
    assert two_legs, "kitchen fixture missing TwoLegRail"
    assert single_legs, "kitchen fixture missing SingleLegRail"

    # Aggregating variant on both rail shapes
    assert any(r.aggregating for r in two_legs), \
        "kitchen fixture missing aggregating TwoLegRail"
    assert any(r.aggregating for r in single_legs), \
        "kitchen fixture missing aggregating SingleLegRail"

    # Variable-direction leg present
    assert any(
        isinstance(r, SingleLegRail) and r.leg_direction == "Variable"
        for r in inst.rails
    ), "kitchen fixture missing Variable-direction leg"

    # Union role (RoleA | RoleB) present
    assert any(
        isinstance(r, TwoLegRail) and len(r.source_role) > 1
        for r in inst.rails
    ), "kitchen fixture missing union role on a Rail"

    # Standalone two-leg (with expected_net) AND template-leg two-leg (without).
    assert any(
        isinstance(r, TwoLegRail) and r.expected_net is not None
        for r in inst.rails
    ), "kitchen fixture missing standalone TwoLegRail"
    assert any(
        isinstance(r, TwoLegRail) and r.expected_net is None
        for r in inst.rails
    ), "kitchen fixture missing template-leg TwoLegRail (no expected_net)"

    # Multiple Completion vocabulary forms across templates.
    completion_forms = {t.completion for t in inst.transfer_templates}
    assert len(completion_forms) >= 2, \
        "kitchen fixture should exercise >1 Completion form"

    # XOR + non-XOR chains both present.
    assert any(c.xor_group is not None for c in inst.chains), \
        "kitchen fixture missing an XOR-group chain entry"
    assert any(c.xor_group is None for c in inst.chains), \
        "kitchen fixture missing a non-XOR chain entry"

    # N.1.i — inline brand theme exercises the loader's _load_theme path.
    assert inst.theme is not None, \
        "kitchen fixture missing inline theme block"
    assert inst.theme.theme_name == "Kitchen Sink Theme"
    assert inst.theme.accent.startswith("#"), \
        "kitchen theme.accent must be a hex color"


def test_pipeline_full_merchant_acquirer_end_to_end(tmp_path: Path) -> None:
    """SPEC's end-to-end merchant-acquirer example through the full pipeline.

    This is the kitchen-sink shape — every primitive in one declaration.
    Lifted from SPEC.md's "End-to-end: a complete merchant-acquiring
    instance" worked example with light adaptations for self-containment.
    If this stops working, the SPEC's example needs updating too.
    """
    inst, sql = _pipeline(dedent("""\
        instance: ex_acq

        accounts:
          - id: north-pool
            role: NorthPool
            scope: internal
          - id: south-pool
            role: SouthPool
            scope: internal
          - id: clearing-suspense
            role: ClearingSuspense
            scope: internal
            expected_eod_balance: 0
          - id: ext-counter
            role: ExternalCounterparty
            scope: external

        account_templates:
          - role: CustomerSubledger
            scope: internal
            parent_role: SouthPool
          - role: MerchantLedger
            scope: internal
            parent_role: NorthPool

        rails:
          - name: SubledgerCharge
            transfer_type: charge
            leg_role: CustomerSubledger
            leg_direction: Debit
            origin: InternalInitiated
            metadata_keys: [merchant_id, customer_id, settlement_period, settlement_period_end]

          - name: SubledgerRefund
            transfer_type: refund
            leg_role: CustomerSubledger
            leg_direction: Credit
            origin: InternalInitiated
            metadata_keys: [merchant_id, customer_id, settlement_period, settlement_period_end]

          - name: SettlementClose
            transfer_type: settlement
            leg_role: MerchantLedger
            leg_direction: Variable
            origin: InternalInitiated
            metadata_keys: [merchant_id, settlement_period, settlement_period_end]

          - name: MerchantPayoutACH
            transfer_type: ach
            source_role: MerchantLedger
            destination_role: ExternalCounterparty
            expected_net: 0
            origin: InternalInitiated
            metadata_keys: [merchant_id, settlement_period]

          - name: PoolBalancingSouthToNorth
            transfer_type: pool_balancing
            source_role: SouthPool
            destination_role: NorthPool
            expected_net: 0
            origin: InternalInitiated
            metadata_keys: [bundled_transfer_type, business_day]
            aggregating: true
            bundles_activity: [SubledgerCharge, SubledgerRefund, SettlementClose]
            cadence: intraday-2h

        transfer_templates:
          - name: MerchantSettlementCycle
            transfer_type: settlement_cycle
            expected_net: 0
            transfer_key: [merchant_id, settlement_period]
            completion: metadata.settlement_period_end
            leg_rails: [SubledgerCharge, SubledgerRefund, SettlementClose]

        chains:
          - parent: MerchantSettlementCycle
            child: MerchantPayoutACH
            required: true

        limit_schedules:
          - parent_role: SouthPool
            transfer_type: charge
            cap: 5000.00
        """), tmp_path)

    # Every primitive present
    assert len(inst.accounts) == 4
    assert len(inst.account_templates) == 2
    assert len(inst.rails) == 5
    assert len(inst.transfer_templates) == 1
    assert len(inst.chains) == 1
    assert len(inst.limit_schedules) == 1

    # Both rail shapes
    assert sum(1 for r in inst.rails if isinstance(r, TwoLegRail)) == 2
    assert sum(1 for r in inst.rails if isinstance(r, SingleLegRail)) == 3

    # Aggregating rail present + correctly flagged
    pool = next(r for r in inst.rails if r.name == "PoolBalancingSouthToNorth")
    assert pool.aggregating is True

    # Variable-direction closing leg
    settlement = next(r for r in inst.rails if r.name == "SettlementClose")
    assert isinstance(settlement, SingleLegRail)
    assert settlement.leg_direction == "Variable"

    # Schema includes the prefix and Current* views
    assert "CREATE TABLE ex_acq_transactions" in sql
    assert "CREATE TABLE ex_acq_daily_balances" in sql
    assert "CREATE MATERIALIZED VIEW ex_acq_current_transactions AS" in sql
    assert "CREATE MATERIALIZED VIEW ex_acq_current_daily_balances AS" in sql
