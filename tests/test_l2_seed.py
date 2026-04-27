"""Tests for the M.2.2 sasquatch_ar seed generator.

The generator emits SQL INSERTs against the v6 prefixed schema. Unit
tests here verify the OUTPUT shape (right columns, right values for each
planted scenario, deterministic across runs); the actual "execute against
real Postgres + run L1 invariant queries + assert exception rows surface"
verification is M.2.6's integration-test substep.

Naming + structure mirror the M.2.7 hash-lock pattern that lands later:
``test_default_scenario_is_deterministic`` is the seed for re-locking
the M.2.7 SHA256 once the generator stabilizes.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from quicksight_gen.common.l2 import (
    Identifier,
    Name,
    emit_schema,
    load_instance,
)

from tests.l2.sasquatch_ar_seed import (
    DriftPlant,
    LimitBreachPlant,
    OverdraftPlant,
    ScenarioPlant,
    TemplateInstance,
    default_ar_scenario,
    emit_seed,
)


YAML_PATH = Path(__file__).parent / "l2" / "sasquatch_ar.yaml"
REFERENCE_DATE = date(2026, 4, 25)  # pinned so tests are stable


@pytest.fixture(scope="module")
def instance():
    """Cached load of the sasquatch_ar L2 instance."""
    return load_instance(YAML_PATH)


@pytest.fixture(scope="module")
def default_seed_sql(instance) -> str:
    """The default scenario's seed SQL — used by every shape test."""
    return emit_seed(instance, default_ar_scenario(today=REFERENCE_DATE))


# -- Smoke -------------------------------------------------------------------


def test_seed_emits_non_empty_sql(default_seed_sql: str) -> None:
    """Sanity: the generator produces an output string."""
    assert default_seed_sql.strip()
    assert "INSERT INTO" in default_seed_sql


def test_seed_uses_l2_instance_prefix(default_seed_sql: str) -> None:
    """All INSERTs are against the prefixed tables per F10 isolation."""
    assert "INSERT INTO sasquatch_ar_transactions" in default_seed_sql
    assert "INSERT INTO sasquatch_ar_daily_balances" in default_seed_sql


def test_seed_emits_schema_compatible_columns(default_seed_sql: str) -> None:
    """Every transaction INSERT lists the v1.1 column set in order."""
    expected_cols = (
        "(id, account_id, account_name, account_role, account_scope, "
        "account_parent_role, amount_money, amount_direction, status, "
        "posting, transfer_id, transfer_type, transfer_completion, "
        "transfer_parent_id, rail_name, template_name, bundle_id, "
        "supersedes, origin, metadata)"
    )
    assert expected_cols in default_seed_sql


# -- Drift scenario ----------------------------------------------------------


def test_drift_plant_produces_two_credit_legs(default_seed_sql: str) -> None:
    """Two $100 inbound credits land on the drift account that day."""
    drift_credits = re.findall(
        r"\(\s*'tx-drift-\d+',\s*'cust-900-0001-bigfoot-brews'.*?'Credit'",
        default_seed_sql,
        re.DOTALL,
    )
    assert len(drift_credits) == 2


def test_drift_balance_row_disagrees_with_computed(
    default_seed_sql: str,
) -> None:
    """Stored daily_balances.money for the drift account-date is $275 —
    $75 higher than the $200 sum of postings (delta_money on the plant)."""
    # Match: bigfoot-brews row dated 2026-04-20 (drift_day = today - 5d)
    pattern = re.compile(
        r"\(\s*'cust-900-0001-bigfoot-brews',[^)]*?"
        r"'2026-04-20T00:00:00\+00:00',\s*'2026-04-21T00:00:00\+00:00',\s*"
        r"(?P<money>-?\d+\.\d+)",
        re.DOTALL,
    )
    m = pattern.search(default_seed_sql)
    assert m is not None, "drift balance row not found"
    assert Decimal(m.group("money")) == Decimal("275.00")


# -- Overdraft scenario ------------------------------------------------------


def test_overdraft_balance_row_is_negative(default_seed_sql: str) -> None:
    """Stored money on the overdraft account-date is < 0."""
    pattern = re.compile(
        r"\(\s*'cust-900-0002-sasquatch-sips',[^)]*?"
        r"'2026-04-19T00:00:00\+00:00',\s*'2026-04-20T00:00:00\+00:00',\s*"
        r"(?P<money>-?\d+\.\d+)",
        re.DOTALL,
    )
    m = pattern.search(default_seed_sql)
    assert m is not None, "overdraft balance row not found"
    assert Decimal(m.group("money")) < 0
    assert Decimal(m.group("money")) == Decimal("-1500.00")


def test_overdraft_plant_rejects_non_negative_money() -> None:
    """OverdraftPlant.money must be negative; positive is a configuration smell."""
    bad = OverdraftPlant(
        account_id=Identifier("cust-001"),
        days_ago=1,
        money=Decimal("100.00"),
    )
    instances = (
        TemplateInstance(
            template_role=Identifier("CustomerDDA"),
            account_id=Identifier("cust-001"),
            name=Name("Test"),
        ),
    )
    inst = load_instance(YAML_PATH)
    with pytest.raises(ValueError, match="must be negative"):
        emit_seed(
            inst,
            ScenarioPlant(
                template_instances=instances,
                overdraft_plants=(bad,),
                today=REFERENCE_DATE,
            ),
        )


# -- Limit-breach scenario --------------------------------------------------


def test_limit_breach_plant_produces_outbound_debit_above_cap(
    default_seed_sql: str,
) -> None:
    """The breach row debits the customer DDA by $22k via wire — exceeds
    the $15k LimitSchedule cap on (DDAControl, wire)."""
    # Find the customer-DDA debit leg of the breach transfer.
    pattern = re.compile(
        r"\(\s*'tx-breach-0001',\s*'cust-700-0001-big-meadow-dairy'.*?"
        r"(?P<money>-?\d+\.\d+),\s*'Debit'",
        re.DOTALL,
    )
    m = pattern.search(default_seed_sql)
    assert m is not None, "breach customer-DDA debit row not found"
    breach_amount = abs(Decimal(m.group("money")))
    # The $15k wire cap from sasquatch_ar.yaml's limit_schedules.
    assert breach_amount > Decimal("15000.00")


def test_limit_breach_emits_balanced_2_leg_transfer(
    default_seed_sql: str,
) -> None:
    """Both legs of the breach transfer (debit on customer + credit on
    External) land in the seed — needed for L1 Conservation when the
    ETL eventually validates expected_net=0."""
    debit_pattern = (
        r"'tx-breach-0001',\s*'cust-700-0001-big-meadow-dairy'.*?'Debit'"
    )
    credit_pattern = (
        r"'tx-breach-0001-ext',\s*'ext-frb-snb-master'.*?'Credit'"
    )
    assert re.search(debit_pattern, default_seed_sql, re.DOTALL)
    assert re.search(credit_pattern, default_seed_sql, re.DOTALL)


def test_limit_breach_uses_correct_rail_and_transfer_type(
    default_seed_sql: str,
) -> None:
    """Rail name and transfer_type on the breach row match the plant
    declaration — the LimitSchedule lookup matches by parent_role + type."""
    pattern = re.compile(
        r"'tx-breach-0001',\s*'cust-700-0001-big-meadow-dairy'.*?"
        r"'wire'.*?'CustomerOutboundWire'",
        re.DOTALL,
    )
    assert pattern.search(default_seed_sql)


# -- Sign-direction agreement (L1 Amount invariant) --------------------------


def test_every_debit_row_has_non_positive_money(default_seed_sql: str) -> None:
    """Every emitted Debit row carries amount_money <= 0 (sign-direction
    invariant — same one the schema enforces via CHECK)."""
    for m in re.finditer(
        r"\((?P<row>[^)]*?'Debit'[^)]*?)\)",
        default_seed_sql,
    ):
        money_match = re.search(r"(-?\d+\.\d+),\s*'Debit'", m.group("row"))
        assert money_match, f"no money/direction pair in: {m.group('row')!r}"
        assert Decimal(money_match.group(1)) <= 0


def test_every_credit_row_has_non_negative_money(default_seed_sql: str) -> None:
    """Every emitted Credit row carries amount_money >= 0."""
    for m in re.finditer(
        r"\((?P<row>[^)]*?'Credit'[^)]*?)\)",
        default_seed_sql,
    ):
        money_match = re.search(r"(-?\d+\.\d+),\s*'Credit'", m.group("row"))
        assert money_match, f"no money/direction pair in: {m.group('row')!r}"
        assert Decimal(money_match.group(1)) >= 0


# -- Determinism ------------------------------------------------------------


def test_default_scenario_is_deterministic(instance) -> None:
    """Two calls with the same scenario produce byte-identical output —
    pre-requisite for the M.2.7 SHA256 hash-lock."""
    sql1 = emit_seed(instance, default_ar_scenario(today=REFERENCE_DATE))
    sql2 = emit_seed(instance, default_ar_scenario(today=REFERENCE_DATE))
    assert sql1 == sql2


def test_default_scenario_hash_is_locked(default_seed_sql: str) -> None:
    """SHA256 hash-lock — M.2a.8 (replaces deprecated M.2.7 substep).

    Any silent generator drift (different scenario count, reordered
    plants, changed reference date math) flips this hash and trips
    the test loudly. Re-lock by pasting the printed digest below in
    the same commit that intentionally changes the generator.
    """
    h = hashlib.sha256(default_seed_sql.encode("utf-8")).hexdigest()
    assert h == (
        "cd237706b7211985dcbdd02bd78aa0d9c2f838ce63124be4910b7702d260ac98"
    ), f"sasquatch_ar L2 seed drifted; new hash: {h}"


# -- Multiple plants of the same kind ----------------------------------------


def test_multiple_drift_plants_each_get_their_own_balance_row(
    instance,
) -> None:
    """Two drift plants on different accounts → two distinct balance rows."""
    instances = (
        TemplateInstance(
            template_role=Identifier("CustomerDDA"),
            account_id=Identifier("cust-001"),
            name=Name("Customer 1"),
        ),
        TemplateInstance(
            template_role=Identifier("CustomerDDA"),
            account_id=Identifier("cust-002"),
            name=Name("Customer 2"),
        ),
    )
    sql = emit_seed(
        instance,
        ScenarioPlant(
            template_instances=instances,
            drift_plants=(
                DriftPlant(
                    account_id=Identifier("cust-001"),
                    days_ago=3,
                    delta_money=Decimal("50.00"),
                ),
                DriftPlant(
                    account_id=Identifier("cust-002"),
                    days_ago=4,
                    delta_money=Decimal("-30.00"),
                ),
            ),
            today=REFERENCE_DATE,
        ),
    )
    # Both drift balance rows present.
    assert "'cust-001'" in sql
    assert "'cust-002'" in sql
    # Day 3 → 2026-04-22; day 4 → 2026-04-21
    assert "'2026-04-22T00:00:00+00:00'" in sql
    assert "'2026-04-21T00:00:00+00:00'" in sql


def test_unknown_account_id_in_plant_raises(instance) -> None:
    """Plant referencing an account not in template_instances fails loudly."""
    with pytest.raises(KeyError, match="not declared"):
        emit_seed(
            instance,
            ScenarioPlant(
                template_instances=(),  # no instances declared
                drift_plants=(
                    DriftPlant(
                        account_id=Identifier("ghost-account"),
                        days_ago=1,
                        delta_money=Decimal("10.00"),
                    ),
                ),
                today=REFERENCE_DATE,
            ),
        )


# -- Schema compatibility (visual sanity, not actual SQL execution) ---------


def test_seed_sql_concats_with_schema_sql_into_a_pipeline(instance) -> None:
    """`emit_schema(inst) + emit_seed(inst, ...)` is the M.2.6 pipeline.
    Smoke: concatenation is well-formed SQL that ends with a semicolon
    and includes the prefixed table names from both stages."""
    schema_sql = emit_schema(instance)
    seed_sql = emit_seed(instance, default_ar_scenario(today=REFERENCE_DATE))
    pipeline = schema_sql + "\n" + seed_sql
    assert pipeline.rstrip().endswith(";")
    # Schema's CREATE + seed's INSERT both reference the same prefixed table.
    assert "CREATE TABLE sasquatch_ar_transactions" in pipeline
    assert "INSERT INTO sasquatch_ar_transactions" in pipeline
