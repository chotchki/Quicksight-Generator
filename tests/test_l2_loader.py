"""Loader tests for ``common.l2.load_instance`` (M.1.2).

Coverage split:
- Happy path against the spike's ``slice.yaml`` (round-trip every primitive
  the spike fixture exercises — currently 1 Account + 1 TwoLegRail).
- Inline kitchen-sink YAML covering every primitive shape — including
  AccountTemplate, both rail shapes, aggregating rails, TransferTemplate,
  ChainEntry with XOR group, LimitSchedule.
- Per-helper rejection tests: F4 Money coercion, F5 InstancePrefix regex
  + length cap, Rail discrimination, missing-required-field paths.

Per the M.1 testing principle (every load-time validator gets a rejection
test): each rejection lands here as it surfaces. Cross-entity validation
(singleton-ParentRole, ≤1 Variable leg, vocabulary literals) is M.1.3
territory and gets its own ``test_l2_validate.py``.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from textwrap import dedent

import pytest

from quicksight_gen.common.l2 import (
    L2LoaderError,
    SingleLegRail,
    TwoLegRail,
    load_instance,
)


SLICE_YAML = Path(__file__).parent / "spike" / "slice.yaml"


# -- Happy paths --------------------------------------------------------------


def test_loads_spike_slice_yaml() -> None:
    """The spike's slice.yaml round-trips cleanly into typed primitives."""
    inst = load_instance(SLICE_YAML)
    assert inst.instance == "spk"
    assert {a.id for a in inst.accounts} == {"int-001", "ext-001"}
    int_acc = next(a for a in inst.accounts if a.id == "int-001")
    assert int_acc.name == "Internal Operations Account"
    assert int_acc.role == "InternalDDA"
    assert int_acc.scope == "internal"

    assert len(inst.rails) == 1
    rail = inst.rails[0]
    assert isinstance(rail, TwoLegRail)
    assert rail.name == "ExtInbound"
    # RoleExpression normalized to a 1-tuple.
    assert rail.source_role == ("ExternalCounterparty",)
    assert rail.destination_role == ("InternalDDA",)
    assert rail.expected_net == Decimal("0")
    assert rail.aggregating is False
    assert rail.metadata_keys == ("external_reference",)


def test_loads_kitchen_sink_yaml_inline(tmp_path: Path) -> None:
    """Every primitive at least once + aggregating + xor + union role."""
    yaml_text = dedent("""\
        instance: ksk

        accounts:
          - id: gl-control
            name: Control Account
            role: ControlAccount
            scope: internal
            expected_eod_balance: 0

          - id: ext-counter
            role: ExternalCounterparty
            scope: external

        account_templates:
          - role: CustomerSubledger
            scope: internal
            parent_role: ControlAccount

          - role: MerchantLedger
            scope: internal
            parent_role: ControlAccount
            expected_eod_balance: 100.50

        rails:
          - name: SubledgerCharge
            transfer_type: charge
            origin: InternalInitiated
            metadata_keys: [merchant_id, settlement_period]
            leg_role: CustomerSubledger
            leg_direction: Debit

          - name: ExtInbound
            transfer_type: ach
            origin: ExternalForcePosted
            metadata_keys: [external_reference]
            source_role: [ExternalCounterparty, MerchantLedger]
            destination_role: ControlAccount
            expected_net: 0

          - name: PoolBalancing
            transfer_type: pool_balancing
            origin: InternalInitiated
            metadata_keys: []
            source_role: ControlAccount
            destination_role: ControlAccount
            expected_net: 0
            aggregating: true
            bundles_activity: [SubledgerCharge, ach]
            cadence: intraday-2h

        transfer_templates:
          - name: MerchantSettlementCycle
            transfer_type: settlement_cycle
            expected_net: 0
            transfer_key: [merchant_id, settlement_period]
            completion: metadata.settlement_period_end
            leg_rails: [SubledgerCharge]

        chains:
          - parent: MerchantSettlementCycle
            child: MerchantPayoutACH
            required: true
            xor_group: PayoutVehicle

        limit_schedules:
          - parent_role: ControlAccount
            transfer_type: ach
            cap: 5000.00
        """)
    p = tmp_path / "kitchen.yaml"
    p.write_text(yaml_text)

    inst = load_instance(p)
    assert inst.instance == "ksk"
    assert len(inst.accounts) == 2
    assert len(inst.account_templates) == 2
    assert len(inst.rails) == 3
    assert len(inst.transfer_templates) == 1
    assert len(inst.chains) == 1
    assert len(inst.limit_schedules) == 1

    # Single-leg + two-leg discrimination
    by_name = {r.name: r for r in inst.rails}
    assert isinstance(by_name["SubledgerCharge"], SingleLegRail)
    assert isinstance(by_name["ExtInbound"], TwoLegRail)
    assert isinstance(by_name["PoolBalancing"], TwoLegRail)

    # Union role → tuple of identifiers
    ext_inbound = by_name["ExtInbound"]
    assert isinstance(ext_inbound, TwoLegRail)
    assert ext_inbound.source_role == ("ExternalCounterparty", "MerchantLedger")
    # Single-string role → 1-tuple
    assert ext_inbound.destination_role == ("ControlAccount",)

    # Aggregating fields populated correctly
    pool = by_name["PoolBalancing"]
    assert isinstance(pool, TwoLegRail)
    assert pool.aggregating is True
    assert pool.bundles_activity == ("SubledgerCharge", "ach")
    assert pool.cadence == "intraday-2h"

    # Money coercion
    template = inst.transfer_templates[0]
    assert template.expected_net == Decimal("0")
    assert inst.limit_schedules[0].cap == Decimal("5000.00")

    # Optional fields default cleanly
    chain = inst.chains[0]
    assert chain.required is True
    assert chain.xor_group == "PayoutVehicle"

    # AccountTemplate Money coercion (the float-precision case for F4)
    merchant_tmpl = inst.account_templates[1]
    assert merchant_tmpl.expected_eod_balance == Decimal("100.50")


# -- F4 Money coercion --------------------------------------------------------


def test_money_coercion_dodges_float_precision(tmp_path: Path) -> None:
    """Per F4: Decimal(str(value)) instead of Decimal(value) — preserves '0.1'."""
    yaml_text = dedent("""\
        instance: pre
        accounts:
          - id: a1
            scope: internal
            role: A
            expected_eod_balance: 0.1
        rails:
          - name: R
            transfer_type: t
            origin: o
            source_role: A
            destination_role: A
            expected_net: 0.1
        """)
    p = tmp_path / "money.yaml"
    p.write_text(yaml_text)

    inst = load_instance(p)
    assert inst.accounts[0].expected_eod_balance == Decimal("0.1")
    rail = inst.rails[0]
    assert isinstance(rail, TwoLegRail)
    assert rail.expected_net == Decimal("0.1")
    # The naive Decimal(0.1) would yield '0.1000000000000000055...'; F4
    # explicitly avoids that by going through str().
    assert str(rail.expected_net) == "0.1"


def test_money_rejects_non_numeric(tmp_path: Path) -> None:
    """Money fields reject obvious garbage."""
    yaml_text = dedent("""\
        instance: pre
        accounts:
          - id: a1
            scope: internal
            expected_eod_balance: "not a number"
        rails: []
        """)
    p = tmp_path / "bad_money.yaml"
    p.write_text(yaml_text)
    with pytest.raises(L2LoaderError, match="not a valid decimal"):
        load_instance(p)


# -- F5 InstancePrefix regex + length cap -------------------------------------


@pytest.mark.parametrize("bad_prefix", [
    "Sasq",        # uppercase
    "1bank",       # leading digit
    "my-bank",     # hyphen not allowed
    "my bank",     # space
    "",            # empty string
])
def test_instance_prefix_regex_rejects(bad_prefix: str, tmp_path: Path) -> None:
    """Per F5: InstancePrefix MUST match ^[a-z][a-z0-9_]*$."""
    p = tmp_path / "bad_prefix.yaml"
    p.write_text(f'instance: "{bad_prefix}"\naccounts: []\nrails: []\n')
    with pytest.raises(L2LoaderError):
        load_instance(p)


def test_instance_prefix_30_char_cap(tmp_path: Path) -> None:
    """Per F5: max 30 characters."""
    long_prefix = "a" * 31
    p = tmp_path / "long.yaml"
    p.write_text(f'instance: "{long_prefix}"\naccounts: []\nrails: []\n')
    with pytest.raises(L2LoaderError, match="max 30 characters"):
        load_instance(p)


def test_instance_prefix_accepts_max_length(tmp_path: Path) -> None:
    """Exactly 30 chars works."""
    p = tmp_path / "max.yaml"
    p.write_text(f'instance: "{"a" * 30}"\naccounts: []\nrails: []\n')
    inst = load_instance(p)
    assert len(inst.instance) == 30


# -- Rail discrimination ------------------------------------------------------


def test_rail_rejects_both_two_leg_and_single_leg(tmp_path: Path) -> None:
    """A Rail cannot declare both shape's fields."""
    yaml_text = dedent("""\
        instance: pre
        accounts:
          - id: a
            scope: internal
            role: R
        rails:
          - name: BadRail
            transfer_type: t
            origin: o
            source_role: R
            destination_role: R
            expected_net: 0
            leg_role: R
            leg_direction: Debit
        """)
    p = tmp_path / "both.yaml"
    p.write_text(yaml_text)
    with pytest.raises(L2LoaderError, match="not both"):
        load_instance(p)


def test_rail_rejects_neither_shape(tmp_path: Path) -> None:
    """A Rail must declare at least one shape."""
    yaml_text = dedent("""\
        instance: pre
        accounts: []
        rails:
          - name: BadRail
            transfer_type: t
            origin: o
        """)
    p = tmp_path / "neither.yaml"
    p.write_text(yaml_text)
    with pytest.raises(L2LoaderError, match="EITHER two-leg .* OR single-leg"):
        load_instance(p)


def test_two_leg_rail_requires_both_role_fields(tmp_path: Path) -> None:
    """Source-only or destination-only is rejected."""
    yaml_text = dedent("""\
        instance: pre
        accounts: []
        rails:
          - name: BadRail
            transfer_type: t
            origin: o
            source_role: R
            expected_net: 0
        """)
    p = tmp_path / "src_only.yaml"
    p.write_text(yaml_text)
    with pytest.raises(L2LoaderError, match="both source_role and destination_role"):
        load_instance(p)


# -- Top-level shape ---------------------------------------------------------


def test_missing_instance_field_rejected(tmp_path: Path) -> None:
    p = tmp_path / "no_instance.yaml"
    p.write_text("accounts: []\nrails: []\n")
    with pytest.raises(L2LoaderError, match="missing required field 'instance'"):
        load_instance(p)


def test_empty_yaml_rejected(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("")
    with pytest.raises(L2LoaderError, match="file is empty"):
        load_instance(p)


def test_malformed_yaml_rejected(tmp_path: Path) -> None:
    p = tmp_path / "malformed.yaml"
    p.write_text("instance: spk\n  accounts: [oops bad indent\n")
    with pytest.raises(L2LoaderError, match="YAML syntax error"):
        load_instance(p)


def test_top_level_must_be_mapping(tmp_path: Path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("- not\n- a\n- mapping\n")
    with pytest.raises(L2LoaderError, match="top level must be a mapping"):
        load_instance(p)


def test_missing_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(L2LoaderError, match="could not read"):
        load_instance(tmp_path / "nonexistent.yaml")
