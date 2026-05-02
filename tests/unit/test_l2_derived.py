"""Tests for ``common.l2.derived`` (M.1a.4 — PostedRequirements).

The derivation function unions three sources per the SPEC's
"PostedRequirements" subsection. Each test isolates one source path; a
combined test exercises all three; a dedup test confirms overlap
collapses; a deterministic-order test guards the sort. Lookup-miss
behaviour is its own test.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from quicksight_gen.common.l2 import (
    Account,
    ChainEntry,
    Identifier,
    L2Instance,
    PARENT_TRANSFER_ID,
    SingleLegRail,
    TransferTemplate,
    TwoLegRail,
    posted_requirements_for,
)


def _make_instance(
    *,
    rails: tuple = (),
    transfer_templates: tuple = (),
    chains: tuple = (),
) -> L2Instance:
    """Minimal L2Instance for isolating one derivation source at a time."""
    return L2Instance(
        instance=Identifier("der"),
        accounts=(
            Account(id=Identifier("a"), scope="internal", role=Identifier("A")),
            Account(id=Identifier("b"), scope="internal", role=Identifier("B")),
        ),
        account_templates=(),
        rails=rails,
        transfer_templates=transfer_templates,
        chains=chains,
        limit_schedules=(),
    )


def _two_leg(name: str, **kwargs) -> TwoLegRail:
    """Helper: TwoLegRail with sane defaults; override via kwargs."""
    defaults = dict(
        name=Identifier(name),
        transfer_type="t",
        metadata_keys=(),
        source_role=(Identifier("A"),),
        destination_role=(Identifier("B"),),
        origin="InternalInitiated",
        expected_net=Decimal("0"),
    )
    defaults.update(kwargs)
    return TwoLegRail(**defaults)


def _single_leg(name: str, **kwargs) -> SingleLegRail:
    """Helper: SingleLegRail with sane defaults; override via kwargs."""
    defaults = dict(
        name=Identifier(name),
        transfer_type="t",
        metadata_keys=(),
        leg_role=(Identifier("A"),),
        leg_direction="Debit",
        origin="InternalInitiated",
    )
    defaults.update(kwargs)
    return SingleLegRail(**defaults)


# -- Source 1: integrator-declared posted_requirements only ------------------


def test_returns_empty_when_rail_has_no_requirements_no_template_no_chain() -> None:
    inst = _make_instance(rails=(_two_leg("R"),))
    assert posted_requirements_for(inst, Identifier("R")) == ()


def test_returns_integrator_declared_only_when_no_template_no_chain() -> None:
    inst = _make_instance(rails=(_two_leg(
        "R",
        posted_requirements=(
            Identifier("external_reference"),
            Identifier("originator_id"),
        ),
    ),))
    # Sorted lex order; integrator-declared survives intact.
    assert posted_requirements_for(inst, Identifier("R")) == (
        Identifier("external_reference"),
        Identifier("originator_id"),
    )


# -- Source 2: TransferKey auto-derivation ------------------------------------


def test_unions_in_transfer_key_when_rail_in_template_leg_rails() -> None:
    rail = _single_leg("Charge", metadata_keys=(
        Identifier("merchant_id"),
        Identifier("settlement_period"),
    ))
    template = TransferTemplate(
        name=Identifier("MerchantSettlementCycle"),
        transfer_type="settlement_cycle",
        expected_net=Decimal("0"),
        transfer_key=(
            Identifier("merchant_id"),
            Identifier("settlement_period"),
        ),
        completion="business_day_end",
        leg_rails=(Identifier("Charge"),),
    )
    inst = _make_instance(rails=(rail,), transfer_templates=(template,))
    assert posted_requirements_for(inst, Identifier("Charge")) == (
        Identifier("merchant_id"),
        Identifier("settlement_period"),
    )


def test_unions_transfer_keys_across_multiple_containing_templates() -> None:
    """A rail MAY appear in multiple templates; each contributes its keys."""
    rail = _single_leg("SharedLeg")
    t1 = TransferTemplate(
        name=Identifier("T1"),
        transfer_type="t1",
        expected_net=Decimal("0"),
        transfer_key=(Identifier("k1"),),
        completion="business_day_end",
        leg_rails=(Identifier("SharedLeg"),),
    )
    t2 = TransferTemplate(
        name=Identifier("T2"),
        transfer_type="t2",
        expected_net=Decimal("0"),
        transfer_key=(Identifier("k2"),),
        completion="business_day_end",
        leg_rails=(Identifier("SharedLeg"),),
    )
    inst = _make_instance(rails=(rail,), transfer_templates=(t1, t2))
    assert posted_requirements_for(inst, Identifier("SharedLeg")) == (
        Identifier("k1"),
        Identifier("k2"),
    )


# -- Source 3: parent_transfer_id from Required-true chain --------------------


def test_required_true_chain_child_adds_parent_transfer_id() -> None:
    """Rail directly named as a Required:true Chain.child gets parent_transfer_id."""
    parent = _two_leg("ParentRail")
    child = _two_leg("ChildRail")
    chain = ChainEntry(
        parent=Identifier("ParentRail"),
        child=Identifier("ChildRail"),
        required=True,
    )
    inst = _make_instance(rails=(parent, child), chains=(chain,))
    assert posted_requirements_for(inst, Identifier("ChildRail")) == (
        PARENT_TRANSFER_ID,
    )


def test_required_false_chain_does_not_add_parent_transfer_id() -> None:
    """Required:false means the parent is genuinely optional — field stays NULL OK."""
    parent = _two_leg("ParentRail")
    child = _two_leg("ChildRail")
    chain = ChainEntry(
        parent=Identifier("ParentRail"),
        child=Identifier("ChildRail"),
        required=False,
    )
    inst = _make_instance(rails=(parent, child), chains=(chain,))
    assert posted_requirements_for(inst, Identifier("ChildRail")) == ()


def test_required_true_chain_via_containing_template() -> None:
    """Rail's containing TEMPLATE is the chain child (not the rail directly).
    Per SPEC: when a TransferTemplate is the chain.child, every leg of that
    template inherits the parent_transfer_id PostedRequirement."""
    rail = _single_leg("Leg")
    template = TransferTemplate(
        name=Identifier("MyTemplate"),
        transfer_type="t",
        expected_net=Decimal("0"),
        transfer_key=(Identifier("k"),),
        completion="business_day_end",
        leg_rails=(Identifier("Leg"),),
    )
    parent = _two_leg("Parent")
    chain = ChainEntry(
        parent=Identifier("Parent"),
        child=Identifier("MyTemplate"),
        required=True,
    )
    inst = _make_instance(
        rails=(rail, parent),
        transfer_templates=(template,),
        chains=(chain,),
    )
    result = posted_requirements_for(inst, Identifier("Leg"))
    assert PARENT_TRANSFER_ID in result
    # Also keeps the TransferKey-derived field.
    assert Identifier("k") in result


# -- Combined --------------------------------------------------------------


def test_unions_all_three_sources_together() -> None:
    """All three derivation paths combine; each contributes its share."""
    rail = _single_leg(
        "BigLeg",
        posted_requirements=(Identifier("integrator_field"),),
    )
    template = TransferTemplate(
        name=Identifier("Template"),
        transfer_type="t",
        expected_net=Decimal("0"),
        transfer_key=(Identifier("template_key"),),
        completion="business_day_end",
        leg_rails=(Identifier("BigLeg"),),
    )
    parent = _two_leg("Parent")
    chain = ChainEntry(
        parent=Identifier("Parent"),
        child=Identifier("BigLeg"),
        required=True,
    )
    inst = _make_instance(
        rails=(rail, parent),
        transfer_templates=(template,),
        chains=(chain,),
    )
    result = posted_requirements_for(inst, Identifier("BigLeg"))
    assert set(result) == {
        Identifier("integrator_field"),
        Identifier("template_key"),
        PARENT_TRANSFER_ID,
    }


# -- Dedup + determinism -----------------------------------------------------


def test_dedups_overlap_between_integrator_declared_and_transfer_key() -> None:
    """Integrator MAY redundantly list a TransferKey field; output stays single."""
    rail = _single_leg(
        "Leg",
        posted_requirements=(Identifier("merchant_id"),),
    )
    template = TransferTemplate(
        name=Identifier("T"),
        transfer_type="t",
        expected_net=Decimal("0"),
        transfer_key=(
            Identifier("merchant_id"),
            Identifier("period"),
        ),
        completion="business_day_end",
        leg_rails=(Identifier("Leg"),),
    )
    inst = _make_instance(rails=(rail,), transfer_templates=(template,))
    result = posted_requirements_for(inst, Identifier("Leg"))
    # Each field appears once even though merchant_id was double-declared.
    assert sorted(result) == list(result)  # deterministic sort
    assert result.count(Identifier("merchant_id")) == 1
    assert result == (Identifier("merchant_id"), Identifier("period"))


def test_deterministic_sort_order_across_runs() -> None:
    """Lex sort means two calls return identical tuples (no set hash flux)."""
    rail = _single_leg(
        "Leg",
        posted_requirements=(
            Identifier("zzz"),
            Identifier("aaa"),
            Identifier("mmm"),
        ),
    )
    inst = _make_instance(rails=(rail,))
    out1 = posted_requirements_for(inst, Identifier("Leg"))
    out2 = posted_requirements_for(inst, Identifier("Leg"))
    assert out1 == out2 == (
        Identifier("aaa"),
        Identifier("mmm"),
        Identifier("zzz"),
    )


# -- Lookup miss --------------------------------------------------------------


def test_unknown_rail_name_raises_keyerror() -> None:
    inst = _make_instance(rails=(_two_leg("Real"),))
    with pytest.raises(KeyError, match="not found"):
        posted_requirements_for(inst, Identifier("NotReal"))


# -- Required:true chain entry but rail is the PARENT, not the child ---------


def test_chain_parent_does_not_inherit_parent_transfer_id() -> None:
    """parent_transfer_id is added to the CHILD side. The parent rail of a
    chain doesn't itself need a parent_transfer_id."""
    parent = _two_leg("Parent")
    child = _two_leg("Child")
    chain = ChainEntry(
        parent=Identifier("Parent"),
        child=Identifier("Child"),
        required=True,
    )
    inst = _make_instance(rails=(parent, child), chains=(chain,))
    assert posted_requirements_for(inst, Identifier("Parent")) == ()
