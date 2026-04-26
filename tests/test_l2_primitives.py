"""Structural regression guards on the L2 primitives package.

Comprehensive per-primitive coverage (load + emit + Current* projection)
lands in M.1.6 once the loader + emitter + Current* projector exist. This
file is the M.1.1 smoke surface — confirms the dataclasses construct
cleanly, the Rail discriminated union dispatches, and the frozen
contract holds.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from quicksight_gen.common.l2 import (
    Account,
    AccountTemplate,
    ChainEntry,
    Identifier,
    L2Instance,
    LimitSchedule,
    SingleLegRail,
    TransferTemplate,
    TwoLegRail,
)


def _example_instance() -> L2Instance:
    """Build a minimal L2Instance using every primitive at least once."""
    return L2Instance(
        instance=Identifier("spk"),
        accounts=(
            Account(
                id=Identifier("int-001"),
                scope="internal",
                name="Internal Operations Account",
                role=Identifier("InternalDDA"),
            ),
        ),
        account_templates=(
            AccountTemplate(
                role=Identifier("CustomerSubledger"),
                scope="internal",
                parent_role=Identifier("SouthPool"),
            ),
        ),
        rails=(
            TwoLegRail(
                name=Identifier("ExtInbound"),
                transfer_type="ach",
                origin="ExternalForcePosted",
                metadata_keys=(Identifier("external_reference"),),
                source_role=(Identifier("ExternalCounterparty"),),
                destination_role=(Identifier("InternalDDA"),),
                expected_net=Decimal("0"),
            ),
            SingleLegRail(
                name=Identifier("SubledgerCharge"),
                transfer_type="charge",
                origin="InternalInitiated",
                metadata_keys=(
                    Identifier("merchant_id"),
                    Identifier("settlement_period"),
                ),
                leg_role=(Identifier("CustomerSubledger"),),
                leg_direction="Debit",
            ),
        ),
        transfer_templates=(
            TransferTemplate(
                name=Identifier("MerchantSettlementCycle"),
                transfer_type="settlement_cycle",
                expected_net=Decimal("0"),
                transfer_key=(
                    Identifier("merchant_id"),
                    Identifier("settlement_period"),
                ),
                completion="metadata.settlement_period_end",
                leg_rails=(Identifier("SubledgerCharge"),),
            ),
        ),
        chains=(
            ChainEntry(
                parent=Identifier("MerchantSettlementCycle"),
                child=Identifier("MerchantPayoutACH"),
                required=True,
                xor_group=Identifier("PayoutVehicle"),
            ),
        ),
        limit_schedules=(
            LimitSchedule(
                parent_role=Identifier("SouthPool"),
                transfer_type="ach",
                cap=Decimal("5000.00"),
            ),
        ),
    )


def test_l2instance_constructs_with_every_primitive() -> None:
    """Every primitive is reachable from L2Instance and constructs cleanly."""
    inst = _example_instance()
    assert inst.instance == "spk"
    assert len(inst.accounts) == 1
    assert len(inst.account_templates) == 1
    assert len(inst.rails) == 2
    assert len(inst.transfer_templates) == 1
    assert len(inst.chains) == 1
    assert len(inst.limit_schedules) == 1


def test_rail_discriminated_union_dispatches_via_match() -> None:
    """Per F2: TwoLegRail / SingleLegRail dispatch via match without isinstance ladders."""
    inst = _example_instance()
    classified: list[tuple[str, str]] = []
    for r in inst.rails:
        match r:
            case TwoLegRail(name=n):
                classified.append((str(n), "two-leg"))
            case SingleLegRail(name=n):
                classified.append((str(n), "single-leg"))
    assert classified == [
        ("ExtInbound", "two-leg"),
        ("SubledgerCharge", "single-leg"),
    ]


def test_primitives_are_frozen() -> None:
    """Frozen dataclasses prevent accidental mutation of an L2 instance."""
    inst = _example_instance()
    with pytest.raises(Exception):
        inst.accounts[0].id = Identifier("oops")  # type: ignore[misc]


def test_aggregating_flag_optional_on_both_rail_shapes() -> None:
    """Per SPEC: aggregating MAY be true on either two-leg or single-leg."""
    two = TwoLegRail(
        name=Identifier("PoolBalancing"),
        transfer_type="pool_balancing",
        origin="InternalInitiated",
        metadata_keys=(),
        source_role=(Identifier("NorthPool"),),
        destination_role=(Identifier("SouthPool"),),
        expected_net=Decimal("0"),
        aggregating=True,
        bundles_activity=(Identifier("SubledgerCharge"),),
        cadence="intraday-2h",
    )
    assert two.aggregating is True
    assert two.cadence == "intraday-2h"

    single = SingleLegRail(
        name=Identifier("ExternalSweep"),
        transfer_type="sweep",
        origin="InternalInitiated",
        metadata_keys=(),
        leg_role=(Identifier("ExternalCounterparty"),),
        leg_direction="Credit",
        aggregating=True,
        bundles_activity=(Identifier("ach"),),
        cadence="daily-eod",
    )
    assert single.aggregating is True
    assert single.cadence == "daily-eod"
