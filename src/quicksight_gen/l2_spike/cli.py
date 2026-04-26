"""M.0 spike — Click CLI wiring `apply` + `generate` commands.

Runs as ``python -m quicksight_gen.l2_spike <command>``. Each command:

  - loads the L2 YAML once via :mod:`l2_spike.loader`
  - dispatches to the appropriate emitter in :mod:`l2_spike.emit`
  - writes the artifact to disk (and optionally executes against the
    target Postgres / QuickSight account)

The CLI surface here intentionally mirrors the workflow sketched in
``SPEC.md`` so M.0 can validate the command shape works end-to-end.
M.6 (CLI workflow polish) replaces this with the production-shape CLI.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import click

from quicksight_gen.common.config import Config
from quicksight_gen.common.models import _strip_nones

from . import emit
from .loader import load


# -- Top-level group ----------------------------------------------------------


@click.group()
def cli() -> None:
    """L2 spike CLI — drives the M.0 vertical slice."""


# -- Helpers ------------------------------------------------------------------


def _spike_config(prefix: str) -> Config:
    """Build a Config for the spike from environment + the L2 instance prefix.

    Real values come from the environment (AWS account / region /
    datasource ARN); falls back to placeholder values so non-deploy commands
    (like ``apply schema`` writing SQL to disk) work without AWS credentials.
    The ``resource_prefix`` is the L2 instance prefix, propagating into all
    QuickSight resource IDs.
    """
    return Config(
        aws_account_id=os.environ.get("AWS_ACCOUNT_ID", "111122223333"),
        aws_region=os.environ.get("AWS_REGION", "us-west-2"),
        datasource_arn=os.environ.get(
            "QS_DATASOURCE_ARN",
            f"arn:aws:quicksight:us-west-2:111122223333:datasource/{prefix}-ds",
        ),
        theme_preset="default",
        resource_prefix=prefix,
    )


_CONFIG_OPTION = click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to the L2 instance YAML.",
)


# -- apply schema -------------------------------------------------------------


@cli.group()
def apply() -> None:
    """Generate + (optionally) execute deploy artifacts."""


@apply.command("schema")
@_CONFIG_OPTION
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write schema SQL to this path. Defaults to <prefix>_schema.sql in CWD.",
)
def apply_schema(config_path: Path, output: Path | None) -> None:
    """Emit + write the prefixed schema SQL."""
    inst = load(config_path)
    sql = emit.emit_schema_sql(inst)
    out = output or Path(f"{inst.instance}_schema.sql")
    out.write_text(sql)
    click.echo(f"Wrote schema SQL to {out}")
    click.echo("To apply: psql $DATABASE_URL < " + str(out))


@apply.command("data")
@_CONFIG_OPTION
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write seed SQL to this path. Defaults to <prefix>_seed.sql in CWD.",
)
def apply_data(config_path: Path, output: Path | None) -> None:
    """Emit + write the prefixed seed SQL (drift scenario plant)."""
    inst = load(config_path)
    sql = emit.emit_seed_sql(inst)
    out = output or Path(f"{inst.instance}_seed.sql")
    out.write_text(sql)
    click.echo(f"Wrote seed SQL to {out}")
    click.echo("To apply: psql $DATABASE_URL < " + str(out))


@apply.command("dashboards")
@_CONFIG_OPTION
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Write dashboard JSON to this directory. Defaults to ./out/<prefix>/.",
)
def apply_dashboards(config_path: Path, output_dir: Path | None) -> None:
    """Build the dashboard App and write its Analysis + Dashboard JSON."""
    inst = load(config_path)
    cfg = _spike_config(inst.instance)
    app = emit.build_dashboard(inst, cfg)

    out = output_dir or Path("out") / inst.instance
    out.mkdir(parents=True, exist_ok=True)

    analysis = app.emit_analysis()
    dashboard = app.emit_dashboard()

    (out / "analysis.json").write_text(
        json.dumps(_strip_nones(asdict(analysis)), indent=2, default=str)
    )
    (out / "dashboard.json").write_text(
        json.dumps(_strip_nones(asdict(dashboard)), indent=2, default=str)
    )
    click.echo(f"Wrote analysis.json + dashboard.json to {out}/")
    click.echo(
        "Real deploy via boto3 wires in M.0.10 — for now this just emits "
        "the JSON the deployer would consume."
    )


# -- generate training --------------------------------------------------------


@cli.group()
def generate() -> None:
    """Generate render artifacts (training site, handbook, etc.)."""


@generate.command("training")
@_CONFIG_OPTION
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Write handbook page to this directory. Defaults to ./training/<prefix>/.",
)
@click.option(
    "--screenshot-path",
    type=str,
    default="drift-sheet.png",
    help=(
        "Path the handbook page references for the embedded screenshot. "
        "M.0.10 wires the real ScreenshotHarness output here; for now "
        "this defaults to the harness's expected filename."
    ),
)
def generate_training(
    config_path: Path,
    output_dir: Path | None,
    screenshot_path: str,
) -> None:
    """Render the spike's one handbook page against the L2 instance."""
    inst = load(config_path)
    out = output_dir or Path("training") / inst.instance
    out.mkdir(parents=True, exist_ok=True)

    handbook_md = emit.render_handbook(inst, screenshot_path=screenshot_path)
    (out / "drift-handbook.md").write_text(handbook_md)
    click.echo(f"Wrote drift-handbook.md to {out}/")
    click.echo(
        "The handbook references "
        f"'{screenshot_path}' for the embedded screenshot — capture it via "
        "ScreenshotHarness against the deployed dashboard "
        "(wiring lands in M.0.10)."
    )


if __name__ == "__main__":
    cli()
