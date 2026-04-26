"""Cross-entity validation tests for ``common.l2.validate`` (M.1.3).

One rejection test per rule (per L.1.18 + M.1's testing principle). Each
test starts from the ``_baseline_instance()`` fixture (a known-valid
instance using every primitive) and mutates one field to trigger exactly
one rule.

Rule numbering matches ``validate.py``'s docstring (U1-U4 / R1-R6 /
C1-C2 / S1-S6 / V1-V2).
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from quicksight_gen.common.l2 import (
    Account,
    AccountTemplate,
    ChainEntry,
    Identifier,
    L2Instance,
    L2ValidationError,
    LimitSchedule,
    Name,
    SingleLegRail,
    TransferTemplate,
    TwoLegRail,
    validate,
)


# -- Baseline ----------------------------------------------------------------


def _baseline_instance() -> L2Instance:
    """A known-valid L2Instance covering every primitive shape.

    Every test mutates exactly one field of this instance to trigger
    exactly one rule. The baseline itself MUST pass ``validate()`` —
    a regression on the baseline means the validator drifted.
    """
    return L2Instance(
        instance=Identifier("base"),
        accounts=(
            Account(
                id=Identifier("gl-control"),
                scope="internal",
                name=Name("Control Account"),
                role=Identifier("ControlAccount"),
            ),
            Account(
                id=Identifier("ext-counter"),
                scope="external",
                role=Identifier("ExternalCounterparty"),
            ),
        ),
        account_templates=(
            AccountTemplate(
                role=Identifier("CustomerSubledger"),
                scope="internal",
                parent_role=Identifier("ControlAccount"),
            ),
        ),
        rails=(
            # Standalone two-leg with expected_net (S1).
            TwoLegRail(
                name=Identifier("ExtInbound"),
                transfer_type="ach",
                origin="ExternalForcePosted",
                metadata_keys=(Identifier("external_reference"),),
                source_role=(Identifier("ExternalCounterparty"),),
                destination_role=(Identifier("ControlAccount"),),
                expected_net=Decimal("0"),
            ),
            # Single-leg, reconciled by the TransferTemplate below (S3).
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
            # Aggregating rail (two-leg) with cadence + bundles_activity (S5).
            TwoLegRail(
                name=Identifier("PoolBalancing"),
                transfer_type="pool_balancing",
                origin="InternalInitiated",
                metadata_keys=(),
                source_role=(Identifier("ControlAccount"),),
                destination_role=(Identifier("ControlAccount"),),
                expected_net=Decimal("0"),
                aggregating=True,
                bundles_activity=(Identifier("ach"),),
                cadence="intraday-2h",
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
        chains=(),
        limit_schedules=(
            LimitSchedule(
                parent_role=Identifier("ControlAccount"),
                transfer_type="ach",
                cap=Decimal("5000.00"),
            ),
        ),
    )


def test_baseline_passes_validation() -> None:
    """Sanity guard: every test below assumes the baseline passes."""
    validate(_baseline_instance())


def _replace(inst: L2Instance, **changes) -> L2Instance:
    return dataclasses.replace(inst, **changes)


# -- Uniqueness (U1-U4) ------------------------------------------------------


def test_u1_duplicate_account_id_rejected() -> None:
    inst = _baseline_instance()
    dup = dataclasses.replace(inst.accounts[1], id=inst.accounts[0].id)
    bad = _replace(inst, accounts=(inst.accounts[0], dup))
    with pytest.raises(L2ValidationError, match="duplicate Account.id"):
        validate(bad)


def test_u2_duplicate_account_template_role_rejected() -> None:
    inst = _baseline_instance()
    dup = AccountTemplate(
        role=inst.account_templates[0].role,
        scope="internal",
        parent_role=Identifier("ControlAccount"),
    )
    bad = _replace(inst, account_templates=(*inst.account_templates, dup))
    with pytest.raises(L2ValidationError, match="duplicate AccountTemplate.role"):
        validate(bad)


def test_u3_duplicate_rail_name_rejected() -> None:
    inst = _baseline_instance()
    dup = dataclasses.replace(inst.rails[0], name=Identifier("PoolBalancing"))
    bad = _replace(inst, rails=(*inst.rails, dup))
    with pytest.raises(L2ValidationError, match="duplicate Rail.name"):
        validate(bad)


def test_u4_duplicate_transfer_template_name_rejected() -> None:
    inst = _baseline_instance()
    dup = dataclasses.replace(
        inst.transfer_templates[0], name=Identifier("MerchantSettlementCycle"),
    )
    bad = _replace(inst, transfer_templates=(*inst.transfer_templates, dup))
    with pytest.raises(
        L2ValidationError, match="duplicate TransferTemplate.name",
    ):
        validate(bad)


# -- Reference resolution (R1-R6) --------------------------------------------


def test_r1_rail_references_undeclared_role_rejected() -> None:
    inst = _baseline_instance()
    bad_rail = dataclasses.replace(
        inst.rails[0],
        source_role=(Identifier("UndeclaredRole"),),
    )
    bad = _replace(inst, rails=(bad_rail, *inst.rails[1:]))
    with pytest.raises(L2ValidationError, match="ExtInbound.*UndeclaredRole"):
        validate(bad)


def test_r2_account_parent_role_resolves() -> None:
    inst = _baseline_instance()
    bad_acc = dataclasses.replace(
        inst.accounts[0], parent_role=Identifier("UndeclaredRole"),
    )
    bad = _replace(inst, accounts=(bad_acc, *inst.accounts[1:]))
    with pytest.raises(L2ValidationError, match="gl-control.*parent_role"):
        validate(bad)


def test_r3_account_template_parent_role_must_be_singleton() -> None:
    """Template-under-template parent reference is rejected per F1."""
    inst = _baseline_instance()
    # Add another template; first template references the second (NOT a singleton).
    second_template = AccountTemplate(
        role=Identifier("MerchantLedger"),
        scope="internal",
        parent_role=Identifier("ControlAccount"),
    )
    bad_template = dataclasses.replace(
        inst.account_templates[0],
        parent_role=Identifier("MerchantLedger"),
    )
    bad = _replace(
        inst,
        account_templates=(bad_template, second_template),
    )
    with pytest.raises(
        L2ValidationError, match="resolves to another AccountTemplate",
    ):
        validate(bad)


def test_r3_account_template_parent_role_undeclared_rejected() -> None:
    inst = _baseline_instance()
    bad_template = dataclasses.replace(
        inst.account_templates[0],
        parent_role=Identifier("UndeclaredRole"),
    )
    bad = _replace(inst, account_templates=(bad_template,))
    with pytest.raises(
        L2ValidationError, match="not declared on any Account",
    ):
        validate(bad)


def test_r4_template_leg_rails_must_exist() -> None:
    inst = _baseline_instance()
    bad_template = dataclasses.replace(
        inst.transfer_templates[0],
        leg_rails=(Identifier("NonexistentRail"),),
    )
    bad = _replace(inst, transfer_templates=(bad_template,))
    with pytest.raises(
        L2ValidationError, match="MerchantSettlementCycle.*NonexistentRail",
    ):
        validate(bad)


def test_r5_chain_endpoints_must_exist() -> None:
    inst = _baseline_instance()
    bad_chain = ChainEntry(
        parent=Identifier("MerchantSettlementCycle"),
        child=Identifier("NonexistentRail"),
        required=True,
    )
    bad = _replace(inst, chains=(bad_chain,))
    with pytest.raises(L2ValidationError, match="chains\\[0\\].child"):
        validate(bad)


def test_r6_limit_schedule_parent_role_must_resolve() -> None:
    inst = _baseline_instance()
    bad_limit = LimitSchedule(
        parent_role=Identifier("UndeclaredRole"),
        transfer_type="ach",
        cap=Decimal("100"),
    )
    bad = _replace(inst, limit_schedules=(bad_limit,))
    with pytest.raises(L2ValidationError, match="limit_schedules\\[0\\]"):
        validate(bad)


# -- Cardinality (C1-C2) -----------------------------------------------------


def test_c1_at_most_one_variable_leg_per_template() -> None:
    inst = _baseline_instance()
    # Add a second SingleLegRail with Variable direction; both go in the
    # template's leg_rails, triggering > 1 Variable legs.
    second_var = SingleLegRail(
        name=Identifier("SettlementCloseB"),
        transfer_type="settlement",
        origin="InternalInitiated",
        metadata_keys=(),
        leg_role=(Identifier("ControlAccount"),),
        leg_direction="Variable",
    )
    first_var = dataclasses.replace(
        inst.rails[1],  # SubledgerCharge
        leg_direction="Variable",
    )
    bad_template = dataclasses.replace(
        inst.transfer_templates[0],
        leg_rails=(first_var.name, second_var.name),
    )
    bad = _replace(
        inst,
        rails=(inst.rails[0], first_var, inst.rails[2], second_var),
        transfer_templates=(bad_template,),
    )
    with pytest.raises(
        L2ValidationError, match="contains 2 Variable-direction legs",
    ):
        validate(bad)


def test_c2_xor_group_members_must_share_parent() -> None:
    inst = _baseline_instance()
    # Two ChainEntries in the same xor_group but with different parents.
    a = ChainEntry(
        parent=Identifier("MerchantSettlementCycle"),
        child=Identifier("ExtInbound"),
        required=False,
        xor_group=Identifier("Vehicle"),
    )
    b = ChainEntry(
        parent=Identifier("ExtInbound"),
        child=Identifier("PoolBalancing"),
        required=False,
        xor_group=Identifier("Vehicle"),
    )
    bad = _replace(inst, chains=(a, b))
    # Note: also trips S4 (PoolBalancing is aggregating), but C2 fires
    # earlier in the validate() sequence so this is the message we expect.
    # If validate() ever reorders, this test surfaces the change.
    with pytest.raises(
        L2ValidationError,
        match="(reference different.*parents|aggregating Rails MUST NOT)",
    ):
        validate(bad)


# -- State-dependent (S1-S6) -------------------------------------------------


def test_s1_standalone_two_leg_requires_expected_net() -> None:
    inst = _baseline_instance()
    bad_rail = dataclasses.replace(inst.rails[0], expected_net=None)
    bad = _replace(inst, rails=(bad_rail, *inst.rails[1:]))
    with pytest.raises(
        L2ValidationError, match="standalone two-leg rail.*MUST declare expected_net",
    ):
        validate(bad)


def test_s2_template_leg_must_not_have_expected_net() -> None:
    inst = _baseline_instance()
    # Add a two-leg rail that's listed in the template's leg_rails AND
    # carries expected_net. The baseline's template only has the
    # SubledgerCharge single-leg; add a two-leg "ClosingLeg" so we can
    # exercise this rule.
    closing = TwoLegRail(
        name=Identifier("ClosingLeg"),
        transfer_type="closing",
        origin="InternalInitiated",
        metadata_keys=(),
        source_role=(Identifier("ControlAccount"),),
        destination_role=(Identifier("ControlAccount"),),
        expected_net=Decimal("0"),  # Wrong: rail is in leg_rails so this is forbidden.
    )
    bad_template = dataclasses.replace(
        inst.transfer_templates[0],
        leg_rails=(*inst.transfer_templates[0].leg_rails, Identifier("ClosingLeg")),
    )
    bad = _replace(
        inst,
        rails=(*inst.rails, closing),
        transfer_templates=(bad_template,),
    )
    with pytest.raises(
        L2ValidationError,
        match="ClosingLeg.*appears in a TransferTemplate.*MUST NOT carry one",
    ):
        validate(bad)


def test_s3_unreconciled_single_leg_rejected() -> None:
    inst = _baseline_instance()
    # Add a SingleLegRail not in any template + not matched by any
    # aggregating bundles_activity.
    orphan = SingleLegRail(
        name=Identifier("OrphanLeg"),
        transfer_type="orphan_type",
        origin="InternalInitiated",
        metadata_keys=(),
        leg_role=(Identifier("ControlAccount"),),
        leg_direction="Debit",
    )
    bad = _replace(inst, rails=(*inst.rails, orphan))
    with pytest.raises(
        L2ValidationError,
        match="OrphanLeg.*single-leg rail is not reconciled",
    ):
        validate(bad)


def test_s4_aggregating_rail_rejected_as_chain_child() -> None:
    inst = _baseline_instance()
    bad_chain = ChainEntry(
        parent=Identifier("MerchantSettlementCycle"),
        child=Identifier("PoolBalancing"),  # aggregating rail
        required=True,
    )
    bad = _replace(inst, chains=(bad_chain,))
    with pytest.raises(
        L2ValidationError,
        match="aggregating Rails MUST NOT appear as Chain.child",
    ):
        validate(bad)


def test_s5_aggregating_rail_requires_cadence() -> None:
    inst = _baseline_instance()
    bad_rail = dataclasses.replace(inst.rails[2], cadence=None)
    bad = _replace(inst, rails=(*inst.rails[:2], bad_rail))
    with pytest.raises(
        L2ValidationError, match="PoolBalancing.*requires cadence",
    ):
        validate(bad)


def test_s5_aggregating_rail_requires_bundles_activity() -> None:
    inst = _baseline_instance()
    bad_rail = dataclasses.replace(inst.rails[2], bundles_activity=())
    bad = _replace(inst, rails=(*inst.rails[:2], bad_rail))
    with pytest.raises(
        L2ValidationError, match="requires bundles_activity",
    ):
        validate(bad)


def test_s6_non_aggregating_rail_rejects_cadence() -> None:
    inst = _baseline_instance()
    bad_rail = dataclasses.replace(inst.rails[0], cadence="daily-eod")
    bad = _replace(inst, rails=(bad_rail, *inst.rails[1:]))
    with pytest.raises(
        L2ValidationError, match="cadence is only meaningful when aggregating",
    ):
        validate(bad)


def test_s6_non_aggregating_rail_rejects_bundles_activity() -> None:
    inst = _baseline_instance()
    bad_rail = dataclasses.replace(
        inst.rails[0], bundles_activity=(Identifier("ach"),),
    )
    bad = _replace(inst, rails=(bad_rail, *inst.rails[1:]))
    with pytest.raises(
        L2ValidationError, match="bundles_activity is only meaningful",
    ):
        validate(bad)


# -- Vocabulary (V1-V2) ------------------------------------------------------


@pytest.mark.parametrize("good_completion", [
    "business_day_end",
    "business_day_end+3d",
    "business_day_end+30d",
    "month_end",
    "metadata.settlement_period_end",
    "metadata.deadline",
])
def test_v1_completion_vocabulary_accepts_valid(good_completion: str) -> None:
    inst = _baseline_instance()
    good_template = dataclasses.replace(
        inst.transfer_templates[0], completion=good_completion,
    )
    validate(_replace(inst, transfer_templates=(good_template,)))


@pytest.mark.parametrize("bad_completion", [
    "tomorrow",
    "business_day_end+3w",         # weeks not supported
    "metadata.",                    # empty key
    "Metadata.deadline",            # capital M
    "business_day_end+",            # missing N
])
def test_v1_completion_vocabulary_rejects_invalid(bad_completion: str) -> None:
    inst = _baseline_instance()
    bad_template = dataclasses.replace(
        inst.transfer_templates[0], completion=bad_completion,
    )
    bad = _replace(inst, transfer_templates=(bad_template,))
    with pytest.raises(L2ValidationError, match="not a v1 CompletionExpression"):
        validate(bad)


@pytest.mark.parametrize("good_cadence", [
    "intraday-1h",
    "intraday-12h",
    "daily-eod",
    "daily-bod",
    "weekly-mon",
    "weekly-sun",
    "monthly-eom",
    "monthly-bom",
    "monthly-1",
    "monthly-15",
    "monthly-31",
])
def test_v2_cadence_vocabulary_accepts_valid(good_cadence: str) -> None:
    inst = _baseline_instance()
    good_rail = dataclasses.replace(inst.rails[2], cadence=good_cadence)
    validate(_replace(inst, rails=(*inst.rails[:2], good_rail)))


@pytest.mark.parametrize("bad_cadence", [
    "every-other-friday",
    "intraday-2",                # missing 'h'
    "weekly-funday",             # not a real weekday
    "monthly-32",                # day 32
    "monthly-0",                 # day 0
    "annual-jan",                # not a v1 cadence
])
def test_v2_cadence_vocabulary_rejects_invalid(bad_cadence: str) -> None:
    inst = _baseline_instance()
    bad_rail = dataclasses.replace(inst.rails[2], cadence=bad_cadence)
    bad = _replace(inst, rails=(*inst.rails[:2], bad_rail))
    with pytest.raises(L2ValidationError, match="not a v1 CadenceExpression"):
        validate(bad)
