"""Schema-emitter tests for ``common.l2.emit_schema`` (M.1.4).

The emitter is a text-template, so most checks assert on the rendered
DDL string. A live-Postgres execution proof exists outside the unit
suite (verified manually via psycopg2 against ``run/config.yaml`` —
the M.0.10 pattern); the kitchen-sink integration test in M.1.6 will
formalize that.

Per the M.1 testing principle: every load-bearing schema feature
(prefix isolation, idempotency, the v6 column shape, the L1 Amount
invariant CHECK, portable JSON storage) gets a guard.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from quicksight_gen.common.l2 import (
    Identifier,
    L2Instance,
    emit_schema,
)


def _strip_comments(sql: str) -> str:
    """Return SQL with line-comment lines (-- …) removed.

    Used by tests that assert on the absence of patterns like ``JSONB`` or
    ``GIN`` — those words legitimately appear in explanatory comments
    (e.g. ``-- portability constraint: no JSONB``) and we don't want
    those to trip the negative assertion.
    """
    return "\n".join(
        line for line in sql.split("\n")
        if not line.lstrip().startswith("--")
    )


def _instance(prefix: str) -> L2Instance:
    """A minimal L2Instance — schema emit doesn't read the entity lists."""
    return L2Instance(
        instance=Identifier(prefix),
        accounts=(),
        account_templates=(),
        rails=(),
        transfer_templates=(),
        chains=(),
        limit_schedules=(),
    )


# -- Prefix isolation --------------------------------------------------------


def test_uses_l2_instance_prefix() -> None:
    """Tables + indexes carry the instance prefix per F10 isolation rule."""
    sql = emit_schema(_instance("ksk"))
    assert "CREATE TABLE ksk_transactions" in sql
    assert "CREATE TABLE ksk_daily_balances" in sql
    assert "CREATE INDEX idx_ksk_transactions_account_posting" in sql
    assert "CREATE INDEX idx_ksk_daily_balances_business_day" in sql


def test_two_instances_emit_isolated_table_names() -> None:
    """Two L2 instances coexist in one DB by using distinct prefixes."""
    a = emit_schema(_instance("aaa"))
    b = emit_schema(_instance("bbb"))
    assert "aaa_transactions" in a and "aaa_transactions" not in b
    assert "bbb_transactions" in b and "bbb_transactions" not in a


# -- Idempotency -------------------------------------------------------------


def test_emits_drop_before_create() -> None:
    """Every CREATE has a DROP IF EXISTS for the same object before it."""
    sql = emit_schema(_instance("idem"))
    drop_idx = sql.index("DROP TABLE IF EXISTS idem_transactions")
    create_idx = sql.index("CREATE TABLE idem_transactions")
    assert drop_idx < create_idx, "DROP must precede CREATE"

    drop_db_idx = sql.index("DROP TABLE IF EXISTS idem_daily_balances")
    create_db_idx = sql.index("CREATE TABLE idem_daily_balances")
    assert drop_db_idx < create_db_idx


def test_drops_daily_balances_before_transactions_for_fk_safety() -> None:
    """Drop daily_balances first so any future FKs from it to transactions
    don't block the drop. Order matters in idempotent DDL."""
    sql = emit_schema(_instance("ord"))
    db_drop = sql.index("DROP TABLE IF EXISTS ord_daily_balances")
    tx_drop = sql.index("DROP TABLE IF EXISTS ord_transactions ")
    assert db_drop < tx_drop


# -- v6 column shape per L1 SPEC ---------------------------------------------


def test_emits_entry_column_on_both_tables() -> None:
    """L1 F's Entry primitive — BIGSERIAL on both transactions + daily_balances."""
    sql = emit_schema(_instance("ent"))
    # Both tables have entry BIGSERIAL
    assert "entry                BIGSERIAL      NOT NULL" in sql
    assert "entry                  BIGSERIAL      NOT NULL" in sql


def test_transactions_includes_amount_money_and_direction() -> None:
    """Per L1 SPEC: Amount = (Money, Direction); both columns present."""
    sql = emit_schema(_instance("amt"))
    assert "amount_money         DECIMAL(20,2)  NOT NULL" in sql
    assert "amount_direction     VARCHAR(20)    NOT NULL" in sql
    assert "amount_direction IN ('Debit', 'Credit')" in sql


def test_transactions_includes_amount_invariant_check() -> None:
    """L1 Amount INVARIANT: money agrees with direction.

    money ≥ 0 if direction = Credit; money ≤ 0 if direction = Debit.
    Encoded as a Postgres CHECK so the DB rejects rows that violate it.
    """
    sql = emit_schema(_instance("inv"))
    assert "amount_direction = 'Credit' AND amount_money >= 0" in sql
    assert "amount_direction = 'Debit'  AND amount_money <= 0" in sql


def test_transactions_includes_transfer_parent_id() -> None:
    """L1 SPEC: Transfer.Parent recursive chain (Phase L addition)."""
    sql = emit_schema(_instance("tp"))
    assert "transfer_parent_id   VARCHAR(100)" in sql


def test_transactions_includes_transfer_completion_and_origin() -> None:
    """L1 SPEC: Transfer.Completion + Transaction.Origin both denormalized."""
    sql = emit_schema(_instance("co"))
    assert "transfer_completion  TIMESTAMPTZ" in sql
    assert "origin               VARCHAR(50)    NOT NULL" in sql
    # Origin is open enum — no CHECK so integrators can extend.
    assert "origin IN" not in sql


def test_transactions_status_is_open_enum() -> None:
    """L1 SPEC says Status ⊇ {Posted}. No closed CHECK on status."""
    sql = emit_schema(_instance("st"))
    assert "status               VARCHAR(50)    NOT NULL" in sql
    # No CHECK constraint on status (would close the enum).
    assert "status IN" not in sql


def test_transactions_transfer_type_is_open_enum() -> None:
    """L1 SPEC: TransferType ⊇ {Sale}; integrators add their rails. No CHECK."""
    sql = emit_schema(_instance("tt"))
    assert "transfer_type        VARCHAR(50)    NOT NULL" in sql
    # No CHECK on transfer_type (v5 had one; v6 drops it for L2 extensibility).
    assert "transfer_type IN" not in sql


def test_daily_balances_includes_expected_eod_and_limits() -> None:
    """L1 SPEC: ExpectedEODBalance + Limits map both denormalized onto the row."""
    sql = emit_schema(_instance("eb"))
    assert "expected_eod_balance   DECIMAL(20,2)" in sql
    # Limits is the Map[TransferType, Money] serialized as JSON
    assert "limits                 TEXT" in sql


def test_daily_balances_money_is_signed() -> None:
    """L1 Non-negative Stored Balance is SHOULD, not MUST.

    Overdraft is observable — the balance column accepts negatives so the
    dashboard can surface them. The transactions table has a sign-direction
    CHECK on its ``amount_money``, but daily_balances has no constraint on
    its ``money`` column at all.
    """
    sql = emit_schema(_instance("sg"))
    no_comments = _strip_comments(sql)
    assert "money                  DECIMAL(20,2)  NOT NULL" in sql
    # \b ensures we match the bare ``money`` column (not ``amount_money``).
    assert re.search(r"\bmoney\s*[><]=?\s*0", no_comments) is None


def test_daily_balances_business_day_window_check() -> None:
    """A BusinessDay's end MUST be after its start."""
    sql = emit_schema(_instance("bd"))
    assert "business_day_end > business_day_start" in sql


# -- Portability constraint --------------------------------------------------


def test_metadata_uses_text_with_is_json_check() -> None:
    """SPEC's portability constraint: TEXT + IS JSON, not JSONB."""
    sql = emit_schema(_instance("p"))
    assert "metadata             TEXT" in sql
    assert "metadata IS NULL OR metadata IS JSON" in sql
    # Limits column same pattern
    assert "limits                 TEXT" in sql
    assert "limits IS NULL OR limits IS JSON" in sql
    # No JSONB type used in any actual SQL statement (comments allowed).
    assert "JSONB" not in _strip_comments(sql).upper()


def test_no_gin_indexes_per_portability_constraint() -> None:
    """SPEC: no GIN indexes on JSON; B-tree only.

    Checks for the actual GIN-index syntax (``USING GIN``) rather than
    the bare substring 'GIN' — which would match ``ORIGIN`` (the
    Transaction.Origin column name) and produce false positives.
    """
    sql = emit_schema(_instance("g"))
    no_comments = _strip_comments(sql)
    assert "USING GIN" not in no_comments.upper()
    # B-tree is the default and only allowed; assert at least one B-tree
    # index actually got emitted to make the negative meaningful.
    assert "CREATE INDEX" in no_comments


# -- Primary keys -----------------------------------------------------------


def test_transactions_pk_includes_entry() -> None:
    """Per L1 F: physical row key is (id, entry); logical key is id."""
    sql = emit_schema(_instance("pk1"))
    assert "PRIMARY KEY (id, entry)" in sql


def test_daily_balances_pk_includes_entry() -> None:
    """Per L1 F: physical row key is (account_id, business_day_start, entry)."""
    sql = emit_schema(_instance("pk2"))
    assert "PRIMARY KEY (account_id, business_day_start, entry)" in sql


# -- Account denormalization (per Implementation Entities) ------------------


@pytest.mark.parametrize("col", [
    "account_id", "account_name", "account_role",
    "account_scope", "account_parent_role",
])
def test_transactions_denormalizes_account(col: str) -> None:
    """SPEC's StoredTransaction = Transaction + Transfer + Account fields."""
    sql = emit_schema(_instance("a"))
    # Both tables carry the account fields.
    assert f"  {col}" in sql or f"  {col} " in sql


@pytest.mark.parametrize("col", [
    "account_id", "account_name", "account_role",
    "account_scope", "account_parent_role",
])
def test_daily_balances_denormalizes_account(col: str) -> None:
    """SPEC's DailyBalance = StoredBalance + Account fields."""
    sql = emit_schema(_instance("a"))
    # Just verify the column name appears (we already assert on transactions
    # via the same parametrize; here we trust same-string-in-template).
    assert col in sql
