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
        _generate_account_recon(config, output_dir, theme_preset)
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
    """Generate Account Reconciliation JSON."""
    _generate_account_recon(
        ctx.obj["config"], ctx.obj["output_dir"], ctx.obj["theme_preset"],
    )


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
    _prune_stale_files(
        out / "datasets",
        keep=_all_dataset_filenames(cfg, keep_current=datasets),
    )
    for ds in datasets:
        _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())

    analysis = build_analysis(cfg)
    _write_json(out / "payment-recon-analysis.json", analysis.to_aws_json())

    dashboard = build_payment_recon_dashboard(cfg)
    _write_json(out / "payment-recon-dashboard.json", dashboard.to_aws_json())

    click.echo(f"\nGenerated {1 + len(datasets) + 2} files in {out}/")


def _generate_account_recon(
    config_path: str, output_dir: str, theme_preset: str | None,
) -> None:
    from quicksight_gen.account_recon.analysis import (
        build_account_recon_dashboard,
        build_analysis,
    )
    from quicksight_gen.account_recon.datasets import build_all_datasets

    cfg = load_config(config_path)
    if theme_preset is not None:
        cfg.theme_preset = theme_preset
    out = Path(output_dir)
    click.echo(
        f"Account Recon: account={cfg.aws_account_id}, "
        f"region={cfg.aws_region}"
    )

    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    datasets = build_all_datasets(cfg)
    _prune_stale_files(
        out / "datasets",
        keep=_all_dataset_filenames(cfg, keep_current=datasets),
    )
    for ds in datasets:
        _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())

    analysis = build_analysis(cfg)
    _write_json(out / "account-recon-analysis.json", analysis.to_aws_json())

    dashboard = build_account_recon_dashboard(cfg)
    _write_json(out / "account-recon-dashboard.json", dashboard.to_aws_json())

    click.echo(f"\nGenerated {1 + len(datasets) + 2} files in {out}/")


def _all_dataset_filenames(cfg, *, keep_current: list) -> set[str]:
    """Expected dataset filenames for both apps combined.

    ``keep_current`` is the list of DataSet models the current generate
    pass will write — always included. The other app's filenames are
    included so a single-app generate doesn't prune its sibling's output.
    """
    from quicksight_gen.account_recon.datasets import (
        build_all_datasets as _ar,
    )
    from quicksight_gen.payment_recon.datasets import (
        build_all_datasets as _pr,
    )

    names: set[str] = {f"{ds.DataSetId}.json" for ds in keep_current}
    names.update(f"{ds.DataSetId}.json" for ds in _pr(cfg))
    names.update(f"{ds.DataSetId}.json" for ds in _ar(cfg))
    return names


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
    _resolve_app(app, all_apps, allow_all=True)
    # Schema lives in a single file covering both apps (pr_ + ar_ prefixes).
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
    from quicksight_gen.account_recon.demo_data import (
        generate_demo_sql as generate_ar_sql,
    )
    from quicksight_gen.payment_recon.demo_data import (
        generate_demo_sql as generate_pr_sql,
    )

    if app == "payment-recon":
        sql = generate_pr_sql()
    elif app == "account-recon":
        sql = generate_ar_sql()
    else:  # all
        sql = generate_pr_sql() + "\n" + generate_ar_sql()

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sql)
    click.echo(f"Wrote seed data to {out}")


@demo.command("etl-example")
@click.argument("app", type=APP_CHOICE, required=False)
@click.option("--all", "all_apps", is_flag=True, help="Emit examples for all apps.")
@click.option(
    "--output", "-o",
    type=click.Path(), default="demo/etl-examples.sql",
    help="Output path for the ETL examples SQL file.",
)
def demo_etl_example(app: str | None, all_apps: bool, output: str) -> None:
    """Emit canonical INSERT-pattern examples for ETL authors.

    Output is exemplary, not executable against the real demo seed —
    every pattern uses fixed sentinel IDs (xxx-EXAMPLE-001) so the
    statements are self-contained. See docs/handbook/etl.md for the
    walkthroughs that reference this output.
    """
    app = _resolve_app(app, all_apps, allow_all=True)
    from quicksight_gen.account_recon.etl_examples import (
        generate_etl_examples_sql as generate_ar_examples,
    )
    from quicksight_gen.payment_recon.etl_examples import (
        generate_etl_examples_sql as generate_pr_examples,
    )

    if app == "payment-recon":
        sql = generate_pr_examples()
    elif app == "account-recon":
        sql = generate_ar_examples()
    else:  # all
        sql = generate_pr_examples() + "\n" + generate_ar_examples()

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sql)
    click.echo(f"Wrote ETL examples to {out}")


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
    _apply_demo(config, output_dir, app)


def _apply_demo(config_path: str, output_dir: str, app: str) -> None:
    """Load schema + chosen seed(s) into demo DB, then regenerate JSON.

    ``app`` is one of ``payment-recon``, ``account-recon``, ``all``.
    Schema is always applied in full — both apps share the DB — so the
    only thing that varies is which seed SQL gets loaded and which
    analyses get generated.
    """
    from quicksight_gen.account_recon.analysis import (
        build_account_recon_dashboard,
        build_analysis as build_ar_analysis,
    )
    from quicksight_gen.account_recon.datasets import (
        build_all_datasets as build_ar_datasets,
    )
    from quicksight_gen.account_recon.demo_data import (
        generate_demo_sql as generate_ar_sql,
    )
    from quicksight_gen.payment_recon.analysis import (
        build_analysis as build_pr_analysis,
        build_payment_recon_dashboard,
    )
    from quicksight_gen.payment_recon.datasets import (
        build_all_datasets as build_pr_datasets,
        build_datasource,
    )
    from quicksight_gen.payment_recon.demo_data import (
        generate_demo_sql as generate_pr_sql,
    )

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

    seed_parts: list[str] = []
    if app in ("payment-recon", "all"):
        seed_parts.append(generate_pr_sql())
    if app in ("account-recon", "all"):
        seed_parts.append(generate_ar_sql())
    seed_sql = "\n".join(seed_parts)

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

    preset = (
        "sasquatch-bank-ar" if app == "account-recon" else "sasquatch-bank"
    )
    click.echo(f"\nGenerating QuickSight JSON with {preset} theme...")
    cfg.theme_preset = preset
    out = Path(output_dir)

    datasource = build_datasource(cfg)
    _write_json(out / "datasource.json", datasource.to_aws_json())

    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    json_count = 2  # datasource + theme
    if app in ("payment-recon", "all"):
        pr_datasets = build_pr_datasets(cfg)
        for ds in pr_datasets:
            _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())
        _write_json(
            out / "payment-recon-analysis.json",
            build_pr_analysis(cfg).to_aws_json(),
        )
        _write_json(
            out / "payment-recon-dashboard.json",
            build_payment_recon_dashboard(cfg).to_aws_json(),
        )
        json_count += len(pr_datasets) + 2

    if app in ("account-recon", "all"):
        ar_datasets = build_ar_datasets(cfg)
        for ds in ar_datasets:
            _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())
        _write_json(
            out / "account-recon-analysis.json",
            build_ar_analysis(cfg).to_aws_json(),
        )
        _write_json(
            out / "account-recon-dashboard.json",
            build_account_recon_dashboard(cfg).to_aws_json(),
        )
        json_count += len(ar_datasets) + 2

    click.echo(f"\nDone. {json_count} JSON files in {out}/")


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
            _generate_account_recon(config, output_dir, theme_preset)

    cfg = load_config(config)
    if app_name == "all":
        targets = list(APPS)
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
