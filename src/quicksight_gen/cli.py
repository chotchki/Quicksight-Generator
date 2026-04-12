"""CLI entry point for quicksight-gen."""

from __future__ import annotations

import json
from pathlib import Path

import click

from quicksight_gen.common.config import load_config
from quicksight_gen.common.theme import build_theme


APPS = ("payment-recon", "account-recon")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    click.echo(f"  wrote {path}")


def _prune_stale_files(directory: Path, *, keep: set[str]) -> None:
    """Delete any *.json in ``directory`` whose filename is not in ``keep``.

    Prevents orphan files from a prior generate — datasets that were dropped
    or renamed — from being re-deployed on the next ``deploy`` run.
    """
    if not directory.is_dir():
        return
    for path in directory.glob("*.json"):
        if path.name not in keep:
            path.unlink()
            click.echo(f"  pruned stale {path}")


@click.group()
def main() -> None:
    """Generate and deploy AWS QuickSight dashboards."""


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

@main.group(invoke_without_command=True)
@click.option(
    "--config", "-c",
    type=click.Path(exists=True), default="config.yaml",
    help="Path to configuration file.",
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(), default="out",
    help="Directory to write generated JSON files.",
)
@click.option(
    "--theme-preset", "-t", type=str, default=None,
    help="Theme preset name (overrides config).",
)
@click.option("--all", "all_apps", is_flag=True, help="Generate every app.")
@click.pass_context
def generate(
    ctx: click.Context, config: str, output_dir: str,
    theme_preset: str | None, all_apps: bool,
) -> None:
    """Generate QuickSight JSON definitions."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["output_dir"] = output_dir
    ctx.obj["theme_preset"] = theme_preset
    if ctx.invoked_subcommand is not None:
        return
    if all_apps:
        _generate_payment_recon(config, output_dir, theme_preset)
        _generate_account_recon_stub()
    else:
        click.echo(ctx.get_help())
        raise click.UsageError("Specify an app (payment-recon, account-recon) or --all.")


@generate.command("payment-recon")
@click.pass_context
def generate_payment_recon_cmd(ctx: click.Context) -> None:
    """Generate Payment Reconciliation JSON."""
    _generate_payment_recon(
        ctx.obj["config"], ctx.obj["output_dir"], ctx.obj["theme_preset"],
    )


@generate.command("account-recon")
@click.pass_context
def generate_account_recon_cmd(ctx: click.Context) -> None:
    """Generate Account Reconciliation JSON (stubbed)."""
    _generate_account_recon_stub()


def _generate_payment_recon(
    config_path: str, output_dir: str, theme_preset: str | None,
) -> None:
    from quicksight_gen.payment_recon.analysis import (
        build_analysis,
        build_payment_recon_dashboard,
    )
    from quicksight_gen.payment_recon.datasets import build_all_datasets

    cfg = load_config(config_path)
    if theme_preset is not None:
        cfg.theme_preset = theme_preset
    out = Path(output_dir)
    click.echo(
        f"Payment Recon: account={cfg.aws_account_id}, "
        f"region={cfg.aws_region}"
    )

    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    datasets = build_all_datasets(cfg)
    expected_dataset_files = {f"{ds.DataSetId}.json" for ds in datasets}
    _prune_stale_files(out / "datasets", keep=expected_dataset_files)
    for ds in datasets:
        _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())

    analysis = build_analysis(cfg)
    _write_json(out / "payment-recon-analysis.json", analysis.to_aws_json())

    dashboard = build_payment_recon_dashboard(cfg)
    _write_json(out / "payment-recon-dashboard.json", dashboard.to_aws_json())

    click.echo(f"\nGenerated {1 + len(datasets) + 2} files in {out}/")


def _generate_account_recon_stub() -> None:
    raise NotImplementedError(
        "Account Recon generation is not yet implemented (Phase 3)."
    )


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

APP_CHOICE = click.Choice(["payment-recon", "account-recon"])


@main.group()
def demo() -> None:
    """Manage demo database schema and sample data."""


@demo.command("schema")
@click.argument("app", type=APP_CHOICE, required=False)
@click.option("--all", "all_apps", is_flag=True, help="Emit schema for all apps.")
@click.option(
    "--output", "-o",
    type=click.Path(), default="demo/schema.sql",
    help="Output path for the schema SQL file.",
)
def demo_schema(app: str | None, all_apps: bool, output: str) -> None:
    """Emit the PostgreSQL DDL for the demo database."""
    app = _resolve_app(app, all_apps, allow_all=True)
    if app in ("account-recon",):
        raise NotImplementedError(
            "Account Recon schema is not yet implemented (Phase 3)."
        )
    schema_path = _project_root() / "demo" / "schema.sql"
    if not schema_path.exists():
        raise click.ClickException(f"Schema file not found at {schema_path}")
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema_path.read_text())
    click.echo(f"Wrote schema to {out}")


@demo.command("seed")
@click.argument("app", type=APP_CHOICE, required=False)
@click.option("--all", "all_apps", is_flag=True, help="Emit seeds for all apps.")
@click.option(
    "--output", "-o",
    type=click.Path(), default="demo/seed.sql",
    help="Output path for the seed data SQL file.",
)
def demo_seed(app: str | None, all_apps: bool, output: str) -> None:
    """Emit INSERT statements with demo data."""
    app = _resolve_app(app, all_apps, allow_all=True)
    if app == "account-recon":
        raise NotImplementedError(
            "Account Recon seed is not yet implemented (Phase 3)."
        )
    from quicksight_gen.payment_recon.demo_data import generate_demo_sql

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_demo_sql())
    click.echo(f"Wrote seed data to {out}")


@demo.command("apply")
@click.argument("app", type=APP_CHOICE, required=False)
@click.option("--all", "all_apps", is_flag=True, help="Apply for all apps.")
@click.option(
    "--config", "-c",
    type=click.Path(exists=True), default="config.yaml",
    help="Path to configuration file.",
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(), default="out",
    help="Directory to write generated QuickSight JSON files.",
)
def demo_apply(app: str | None, all_apps: bool, config: str, output_dir: str) -> None:
    """Apply schema + seed data to the demo DB and generate QuickSight JSON."""
    app = _resolve_app(app, all_apps, allow_all=True)
    if app == "account-recon":
        raise NotImplementedError(
            "Account Recon apply is not yet implemented (Phase 3)."
        )
    _apply_payment_recon(config, output_dir)


def _apply_payment_recon(config_path: str, output_dir: str) -> None:
    from quicksight_gen.payment_recon.analysis import (
        build_analysis,
        build_payment_recon_dashboard,
    )
    from quicksight_gen.payment_recon.datasets import (
        build_all_datasets,
        build_datasource,
    )
    from quicksight_gen.payment_recon.demo_data import generate_demo_sql

    cfg = load_config(config_path)
    if not cfg.demo_database_url:
        raise click.ClickException(
            "demo_database_url is required for 'demo apply'. "
            "Set it in your config YAML or via QS_GEN_DEMO_DATABASE_URL."
        )

    try:
        import psycopg2  # type: ignore[import-untyped]
    except ImportError:
        raise click.ClickException(
            "psycopg2 is required for 'demo apply'. "
            "Install it with: pip install 'quicksight-gen[demo]'"
        )

    schema_path = _project_root() / "demo" / "schema.sql"
    if not schema_path.exists():
        raise click.ClickException(f"Schema file not found at {schema_path}")
    schema_sql = schema_path.read_text()
    seed_sql = generate_demo_sql()

    click.echo(f"Connecting to {cfg.demo_database_url.split('@')[-1]}...")
    conn = psycopg2.connect(cfg.demo_database_url)
    try:
        with conn.cursor() as cur:
            click.echo("  Applying schema...")
            cur.execute(schema_sql)
            click.echo("  Inserting seed data...")
            cur.execute(seed_sql)
        conn.commit()
        click.echo("  Database ready.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    click.echo("\nGenerating QuickSight JSON with sasquatch-bank theme...")
    cfg.theme_preset = "sasquatch-bank"
    out = Path(output_dir)

    datasource = build_datasource(cfg)
    _write_json(out / "datasource.json", datasource.to_aws_json())

    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    datasets = build_all_datasets(cfg)
    for ds in datasets:
        _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())

    analysis = build_analysis(cfg)
    _write_json(out / "payment-recon-analysis.json", analysis.to_aws_json())

    dashboard = build_payment_recon_dashboard(cfg)
    _write_json(out / "payment-recon-dashboard.json", dashboard.to_aws_json())

    click.echo(f"\nDone. {2 + len(datasets) + 2} JSON files in {out}/")


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

@main.command("deploy")
@click.argument("app", type=APP_CHOICE, required=False)
@click.option("--all", "all_apps", is_flag=True, help="Deploy every app.")
@click.option(
    "--config", "-c",
    type=click.Path(exists=True), default="config.yaml",
    help="Path to configuration file.",
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(), default="out",
    help="Directory to read generated JSON from.",
)
@click.option(
    "--generate", "generate_first", is_flag=True,
    help="Regenerate JSON before deploying.",
)
@click.option(
    "--theme-preset", "-t", type=str, default=None,
    help="Theme preset (used when --generate is set).",
)
def deploy_cmd(
    app: str | None, all_apps: bool, config: str, output_dir: str,
    generate_first: bool, theme_preset: str | None,
) -> None:
    """Deploy generated JSON to AWS QuickSight (delete-then-create)."""
    from quicksight_gen.common.deploy import deploy

    app_name = _resolve_app(app, all_apps, allow_all=True)

    if generate_first:
        if app_name in ("payment-recon", "all"):
            _generate_payment_recon(config, output_dir, theme_preset)
        if app_name in ("account-recon", "all"):
            if app_name == "all":
                click.echo("Account Recon: not yet implemented (skipped)")
            else:
                _generate_account_recon_stub()

    cfg = load_config(config)
    if app_name == "all":
        targets = list(APPS)
    elif app_name == "account-recon":
        raise NotImplementedError(
            "Account Recon deploy is not yet implemented (Phase 3)."
        )
    else:
        targets = [app_name]

    exit_code = deploy(cfg, Path(output_dir), targets)
    if exit_code != 0:
        raise click.ClickException(f"Deploy failed (exit code {exit_code}).")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

@main.command("cleanup")
@click.option(
    "--config", "-c",
    type=click.Path(exists=True), default="config.yaml",
    help="Path to configuration file.",
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(), default="out",
    help="Directory holding current generate output (used to know what's not stale).",
)
@click.option("--dry-run", is_flag=True, help="Only list stale resources.")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def cleanup_cmd(config: str, output_dir: str, dry_run: bool, yes: bool) -> None:
    """Delete tagged QuickSight resources that are not in current output."""
    from quicksight_gen.common.cleanup import run_cleanup

    cfg = load_config(config)
    exit_code = run_cleanup(
        cfg, Path(output_dir), dry_run=dry_run, skip_confirm=yes,
    )
    if exit_code != 0:
        raise click.ClickException(f"Cleanup failed (exit code {exit_code}).")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_app(app: str | None, all_apps: bool, *, allow_all: bool) -> str:
    if all_apps and app is not None:
        raise click.UsageError("Pass either an app argument OR --all, not both.")
    if all_apps:
        if not allow_all:
            raise click.UsageError("--all is not supported for this command.")
        return "all"
    if app is None:
        raise click.UsageError("Specify an app (payment-recon, account-recon) or --all.")
    return app


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent
