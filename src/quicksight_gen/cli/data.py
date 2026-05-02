"""``quicksight-gen data`` — per-prefix demo seed data.

Five operations:

  apply    — emit the seed SQL (default), or ``--execute`` against the demo DB.
  refresh  — emit the REFRESH MATERIALIZED VIEW SQL, or ``--execute``.
  clean    — emit TRUNCATE statements, or ``--execute`` to wipe the rows.
  hash     — re-lock or verify the YAML's ``seed_hash:`` against the
             auto-seed (canonical-date, plant-only).
  test     — pytest the seed pipeline (hash-lock check).

Same emit-vs-execute pattern as the schema group — default is
print the script, ``--execute`` actually runs it.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

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


@data.command("hash")
@click.argument(
    "yaml_path",
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--output", "-o",
    type=click.Path(), default=None,
    help="Output path for the canonical-date plant SQL (default: stdout).",
)
@click.option(
    "--lock", is_flag=True,
    help=(
        "Write the canonical-seed SHA256 back into the YAML's "
        "``seed_hash.postgres`` field (creating the field if absent). "
        "Use this after a reviewed change to the L2 spec drifts the "
        "canonical seed output."
    ),
)
@click.option(
    "--check", "check_hash", is_flag=True,
    help=(
        "Exit 1 if the YAML's ``seed_hash.postgres`` doesn't match the "
        "actual SHA256 of the auto-generated canonical-date seed. Use "
        "in CI to guard against unreviewed L2 spec drift."
    ),
)
def data_hash(
    yaml_path: str,
    output: str | None,
    lock: bool,
    check_hash: bool,
) -> None:
    """Lock or verify the YAML's ``seed_hash`` against the canonical seed.

    Walks the L2 instance and plants one of every L1 exception kind
    (drift, overdraft, limit-breach, stuck-pending, stuck-unbundled,
    supersession) using deterministic heuristics. Plants that can't be
    derived from the YAML (e.g., no LimitSchedule declared) are
    omitted with a one-line warning.

    Hash semantics: hashed against a fixed canonical reference date
    (2030-01-01) so the SHA256 is stable across days. ``--lock``
    writes the current hash into the YAML; ``--check`` verifies the
    YAML's declared hash matches.

    The hash covers the plant-only output (``emit_seed``); the
    full-seed pipeline behind ``data apply`` rolls today's date
    into the baseline, which is intentional but unhashable.
    """
    from quicksight_gen.common.l2 import load_instance
    from quicksight_gen.common.l2.auto_scenario import default_scenario_for
    from quicksight_gen.common.l2.seed import emit_seed

    p = Path(yaml_path)
    instance = load_instance(p)

    # Hash against the canonical reference date so the SHA256 lives
    # independently of the day the CLI runs.
    canonical_today = date(2030, 1, 1)
    report = default_scenario_for(instance, today=canonical_today)
    sql = emit_seed(instance, report.scenario)
    actual_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()

    for kind, reason in report.omitted:
        click.echo(f"  [warn] omitted {kind}: {reason}", err=True)

    if check_hash:
        # P.5.b — seed_hash is per-dialect dict on L2Instance. The CLI's
        # emit_seed call uses the default Postgres dialect; check
        # against the ``postgres`` entry only.
        declared = instance.seed_hash
        if declared is None:
            click.echo(
                "  [error] --check requested but YAML has no "
                "`seed_hash:` field; run with --lock first.",
                err=True,
            )
            raise SystemExit(1)
        expected = declared.get("postgres")
        if expected is None:
            click.echo(
                "  [error] --check requested but YAML's `seed_hash:` "
                "dict is missing the `postgres` key; run with --lock to "
                "populate.",
                err=True,
            )
            raise SystemExit(1)
        if expected != actual_hash:
            click.echo(
                f"  [error] seed_hash mismatch (postgres):\n"
                f"    YAML  : {expected}\n"
                f"    actual: {actual_hash}\n"
                f"  Re-run with --lock if the change was intentional.",
                err=True,
            )
            raise SystemExit(1)
        click.echo(
            f"  [ok] seed_hash matches (postgres={actual_hash})", err=True,
        )

    if lock:
        _rewrite_seed_hash_in_yaml(p, actual_hash)
        click.echo(
            f"  [lock] wrote seed_hash.postgres={actual_hash} into {p}",
            err=True,
        )

    if output is None:
        click.echo(sql)
    else:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(sql)
        click.echo(f"Wrote canonical-date plant SQL to {out}", err=True)


def _rewrite_seed_hash_in_yaml(yaml_path: Path, new_hash: str) -> None:
    """Idempotently set ``seed_hash.postgres: <new_hash>`` on a YAML file.

    P.5.b — seed_hash is a per-dialect dict in YAML. ``--lock`` only
    writes the Postgres hash (the CLI's emit_seed defaults to PG); the
    Oracle hash is locked separately (in tests/l2/*.yaml manually until
    a future ``--dialect oracle`` flag lands).

    Preserves comments + ordering by treating the file as text — never
    parses + re-emits via PyYAML (that would lose every comment and
    re-order keys). Replaces the entire ``seed_hash:`` block (top-level
    key + any indented children) with the new dict shape, or appends
    one if the field is absent.
    """
    text = yaml_path.read_text()
    lines = text.splitlines(keepends=True)
    new_block = (
        f"seed_hash:\n  postgres: {new_hash}\n"
    )
    seen_at = -1
    for i, line in enumerate(lines):
        if re.match(r"^seed_hash\s*:", line):
            seen_at = i
            break
    if seen_at >= 0:
        end_at = len(lines)
        existing_oracle: str | None = None
        for j in range(seen_at + 1, len(lines)):
            stripped = lines[j].lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            if not lines[j][:1].isspace():
                end_at = j
                break
            m = re.match(r"\s+oracle\s*:\s*(\w+)", lines[j])
            if m:
                existing_oracle = m.group(1)
        if existing_oracle is not None:
            new_block = (
                f"seed_hash:\n"
                f"  postgres: {new_hash}\n"
                f"  oracle: {existing_oracle}\n"
            )
        lines = lines[:seen_at] + [new_block] + lines[end_at:]
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        lines.append(new_block)
    yaml_path.write_text("".join(lines))


@data.command("etl-example")
@click.option(
    "-o", "--output",
    type=click.Path(), default="demo/etl-examples.sql",
    show_default=True,
    help="Output path for the ETL examples SQL file.",
)
def data_etl_example(output: str) -> None:
    """Emit canonical INSERT-pattern examples for ETL authors.

    Output is exemplary, not executable against the real demo seed —
    every pattern uses fixed sentinel IDs (xxx-EXAMPLE-001) so the
    statements are self-contained. Each block carries a ``-- WHY:``
    header naming the business invariant and a ``-- Consumed by:``
    header naming the dashboard view that reads the resulting rows.

    See docs/handbook/etl.md for the walkthroughs that reference this
    output.
    """
    from quicksight_gen.apps.investigation.etl_examples import (
        generate_etl_examples_sql,
    )

    sql = generate_etl_examples_sql()
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sql)
    click.echo(f"Wrote ETL examples to {out}")


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
