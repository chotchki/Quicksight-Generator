"""Shared CLI helpers (load config, resolve L2, emit-vs-apply primitives).

The four artifact groups (`schema` / `data` / `json` / `docs`) reuse a
small set of primitives:

  ``resolve_l2_for_demo``  — load YAML + stamp prefix on cfg
  ``build_full_seed_sql``  — densify + broken + boost + emit_full_seed
  ``emit_to_target``       — write SQL to file or stdout
  ``connect_and_apply``    — open demo DB, execute, commit/rollback
  ``write_json``           — write a generated dataset/analysis/dashboard JSON

Every artifact module imports from here so the apply/emit/clean/test
implementations are thin wrappers around the production library
(``common/l2/``, ``common/datasource.py``, ``common/theme.py``).
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from quicksight_gen.common.config import load_config


__all__ = [
    "APPS",
    "build_full_seed_sql",
    "connect_and_apply",
    "emit_to_target",
    "load_config",
    "prune_stale_files",
    "resolve_l2_for_demo",
    "write_json",
]


APPS = (
    "investigation",
    "executives",
    "l1-dashboard",
    "l2-flow-tracing",
)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    click.echo(f"  wrote {path}")


def prune_stale_files(directory: Path, *, keep: set[str]) -> None:
    """Delete any ``*.json`` in ``directory`` whose name isn't in ``keep``.

    Prevents orphan files from a prior emit — datasets that were dropped
    or renamed — from being re-deployed on the next ``json apply`` run.
    """
    if not directory.is_dir():
        return
    for path in directory.glob("*.json"):
        if path.name not in keep:
            path.unlink()
            click.echo(f"  pruned stale {path}")


def resolve_l2_for_demo(
    config_path: str, l2_instance_path: str | None,
):  # type: ignore[no-untyped-def]
    """Load config + L2 instance and stamp the per-instance prefix on cfg.

    Returns ``(cfg, instance)``. Mirrors the prelude every ``apply``
    operation needs: load YAML, resolve to either the bundled
    spec_example or the integrator's own L2, stamp
    ``cfg.l2_instance_prefix`` so downstream SQL (REFRESH MATERIALIZED
    VIEW, dataset IDs) lands on the right per-prefix objects.
    """
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance

    cfg = load_config(config_path)
    if l2_instance_path is not None:
        from quicksight_gen.common.l2 import load_instance
        instance = load_instance(Path(l2_instance_path))
    else:
        instance = default_l2_instance()
    if cfg.l2_instance_prefix is None:
        cfg = cfg.with_l2_instance_prefix(str(instance.instance))
    return cfg, instance


def build_full_seed_sql(cfg, instance) -> str:  # type: ignore[no-untyped-def]
    """Compose the demo seed pipeline.

    Densify per-kind plants (×5) → add 15 broken-rail stuck_pending
    plants on one rail → boost inv_fanout amounts (×5). Returns the
    concatenated SQL of the 90-day baseline + plant overlays.
    """
    from quicksight_gen.common.l2.auto_scenario import (
        add_broken_rail_plants,
        boost_inv_fanout_plants,
        default_scenario_for,
        densify_scenario,
    )
    from quicksight_gen.common.l2.seed import emit_full_seed

    base = default_scenario_for(instance).scenario
    dense = densify_scenario(base, factor=5)
    broken = add_broken_rail_plants(dense, instance, broken_count=15)
    final = boost_inv_fanout_plants(broken, amount_multiplier=5)
    return emit_full_seed(instance, final, dialect=cfg.dialect)


def emit_to_target(
    sql: str, output: str | None, *, stdout: bool, label: str,
) -> None:
    """Write SQL to ``output`` or stdout; echo a one-line summary on stderr.

    The ``stdout`` flag is the explicit ``--stdout`` from the CLI; when
    True, write to stdout regardless of ``output``. When False and
    ``output is None``, raise — caller must pick one of the two.
    """
    if stdout:
        click.echo(sql, nl=False)
        return
    if output is None:
        raise click.UsageError(
            "Specify either --stdout (write to stdout) or -o FILE."
        )
    Path(output).write_text(sql, encoding="utf-8")
    line_count = sql.count("\n")
    size_kb = len(sql.encode("utf-8")) // 1024
    click.echo(
        f"Wrote {label} to {output} ({line_count} lines, {size_kb} KB)",
        err=True,
    )


def connect_and_apply(
    cfg, sql: str, *, label: str,  # type: ignore[no-untyped-def]
) -> None:
    """Open the demo DB connection, run ``sql``, commit; rollback on error."""
    from quicksight_gen.common.db import connect_demo_db, execute_script

    if not cfg.demo_database_url:
        raise click.ClickException(
            "demo_database_url is required. "
            "Set it in your config YAML or via QS_GEN_DEMO_DATABASE_URL."
        )

    click.echo(f"Connecting to {cfg.demo_database_url.split('@')[-1]}...")
    try:
        conn = connect_demo_db(cfg)
    except ImportError as e:
        raise click.ClickException(str(e)) from e
    try:
        with conn.cursor() as cur:
            click.echo(f"  Applying {label}...")
            execute_script(cur, sql, dialect=cfg.dialect)
        conn.commit()
        click.echo(f"  {label.capitalize()} applied.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Common click options shared across artifact subcommands.

def l2_instance_option():  # type: ignore[no-untyped-def]
    """``--l2 PATH`` — defaults to bundled spec_example."""
    return click.option(
        "--l2", "l2_instance_path",
        type=click.Path(exists=True, dir_okay=False), default=None,
        help="Path to L2 instance YAML. Default: bundled spec_example.",
    )


def config_option(*, required_for_dialect_only: bool = False):  # type: ignore[no-untyped-def]
    """``--config / -c PATH`` — config.yaml.

    Pass ``required_for_dialect_only=True`` for emit-only commands that
    only need the dialect setting (no DB connection).
    """
    help_text = (
        "Path to configuration file (used for the dialect setting only)."
        if required_for_dialect_only
        else "Path to configuration file (DB connection + dialect)."
    )
    return click.option(
        "--config", "-c",
        type=click.Path(exists=True), default="config.yaml",
        help=help_text,
    )


def output_options(*, default_dir: str | None = None):  # type: ignore[no-untyped-def]
    """``-o FILE`` + ``--stdout`` — emit-vs-apply redirect.

    When ``default_dir`` is set (e.g. ``"out"`` for json apply), ``-o``
    defaults to that dir and the apply lands files there as a side
    effect; ``--stdout`` is then meaningless and not exposed.
    """
    def decorator(fn):  # type: ignore[no-untyped-def]
        if default_dir is None:
            fn = click.option(
                "--stdout", is_flag=True, default=False,
                help="Write the script to stdout instead of executing.",
            )(fn)
            fn = click.option(
                "-o", "--output", "output",
                type=click.Path(), default=None,
                help="Write the script to FILE instead of executing.",
            )(fn)
        else:
            fn = click.option(
                "-o", "--output", "output",
                type=click.Path(), default=default_dir,
                help=f"Output directory (default: {default_dir}/).",
            )(fn)
        return fn
    return decorator
