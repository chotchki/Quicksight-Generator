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
    "--no-screenshot",
    is_flag=True,
    default=False,
    help=(
        "Skip ScreenshotHarness invocation; render handbook with a "
        "placeholder image reference. Useful when the dashboard isn't "
        "deployed yet or when running without Playwright/AWS credentials."
    ),
)
def generate_training(
    instance_path: Path,
    config_path: Path,
    output_dir: Path | None,
    no_screenshot: bool,
) -> None:
    """Render the handbook page (with embedded screenshot) against the L2 instance."""
    inst, cfg = _load_pair(instance_path, config_path)
    out = output_dir or Path("training") / inst.instance
    out.mkdir(parents=True, exist_ok=True)

    if no_screenshot:
        screenshot_filename = "drift-sheet.png"
        click.echo(
            "--no-screenshot: skipping ScreenshotHarness; handbook will "
            f"reference '{screenshot_filename}' as a placeholder."
        )
    else:
        screenshot_filename = _capture_screenshot(cfg, inst, out)
        click.echo(f"Captured screenshot at {out / screenshot_filename}")

    handbook_md = emit.render_handbook(inst, screenshot_path=screenshot_filename)
    (out / "drift-handbook.md").write_text(handbook_md)
    click.echo(f"Wrote drift-handbook.md to {out}/")


def _capture_screenshot(cfg: Config, inst: L2Instance, output_dir: Path) -> str:
    """Generate embed URL → launch Playwright → screenshot the deployed Drift sheet.

    Returns the screenshot filename (relative to output_dir) so the
    handbook's `![](...)` reference resolves alongside the rendered page.
    The dashboard must already be deployed (run `apply dashboards` first).

    Note: ``ScreenshotHarness.capture_all_sheets()`` was built for multi-
    sheet dashboards and waits on `[role="tab"]` (the sheet tab strip)
    which QuickSight doesn't render for single-sheet dashboards. The spike
    has one sheet, so we do a direct capture inline rather than going
    through the harness's tab-aware machinery — see F12 in findings.
    """
    import boto3

    # tests/e2e helpers — see F7 for the promote-out-of-tests follow-up.
    from tests.e2e.browser_helpers import (
        generate_dashboard_embed_url,
        webkit_page,
    )

    if not cfg.principal_arns:
        raise click.ClickException(
            "principal_arns is required in the AWS config to generate an "
            "embed URL. Add at least one user ARN to run/config.yaml or "
            "use --no-screenshot."
        )

    dashboard_id = cfg.prefixed("spike-drift-dashboard")
    # QS_SPIKE_EMBED_USER_ARN can override which principal_arn we embed for —
    # `quicksight-test-user` is typically the right default rather than the
    # root-linked first ARN, which can have account-binding quirks that
    # surface as "We can't open that dashboard" in headless contexts.
    user_arn = os.environ.get(
        "QS_SPIKE_EMBED_USER_ARN",
        cfg.principal_arns[-1],  # Last entry; usually the dedicated test user.
    )

    click.echo(f"Generating embed URL for dashboard {dashboard_id}...")
    qs_identity_client = boto3.client("quicksight", region_name="us-east-1")
    embed_url = generate_dashboard_embed_url(
        qs_identity_client,
        account_id=cfg.aws_account_id,
        dashboard_id=dashboard_id,
        user_arn=user_arn,
    )

    click.echo("Launching Playwright + capturing the Drift sheet...")
    timeout_ms = int(os.environ.get("QS_E2E_PAGE_TIMEOUT", "60000"))
    settle_seconds = int(os.environ.get("QS_SPIKE_SETTLE_SECONDS", "12"))
    screenshot_filename = "drift-sheet.png"
    screenshot_path = output_dir / screenshot_filename

    # Single-sheet dashboards don't render the tab strip and the
    # visual-rendered selector is fragile; for the spike we use a
    # plain networkidle + fixed-seconds settle. Brute-force but
    # reliable. M.1+ wires a proper wait that handles one-sheet vs
    # multi-sheet uniformly.
    with webkit_page(headless=True) as page:
        page.goto(embed_url)
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        page.wait_for_timeout(settle_seconds * 1000)
        page.screenshot(path=str(screenshot_path), full_page=True)

    return screenshot_filename


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
