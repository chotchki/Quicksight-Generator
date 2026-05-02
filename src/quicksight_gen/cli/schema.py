"""``quicksight-gen schema`` — per-prefix DDL for an L2 instance.

Three operations:

  apply  — emit-or-execute the schema DDL.
  clean  — emit-or-execute the matching DROP statements.
  test   — pytest + pyright the schema-emitting library code.

Default ``apply`` / ``clean`` connect to the demo DB and execute.
Pass ``-o FILE`` or ``--stdout`` to redirect to the SQL script
without touching the DB (the integrator can pipe to their own
DB tool).
"""

from __future__ import annotations

import subprocess
import sys

import click

from quicksight_gen.cli._helpers import (
    config_option,
    connect_and_apply,
    emit_to_target,
    l2_instance_option,
    output_options,
    resolve_l2_for_demo,
)


@click.group()
def schema() -> None:
    """Per-prefix schema DDL: tables, views, materialized views."""


@schema.command("apply")
@l2_instance_option()
@config_option()
@output_options()
def schema_apply(
    l2_instance_path: str | None, config: str,
    output: str | None, stdout: bool,
) -> None:
    """Apply the schema DDL to the demo DB (or emit it with -o / --stdout).

    Default: connect to the DB named in the config and run every
    CREATE statement for the L2 instance's per-prefix tables, views,
    and materialized views.

    With ``-o FILE`` or ``--stdout``: write the SQL only — no DB
    connection. Pipe to ``psql`` / ``sqlplus`` / etc. for hand
    insertion.
    """
    from quicksight_gen.common.l2.schema import emit_schema

    cfg, instance = resolve_l2_for_demo(config, l2_instance_path)
    sql = emit_schema(instance, dialect=cfg.dialect)

    if output is not None or stdout:
        emit_to_target(sql, output, stdout=stdout, label="schema DDL")
        return

    connect_and_apply(cfg, sql, label="schema DDL")


@schema.command("clean")
@l2_instance_option()
@config_option()
@output_options()
def schema_clean(
    l2_instance_path: str | None, config: str,
    output: str | None, stdout: bool,
) -> None:
    """Drop every per-prefix schema object for the L2 instance.

    Default: connect to the DB and DROP every matview / view / table
    the L2 emits, in dependency order.

    With ``-o FILE`` or ``--stdout``: write the DROP script only.

    Schema-only cleanup. To also wipe seeded rows, run ``data clean``
    first.
    """
    from quicksight_gen.common.l2.schema import emit_schema_drop_sql

    cfg, instance = resolve_l2_for_demo(config, l2_instance_path)
    sql = emit_schema_drop_sql(instance, dialect=cfg.dialect)

    if output is not None or stdout:
        emit_to_target(sql, output, stdout=stdout, label="schema DROP")
        return

    connect_and_apply(cfg, sql, label="schema DROP")


@schema.command("test")
@click.option(
    "--pytest-args", default="",
    help="Extra args passed verbatim to pytest (e.g. '-k drift -v').",
)
def schema_test(pytest_args: str) -> None:
    """Run the schema test suite (pytest + pyright)."""
    pytest_argv = (
        [sys.executable, "-m", "pytest", "tests/schema/", "-q"]
        + (pytest_args.split() if pytest_args else [])
    )
    pyright_argv = [
        sys.executable, "-m", "pyright",
        "src/quicksight_gen/common/l2/schema.py",
    ]
    failed = []
    click.echo(f"$ {' '.join(pytest_argv)}")
    if subprocess.call(pytest_argv) != 0:
        failed.append("pytest")
    click.echo(f"$ {' '.join(pyright_argv)}")
    if subprocess.call(pyright_argv) != 0:
        failed.append("pyright")
    if failed:
        raise click.ClickException(f"schema test failed: {', '.join(failed)}")
    click.echo("schema test: OK")
