"""X.4.g — Studio "Deploy changes" pipeline.

Five-step orchestration that takes the operator's current `cfg` +
`L2Instance` and refreshes the demo DB so the dashboards re-render
against the new shape:

1. **etl_hook gate** — run `cfg.etl_hook` as a subprocess; halt on
   non-zero exit BEFORE step 2 touches the demo DB. (X.4.g.4)
2. **wipe + pull** — wipe demo data, then if `cfg.etl_datasource` is
   set, copy `transactions` + `daily_balances` rows filtered to
   `<= cfg.test_generator.end_date`. (X.4.g.5 / X.4.g.6)
3. **generator** — `emit_full_seed` against the current
   `cfg.test_generator` knobs; always additive. (X.4.g.7-10)
4. **matview refresh** — existing `refresh_matviews_sql(instance)`.
   (X.4.g.11)
5. **reload** — bump `data_generation_id`; Dashboards' open page
   polls and reloads its current URL. (X.4.g.12)

This module is HTTP-free. The studio's `POST /deploy` endpoint
(X.4.g.13) wires up a `DevLogWriter` that emits via `_DEVLOG.info`;
the CLI (a future `quicksight-gen deploy apply` subcommand) wires
one that prints to stdout; tests wire one that appends to a list.
"""
from __future__ import annotations

import asyncio
import shlex
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING

from quicksight_gen.common.db import connect_demo_db, execute_script
from quicksight_gen.common.l2.schema import wipe_demo_data_sql

if TYPE_CHECKING:
    from quicksight_gen.common.config import Config
    from quicksight_gen.common.l2.primitives import L2Instance


# A function the pipeline calls to surface progress / errors. Each
# event is a JSON-serializable mapping with at minimum an ``event``
# key (string identifier like ``deploy:step1:start``) so consumers
# can switch on it. ``None`` disables emission entirely.
DevLogWriter = Callable[[Mapping[str, object]], Awaitable[None]]


async def _emit(
    dev_log: DevLogWriter | None, payload: Mapping[str, object],
) -> None:
    if dev_log is None:
        return
    await dev_log(payload)


async def step_1_etl_hook(
    cfg: Config,
    *,
    dev_log: DevLogWriter | None = None,
) -> int:
    """Run ``cfg.etl_hook`` as a subprocess; stream output to ``dev_log``.

    Returns the subprocess exit code, OR 0 when ``cfg.etl_hook`` is
    unset / empty (no-op skip). Caller checks the return value and
    halts the pipeline if non-zero — step 2's wipe must NOT run when
    the operator's ETL refresh failed.

    The command is ``shlex.split`` then run via
    ``asyncio.create_subprocess_exec`` (NOT ``shell=True``). Stdout
    and stderr stream line-by-line as ``deploy:step1:stdout`` /
    ``deploy:step1:stderr`` events so the operator watches progress
    in the studio's dev_log overlay rather than waiting for the
    subprocess to drain.

    A missing binary (``FileNotFoundError`` from
    ``create_subprocess_exec``) propagates — the caller surfaces it
    as an actionable error, NOT a silent skip. The whole point of
    declaring an ``etl_hook`` is that it MUST run.
    """
    if cfg.etl_hook is None:
        await _emit(dev_log, {
            "event": "deploy:step1:skip",
            "reason": "etl_hook not configured",
        })
        return 0
    cmd = shlex.split(cfg.etl_hook)
    if not cmd:
        await _emit(dev_log, {
            "event": "deploy:step1:skip",
            "reason": "etl_hook is empty after shlex split",
        })
        return 0

    await _emit(dev_log, {
        "event": "deploy:step1:start",
        "cmd": list(cmd),
    })
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _stream(
        stream: asyncio.StreamReader | None, channel: str,
    ) -> None:
        if stream is None:
            return
        # readline() returns b"" on EOF; readuntil(LF) raises at EOF.
        # The ``async for`` over a StreamReader yields chunks split on
        # newline and stops at EOF — that's what we want.
        async for raw_line in stream:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            await _emit(dev_log, {
                "event": f"deploy:step1:{channel}",
                "line": line,
            })

    await asyncio.gather(
        _stream(proc.stdout, "stdout"),
        _stream(proc.stderr, "stderr"),
    )
    rc = await proc.wait()
    await _emit(dev_log, {
        "event": "deploy:step1:done",
        "exit_code": rc,
    })
    return rc


async def step_2_wipe(
    cfg: Config,
    instance: L2Instance,
    *,
    dev_log: DevLogWriter | None = None,
) -> tuple[int, int]:
    """Empty ``<prefix>_transactions`` + ``<prefix>_daily_balances``.

    X.4.g.5 — runs unconditionally (when the pipeline reaches it),
    AFTER step 1's etl_hook gate has succeeded. The matview re-derive
    is step 4's job; this just clears the two base tables so step 2's
    pull (etl_datasource) and step 3's generator both write into clean
    state.

    Returns ``(transactions_deleted, daily_balances_deleted)`` row
    counts so the caller can surface "wiped 12,345 transactions" in
    the deploy summary.

    Sync DB-API 2.0 work runs in ``asyncio.to_thread`` so it doesn't
    block the asyncio loop — the studio's POST /deploy endpoint
    otherwise stalls all other requests for the wipe duration on
    a multi-million-row demo DB.
    """
    sql = wipe_demo_data_sql(instance, dialect=cfg.dialect)
    await _emit(dev_log, {
        "event": "deploy:step2:wipe:start",
        "instance": instance.instance,
        "dialect": cfg.dialect.value,
    })

    def _run_wipe() -> tuple[int, int]:
        conn = connect_demo_db(cfg)
        try:
            cur = conn.cursor()
            try:
                # Count first so the dev_log can report what was wiped.
                p = instance.instance
                cur.execute(f"SELECT COUNT(*) FROM {p}_transactions")
                tx_count = int(cur.fetchone()[0])
                cur.execute(f"SELECT COUNT(*) FROM {p}_daily_balances")
                bal_count = int(cur.fetchone()[0])
                execute_script(cur, sql, dialect=cfg.dialect)
                conn.commit()
                return tx_count, bal_count
            finally:
                cur.close()
        finally:
            conn.close()

    tx_count, bal_count = await asyncio.to_thread(_run_wipe)
    await _emit(dev_log, {
        "event": "deploy:step2:wipe:done",
        "transactions_deleted": tx_count,
        "daily_balances_deleted": bal_count,
    })
    return tx_count, bal_count
