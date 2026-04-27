"""Fuzzer meta-guard (M.2d.9.2).

This file is the validation FOR the validator: it runs the
``random_l2_yaml(seed)`` fuzzer across many seeds and asserts that
every emitted YAML loads + cross-entity-validates without raising.
A regression here means the fuzzer itself produces invalid YAML —
catch it before the M.2d.8 contract matrix tries (and gives an
opaque rail-resolution failure instead of "fuzzer produces invalid
output").

Three properties asserted:

1. **Validity** — every seed in ``range(100)`` produces YAML that
   ``load_instance`` accepts (which transitively runs cross-entity
   ``validate``).
2. **Determinism** — same seed = byte-identical output across calls.
3. **Coverage** — across 100 seeds, the fuzzer exercises every
   primitive kind (account, account_template, rail, transfer_template,
   chain, limit_schedule) at least once.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quicksight_gen.common.l2 import load_instance

from tests.l2.fuzz import random_l2_yaml


# 100 seeds covers a lot of variation while keeping wall time low
# (current per-seed cost: well under 10ms).
META_GUARD_SEEDS = list(range(100))


@pytest.mark.parametrize("seed", META_GUARD_SEEDS)
def test_fuzzer_output_loads_and_validates(seed: int, tmp_path: Path) -> None:
    """Every seed produces YAML that ``load_instance`` accepts."""
    yaml_text = random_l2_yaml(seed)
    yaml_path = tmp_path / f"fuzz_{seed}.yaml"
    yaml_path.write_text(yaml_text)
    # load_instance(validate=True) by default — so a single call
    # exercises both the loader's per-entity rules AND the
    # cross-entity validator.
    inst = load_instance(yaml_path)
    # Sanity: instance prefix carries the seed.
    assert str(inst.instance).startswith("fuzz_seed_"), (
        f"seed={seed}: instance prefix doesn't carry the seed marker; "
        f"got {inst.instance!r}"
    )


@pytest.mark.parametrize("seed", [0, 7, 42, 999, 12345])
def test_fuzzer_is_byte_deterministic(seed: int) -> None:
    """Same seed = byte-identical YAML across calls."""
    a = random_l2_yaml(seed)
    b = random_l2_yaml(seed)
    assert a == b, (
        f"seed={seed}: fuzzer is not deterministic — output differs "
        f"between calls. (likely an unseeded random source somewhere)"
    )


def test_fuzzer_exercises_every_primitive_kind_across_seeds(
    tmp_path: Path,
) -> None:
    """Across 100 seeds, the fuzzer produces at least one of every
    primitive kind. If this fails, the fuzzer's variation surface has
    a hole — some primitive never gets generated.
    """
    saw = {
        "accounts": False,
        "account_templates": False,
        "rails": False,
        "transfer_templates": False,
        "chains": False,
        "limit_schedules": False,
        # Specific shapes worth checking too:
        "two_leg_rail": False,
        "single_leg_rail": False,
        "aggregating_rail": False,
        "rail_with_max_pending_age": False,
        "rail_with_max_unbundled_age": False,
        "chain_with_xor_group": False,
    }
    for seed in META_GUARD_SEEDS:
        yaml_text = random_l2_yaml(seed)
        p = tmp_path / f"fuzz_{seed}.yaml"
        p.write_text(yaml_text)
        inst = load_instance(p)
        if inst.accounts:
            saw["accounts"] = True
        if inst.account_templates:
            saw["account_templates"] = True
        if inst.rails:
            saw["rails"] = True
        if inst.transfer_templates:
            saw["transfer_templates"] = True
        if inst.chains:
            saw["chains"] = True
        if inst.limit_schedules:
            saw["limit_schedules"] = True
        for r in inst.rails:
            from quicksight_gen.common.l2 import SingleLegRail, TwoLegRail
            if isinstance(r, TwoLegRail):
                saw["two_leg_rail"] = True
            if isinstance(r, SingleLegRail):
                saw["single_leg_rail"] = True
            if r.aggregating:
                saw["aggregating_rail"] = True
            if r.max_pending_age is not None:
                saw["rail_with_max_pending_age"] = True
            if r.max_unbundled_age is not None:
                saw["rail_with_max_unbundled_age"] = True
        for c in inst.chains:
            if c.xor_group is not None:
                saw["chain_with_xor_group"] = True
        if all(saw.values()):
            return  # short-circuit on full coverage
    missing = [k for k, v in saw.items() if not v]
    assert not missing, (
        f"After {len(META_GUARD_SEEDS)} seeds the fuzzer never produced: "
        f"{missing!r}. Either widen the variation surface in fuzz.py OR "
        f"explicitly accept the gap with a comment in this test."
    )
