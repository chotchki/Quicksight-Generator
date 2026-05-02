"""``quicksight-gen data`` — per-prefix demo seed data.

Four operations:

  apply    — emit the seed SQL (default), or ``--execute`` against the demo DB.
  refresh  — emit the REFRESH MATERIALIZED VIEW SQL, or ``--execute``.
  clean    — emit TRUNCATE statements, or ``--execute`` to wipe the rows.
  test     — pytest the seed pipeline (hash-lock check).

Same emit-vs-execute pattern as the schema group — default is
print the script, ``--execute`` actually runs it.
"""

from __future__ import annotations

import subprocess
import sys

import click

from quicksight_gen.cli._helpers import (
    build_full_seed_sql,
    config_option,
    connect_and_apply,
    emit_to_target,
    execute_option,
    l2_instance_option,
    output_option,
    resolve_l2_for_demo,
)


@click.group()
def data() -> None:
    """Per-prefix seed data: 90-day baseline + plant overlays."""


@data.command("apply")
@l2_instance_option()
@config_option(required_for_dialect_only=True)
@output_option()
@execute_option()
def data_apply(
    l2_instance_path: str | None, config: str,
    output: str | None, execute: bool,
) -> None:
    """Emit the demo seed SQL (or ``--execute`` to insert against the demo DB).

    The composition: 90-day baseline → densify per-kind plants ×5 →
    add 15 broken-rail stuck_pending plants → boost inv_fanout amounts
    ×5 → emit_full_seed.

    Default: print every INSERT to stdout (or to ``-o FILE``). Pass
    ``--execute`` to connect + insert.

    Assumes the schema is already applied (``schema apply --execute``
    or a prior schema). After ``data apply --execute`` you'll likely
    want ``data refresh --execute`` so the matviews see the new rows.
    """
    cfg, instance = resolve_l2_for_demo(config, l2_instance_path)
    sql = build_full_seed_sql(cfg, instance)

    if execute:
        connect_and_apply(cfg, sql, label="seed data")
    else:
        emit_to_target(sql, output, label="seed SQL")


@data.command("refresh")
@l2_instance_option()
@config_option(required_for_dialect_only=True)
@output_option()
@execute_option()
def data_refresh(
    l2_instance_path: str | None, config: str,
    output: str | None, execute: bool,
) -> None:
    """Emit the REFRESH MATERIALIZED VIEW SQL (or ``--execute`` to refresh).

    Default: print every ``REFRESH MATERIALIZED VIEW`` (in dependency
    order: leaves → helpers → invariants → rollups) to stdout (or to
    ``-o FILE``). Pass ``--execute`` to run against the demo DB.

    Run after every ETL load that mutates ``<prefix>_transactions``
    or ``<prefix>_daily_balances`` — the L1 invariant matviews +
    Investigation matviews don't auto-refresh.
    """
    from quicksight_gen.common.l2.schema import refresh_matviews_sql

    cfg, instance = resolve_l2_for_demo(config, l2_instance_path)
    sql = refresh_matviews_sql(instance, dialect=cfg.dialect)

    if execute:
        connect_and_apply(cfg, sql, label="matview refresh")
    else:
        emit_to_target(sql, output, label="refresh SQL")


@data.command("clean")
@l2_instance_option()
@config_option(required_for_dialect_only=True)
@output_option()
@execute_option()
def data_clean(
    l2_instance_path: str | None, config: str,
    output: str | None, execute: bool,
) -> None:
    """Emit TRUNCATE statements (or ``--execute`` to wipe seeded rows).

    Default: print TRUNCATEs for ``<prefix>_transactions`` and
    ``<prefix>_daily_balances`` to stdout (or to ``-o FILE``). The
    schema stays — only the rows go.

    Pass ``--execute`` to actually run them.

    To wipe schema + rows together, run ``data clean --execute``
    followed by ``schema clean --execute``.
    """
    from quicksight_gen.common.l2.seed import emit_truncate_sql

    cfg, instance = resolve_l2_for_demo(config, l2_instance_path)
    sql = emit_truncate_sql(instance, dialect=cfg.dialect)

    if execute:
        connect_and_apply(cfg, sql, label="data TRUNCATE")
    else:
        emit_to_target(sql, output, label="data TRUNCATE")


@data.command("test")
@click.option(
    "--pytest-args", default="",
    help="Extra args passed verbatim to pytest (e.g. '-k hash_lock').",
)
def data_test(pytest_args: str) -> None:
    """Run the data test suite (pytest + pyright on the seed pipeline)."""
    pytest_argv = (
        [sys.executable, "-m", "pytest", "tests/data/", "-q"]
        + (pytest_args.split() if pytest_args else [])
    )
    pyright_argv = [
        sys.executable, "-m", "pyright",
        "src/quicksight_gen/common/l2/seed.py",
    ]
    failed = []
    click.echo(f"$ {' '.join(pytest_argv)}")
    if subprocess.call(pytest_argv) != 0:
        failed.append("pytest")
    click.echo(f"$ {' '.join(pyright_argv)}")
    if subprocess.call(pyright_argv) != 0:
        failed.append("pyright")
    if failed:
        raise click.ClickException(f"data test failed: {', '.join(failed)}")
    click.echo("data test: OK")
