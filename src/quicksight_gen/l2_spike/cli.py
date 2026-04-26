"""M.0 spike — Click CLI wiring.

Two config inputs per command (mirrors the existing CLI's split):

  ``-c / --config``    AWS / Postgres config YAML (loaded via the existing
                        ``common.config.load_config`` — same shape as
                        ``run/config.yaml``).
  ``-i / --instance``  L2 instance YAML (the spike's ``slice.yaml``).

By default each ``apply`` subcommand writes artifacts to disk AND executes
them against the target system (Postgres for schema/data, QuickSight for
dashboards). ``--dry-run`` short-circuits the execution leg so the spike
can be inspected without AWS credentials. The L2 instance's
``InstancePrefix`` overrides ``cfg.resource_prefix`` so every generated
DB object + QuickSight resource ID is namespaced to the spike instance
even when the AWS YAML's default prefix differs (``run/config.yaml``
typically pins ``qs-gen``).

This CLI is throwaway spike code; M.6 (CLI workflow polish) replaces it.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import click

from quicksight_gen.common.config import Config, load_config
from quicksight_gen.common.models import _strip_nones

from . import emit
from .loader import L2Instance, load


# -- Top-level group ----------------------------------------------------------


@click.group()
def cli() -> None:
    """L2 spike CLI — drives the M.0 vertical slice."""


# -- Reusable Click options ---------------------------------------------------


_INSTANCE_OPTION = click.option(
    "--instance",
    "-i",
    "instance_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to the L2 instance YAML (e.g. tests/spike/slice.yaml).",
)

_CONFIG_OPTION = click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help=(
        "Path to the AWS/Postgres config YAML "
        "(e.g. run/config.yaml). Loaded via common.config.load_config."
    ),
)

_DRY_RUN_OPTION = click.option(
    "--dry-run/--execute",
    default=False,
    help=(
        "If --dry-run, only writes artifacts to disk. "
        "If --execute (default), also runs against the target system "
        "(Postgres for schema/data, QuickSight for dashboards)."
    ),
)


# -- Helpers ------------------------------------------------------------------


def _load_pair(instance_path: Path, config_path: Path) -> tuple[L2Instance, Config]:
    """Load both the L2 instance and the AWS config, splice the prefix."""
    inst = load(instance_path)
    cfg = load_config(str(config_path))
    # The L2 instance's InstancePrefix is authoritative over cfg.resource_prefix
    # for the spike's deploy: dashboard resource IDs get the spike prefix even
    # when run/config.yaml is configured for the production "qs-gen".
    cfg.resource_prefix = inst.instance
    return inst, cfg


# -- apply --------------------------------------------------------------------


@cli.group()
def apply() -> None:
    """Generate + (by default) execute deploy artifacts."""


@apply.command("schema")
@_INSTANCE_OPTION
@_CONFIG_OPTION
@_DRY_RUN_OPTION
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Where to write the SQL. Defaults to <prefix>_schema.sql in CWD.",
)
def apply_schema(
    instance_path: Path,
    config_path: Path,
    dry_run: bool,
    output: Path | None,
) -> None:
    """Emit the prefixed schema DDL and (by default) execute against Postgres."""
    inst, cfg = _load_pair(instance_path, config_path)
    sql = emit.emit_schema_sql(inst)

    out = output or Path(f"{inst.instance}_schema.sql")
    out.write_text(sql)
    click.echo(f"Wrote schema SQL to {out}")

    if dry_run:
        click.echo("--dry-run: skipping Postgres execution.")
        return

    _execute_sql(cfg, sql, label="schema DDL")


@apply.command("data")
@_INSTANCE_OPTION
@_CONFIG_OPTION
@_DRY_RUN_OPTION
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Where to write the SQL. Defaults to <prefix>_seed.sql in CWD.",
)
def apply_data(
    instance_path: Path,
    config_path: Path,
    dry_run: bool,
    output: Path | None,
) -> None:
    """Emit the prefixed seed SQL and (by default) execute against Postgres."""
    inst, cfg = _load_pair(instance_path, config_path)
    sql = emit.emit_seed_sql(inst)

    out = output or Path(f"{inst.instance}_seed.sql")
    out.write_text(sql)
    click.echo(f"Wrote seed SQL to {out}")

    if dry_run:
        click.echo("--dry-run: skipping Postgres execution.")
        return

    _execute_sql(cfg, sql, label="seed data")


@apply.command("dashboards")
@_INSTANCE_OPTION
@_CONFIG_OPTION
@_DRY_RUN_OPTION
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Where to write JSON. Defaults to ./out/<prefix>/.",
)
def apply_dashboards(
    instance_path: Path,
    config_path: Path,
    dry_run: bool,
    output_dir: Path | None,
) -> None:
    """Build the dashboard bundle (datasource + theme + dataset + analysis + dashboard JSON) and (by default) deploy via boto3."""
    inst, cfg = _load_pair(instance_path, config_path)

    out = output_dir or Path("out") / inst.instance
    out.mkdir(parents=True, exist_ok=True)
    (out / "datasets").mkdir(parents=True, exist_ok=True)

    # Build the App + write all the JSON files in the convention the existing
    # deploy() expects (`<app>-analysis.json` + `<app>-dashboard.json` + theme
    # + datasource + datasets/<dataset_id>.json).
    app = emit.build_dashboard(inst, cfg)
    analysis = app.emit_analysis()
    dashboard = app.emit_dashboard()
    _write_json(out / "spike-drift-analysis.json", _strip_nones(asdict(analysis)))
    _write_json(out / "spike-drift-dashboard.json", _strip_nones(asdict(dashboard)))

    # Theme + datasource — reuse existing builders so the deploy machinery
    # has every JSON file it expects under the same naming scheme.
    from quicksight_gen.apps.payment_recon.datasets import build_datasource
    from quicksight_gen.common.theme import build_theme

    if cfg.demo_database_url:
        datasource = build_datasource(cfg)
        _write_json(out / "datasource.json", datasource.to_aws_json())

    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    # The dataset itself was registered inside build_dashboard; re-emit its
    # JSON for the deployer to pick up.
    _write_dataset_json(out, inst, cfg)

    click.echo(f"Wrote dashboard bundle to {out}/")

    if dry_run:
        click.echo("--dry-run: skipping QuickSight deploy.")
        return

    from quicksight_gen.common.deploy import deploy

    deploy(cfg, out, ["spike-drift"])


# -- generate -----------------------------------------------------------------


@cli.group()
def generate() -> None:
    """Generate render artifacts (training site, handbook, etc.)."""


@generate.command("training")
@_INSTANCE_OPTION
@_CONFIG_OPTION
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Where to write the handbook + screenshots. Defaults to ./training/<prefix>/.",
)
@click.option(
    "--screenshot-path",
    type=str,
    default="drift-sheet.png",
    help=(
        "Path the handbook page references for the embedded screenshot. "
        "ScreenshotHarness wiring is a follow-up substep — for now this "
        "defaults to the harness's expected filename so the markdown link "
        "resolves once a real PNG lands in the same directory."
    ),
)
def generate_training(
    instance_path: Path,
    config_path: Path,
    output_dir: Path | None,
    screenshot_path: str,
) -> None:
    """Render the handbook page against the L2 instance vocabulary."""
    inst, _cfg = _load_pair(instance_path, config_path)
    out = output_dir or Path("training") / inst.instance
    out.mkdir(parents=True, exist_ok=True)

    handbook_md = emit.render_handbook(inst, screenshot_path=screenshot_path)
    (out / "drift-handbook.md").write_text(handbook_md)
    click.echo(f"Wrote drift-handbook.md to {out}/")
    click.echo(
        f"Handbook references '{screenshot_path}' — drop the captured PNG "
        f"there or wire ScreenshotHarness via a follow-up substep."
    )


# -- Internal helpers ---------------------------------------------------------


def _execute_sql(cfg: Config, sql: str, *, label: str) -> None:
    """Execute SQL against ``cfg.demo_database_url`` via psycopg2."""
    if not cfg.demo_database_url:
        raise click.ClickException(
            "demo_database_url is required to execute SQL. Either set it in "
            "the AWS config YAML or use --dry-run to skip execution."
        )
    try:
        import psycopg2  # type: ignore[import-untyped]
    except ImportError as exc:
        raise click.ClickException(
            "psycopg2 is required to execute SQL. Install it with "
            "`pip install 'quicksight-gen[demo]'`."
        ) from exc

    where = cfg.demo_database_url.split("@")[-1]
    click.echo(f"Connecting to {where} and applying {label}...")
    conn = psycopg2.connect(cfg.demo_database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        click.echo(f"  {label} applied successfully.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str))


def _write_dataset_json(out_dir: Path, inst: L2Instance, cfg: Config) -> None:
    """Re-build the drift dataset and write its JSON for the deployer."""
    from quicksight_gen.common.dataset_contract import build_dataset

    drift_ds = build_dataset(
        cfg,
        cfg.prefixed("drift-dataset"),
        "Drift Detail",
        "drift-view",
        emit._drift_sql(inst.instance),
        emit._DRIFT_CONTRACT,
        visual_identifier="drift-view",
    )
    _write_json(
        out_dir / "datasets" / f"{drift_ds.DataSetId}.json",
        drift_ds.to_aws_json(),
    )


if __name__ == "__main__":
    cli()
