"""X.4.g — deploy pipeline coverage.

The pipeline module is HTTP-free: each step takes the cfg + an
optional ``DevLogWriter`` (a ``Callable[[Mapping], Awaitable[None]]``)
and returns a primitive (exit code, row count, etc.). Tests assert
against the writer-collected event list, which is the same shape the
studio's POST /deploy endpoint will surface.

Async functions are wrapped in ``asyncio.run`` (project convention —
see tests/unit/test_common_db.py) rather than relying on
``pytest.mark.asyncio`` (the plugin isn't installed).
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from quicksight_gen.common.config import Config
from quicksight_gen.common.db import connect_demo_db, execute_script
from quicksight_gen.common.l2.deploy_pipeline import (
    step_1_etl_hook,
    step_2_wipe,
)
from quicksight_gen.common.l2.loader import load_instance
from quicksight_gen.common.l2.primitives import L2Instance
from quicksight_gen.common.l2.schema import emit_schema, wipe_demo_data_sql
from quicksight_gen.common.sql import Dialect


def _base_cfg() -> Config:
    return Config(
        aws_account_id="111122223333",
        aws_region="us-east-1",
        datasource_arn=(
            "arn:aws:quicksight:us-east-1:111122223333:datasource/x"
        ),
    )


@pytest.fixture
def spec_example_instance() -> L2Instance:
    """Bundled spec_example fixture — the smallest valid L2."""
    return load_instance(Path("tests/l2/spec_example.yaml"))


def _sqlite_cfg(tmp_path: Path) -> Config:
    """Config bound to a fresh SQLite tempfile for orchestrator tests."""
    db_path = tmp_path / "demo.sqlite"
    return Config(
        aws_account_id="111122223333",
        aws_region="us-east-1",
        datasource_arn=(
            "arn:aws:quicksight:us-east-1:111122223333:datasource/x"
        ),
        demo_database_url=f"sqlite:///{db_path}",
        dialect=Dialect.SQLITE,
    )


def _apply_schema_and_plant_two_rows(
    cfg: Config, instance: L2Instance,
) -> None:
    """Set up a SQLite tempfile DB with the L2 schema + two planted rows
    so the wipe has something to delete. Plants conform to the L2 v6
    schema's CHECK constraints (amount_direction enum, sign-direction
    agreement, account_scope enum)."""
    schema_sql = emit_schema(instance, dialect=cfg.dialect)
    p = instance.instance
    plant_tx = (
        f"INSERT INTO {p}_transactions ("
        "id, account_id, account_scope, "
        "amount_money, amount_direction, status, posting, "
        "transfer_id, transfer_type, rail_name, origin"
        ") VALUES ("
        "'t1', 'a1', 'internal', "
        "100.00, 'Credit', 'posted', '2030-01-01 00:00:00', "
        "'g1', 'cash_withdrawal', 'r1', 'inbound'"
        ");"
    )
    plant_bal = (
        f"INSERT INTO {p}_daily_balances ("
        "account_id, account_scope, "
        "business_day_start, business_day_end, money"
        ") VALUES ("
        "'a1', 'internal', "
        "'2030-01-01 00:00:00', '2030-01-02 00:00:00', 100.00"
        ");"
    )
    conn = connect_demo_db(cfg)
    try:
        cur = conn.cursor()
        try:
            execute_script(cur, schema_sql, dialect=cfg.dialect)
            execute_script(
                cur, plant_tx + "\n" + plant_bal, dialect=cfg.dialect,
            )
            conn.commit()
        finally:
            cur.close()
    finally:
        conn.close()


def _row_counts(cfg: Config, instance: L2Instance) -> tuple[int, int]:
    p = instance.instance
    conn = connect_demo_db(cfg)
    try:
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT COUNT(*) FROM {p}_transactions")
            tx = int(cur.fetchone()[0])
            cur.execute(f"SELECT COUNT(*) FROM {p}_daily_balances")
            bal = int(cur.fetchone()[0])
            return tx, bal
        finally:
            cur.close()
    finally:
        conn.close()


class _EventCollector:
    """List-collecting DevLogWriter for assertions."""

    def __init__(self) -> None:
        self.events: list[Mapping[str, object]] = []

    async def __call__(self, payload: Mapping[str, object]) -> None:
        self.events.append(dict(payload))

    def kinds(self) -> list[str]:
        return [str(e.get("event", "")) for e in self.events]

    def by_kind(self, kind: str) -> list[Mapping[str, object]]:
        return [e for e in self.events if e.get("event") == kind]


def _run_step_1(cfg: Config, sink: _EventCollector | None) -> int:
    return asyncio.run(step_1_etl_hook(cfg, dev_log=sink))


# ---------- skip paths ----------

def test_etl_hook_unset_returns_zero_and_emits_skip() -> None:
    cfg = _base_cfg()
    assert cfg.etl_hook is None
    sink = _EventCollector()
    assert _run_step_1(cfg, sink) == 0
    assert sink.kinds() == ["deploy:step1:skip"]
    assert sink.events[0]["reason"] == "etl_hook not configured"


def test_etl_hook_whitespace_only_skips() -> None:
    """Empty / whitespace shlex result is treated as no-op (not error)."""
    cfg = replace(_base_cfg(), etl_hook="   ")
    sink = _EventCollector()
    assert _run_step_1(cfg, sink) == 0
    assert sink.kinds() == ["deploy:step1:skip"]
    assert "empty after shlex" in str(sink.events[0]["reason"])


# ---------- exit code propagation ----------

def test_etl_hook_zero_exit_returns_zero() -> None:
    cfg = replace(_base_cfg(), etl_hook="sh -c 'exit 0'")
    sink = _EventCollector()
    assert _run_step_1(cfg, sink) == 0
    assert "deploy:step1:done" in sink.kinds()
    assert sink.by_kind("deploy:step1:done")[0]["exit_code"] == 0


def test_etl_hook_nonzero_exit_propagates() -> None:
    """Halt contract: caller checks rc != 0 and skips step 2."""
    cfg = replace(_base_cfg(), etl_hook="sh -c 'exit 7'")
    sink = _EventCollector()
    assert _run_step_1(cfg, sink) == 7
    assert sink.by_kind("deploy:step1:done")[0]["exit_code"] == 7


# ---------- streaming ----------

def test_etl_hook_stdout_streams_line_by_line() -> None:
    cfg = replace(_base_cfg(), etl_hook="sh -c 'echo first; echo second'")
    sink = _EventCollector()
    _run_step_1(cfg, sink)
    stdout_lines = [
        e["line"] for e in sink.by_kind("deploy:step1:stdout")
    ]
    assert stdout_lines == ["first", "second"]


def test_etl_hook_stderr_streams_separately() -> None:
    cfg = replace(_base_cfg(), etl_hook=(
        "sh -c 'echo to-stdout; echo to-stderr 1>&2'"
    ))
    sink = _EventCollector()
    _run_step_1(cfg, sink)
    assert [e["line"] for e in sink.by_kind("deploy:step1:stdout")] == [
        "to-stdout",
    ]
    assert [e["line"] for e in sink.by_kind("deploy:step1:stderr")] == [
        "to-stderr",
    ]


def test_etl_hook_event_order_start_then_streams_then_done() -> None:
    """The full lifecycle in order; pipeline orchestration relies on
    this so it can render progress incrementally."""
    cfg = replace(_base_cfg(), etl_hook="sh -c 'echo go; exit 3'")
    sink = _EventCollector()
    assert _run_step_1(cfg, sink) == 3
    kinds = sink.kinds()
    assert kinds[0] == "deploy:step1:start"
    assert kinds[-1] == "deploy:step1:done"
    assert "deploy:step1:stdout" in kinds


# ---------- dev_log opt-out ----------

def test_etl_hook_dev_log_none_does_not_crash() -> None:
    """Pipeline callers may opt out of streaming (e.g. CLI's --quiet)."""
    cfg = replace(_base_cfg(), etl_hook="sh -c 'exit 0'")
    assert _run_step_1(cfg, None) == 0


# ---------- failure modes ----------

def test_etl_hook_missing_binary_propagates() -> None:
    """A missing binary is operator-actionable, NOT a silent skip.
    Whole point of declaring etl_hook is that it MUST run."""
    cfg = replace(
        _base_cfg(),
        etl_hook="/nonexistent/binary/that/does-not-exist arg1",
    )
    sink = _EventCollector()
    with pytest.raises(FileNotFoundError):
        _run_step_1(cfg, sink)
    # `start` event fired before the failure surfaced.
    assert sink.kinds()[0] == "deploy:step1:start"


# ============================================================
# step_2_wipe (X.4.g.5)
# ============================================================


# ---------- SQL emitter ----------

def test_wipe_demo_data_sql_postgres_format(
    spec_example_instance: L2Instance,
) -> None:
    sql = wipe_demo_data_sql(
        spec_example_instance, dialect=Dialect.POSTGRES,
    )
    p = spec_example_instance.instance
    assert f"DELETE FROM {p}_daily_balances;" in sql
    assert f"DELETE FROM {p}_transactions;" in sql


def test_wipe_demo_data_sql_oracle_format(
    spec_example_instance: L2Instance,
) -> None:
    """Oracle accepts the same DELETE statements (case-folds the
    unquoted identifiers to uppercase to match the schema)."""
    sql = wipe_demo_data_sql(
        spec_example_instance, dialect=Dialect.ORACLE,
    )
    p = spec_example_instance.instance
    assert f"DELETE FROM {p}_daily_balances;" in sql
    assert f"DELETE FROM {p}_transactions;" in sql


def test_wipe_demo_data_sql_sqlite_format(
    spec_example_instance: L2Instance,
) -> None:
    sql = wipe_demo_data_sql(
        spec_example_instance, dialect=Dialect.SQLITE,
    )
    p = spec_example_instance.instance
    assert f"DELETE FROM {p}_daily_balances;" in sql
    assert f"DELETE FROM {p}_transactions;" in sql


# ---------- step_2_wipe orchestrator (SQLite tempfile) ----------

def test_step_2_wipe_clears_both_base_tables(
    tmp_path: Path, spec_example_instance: L2Instance,
) -> None:
    cfg = _sqlite_cfg(tmp_path)
    _apply_schema_and_plant_two_rows(cfg, spec_example_instance)
    pre_tx, pre_bal = _row_counts(cfg, spec_example_instance)
    assert (pre_tx, pre_bal) == (1, 1), (
        "fixture should plant exactly one row per table"
    )

    sink = _EventCollector()
    tx_deleted, bal_deleted = asyncio.run(
        step_2_wipe(cfg, spec_example_instance, dev_log=sink),
    )
    assert tx_deleted == 1
    assert bal_deleted == 1

    post_tx, post_bal = _row_counts(cfg, spec_example_instance)
    assert (post_tx, post_bal) == (0, 0)


def test_step_2_wipe_emits_start_then_done_events(
    tmp_path: Path, spec_example_instance: L2Instance,
) -> None:
    cfg = _sqlite_cfg(tmp_path)
    _apply_schema_and_plant_two_rows(cfg, spec_example_instance)
    sink = _EventCollector()
    asyncio.run(step_2_wipe(cfg, spec_example_instance, dev_log=sink))

    kinds = sink.kinds()
    assert kinds == [
        "deploy:step2:wipe:start",
        "deploy:step2:wipe:done",
    ]
    start = sink.by_kind("deploy:step2:wipe:start")[0]
    assert start["instance"] == spec_example_instance.instance
    assert start["dialect"] == "sqlite"
    done = sink.by_kind("deploy:step2:wipe:done")[0]
    assert done["transactions_deleted"] == 1
    assert done["daily_balances_deleted"] == 1


def test_step_2_wipe_dev_log_none_safe(
    tmp_path: Path, spec_example_instance: L2Instance,
) -> None:
    cfg = _sqlite_cfg(tmp_path)
    _apply_schema_and_plant_two_rows(cfg, spec_example_instance)
    tx, bal = asyncio.run(
        step_2_wipe(cfg, spec_example_instance, dev_log=None),
    )
    assert (tx, bal) == (1, 1)


def test_step_2_wipe_idempotent_on_empty_tables(
    tmp_path: Path, spec_example_instance: L2Instance,
) -> None:
    """Wipe-then-wipe is safe — second call reports zero deletes."""
    cfg = _sqlite_cfg(tmp_path)
    _apply_schema_and_plant_two_rows(cfg, spec_example_instance)
    asyncio.run(step_2_wipe(cfg, spec_example_instance, dev_log=None))
    tx, bal = asyncio.run(
        step_2_wipe(cfg, spec_example_instance, dev_log=None),
    )
    assert (tx, bal) == (0, 0)
