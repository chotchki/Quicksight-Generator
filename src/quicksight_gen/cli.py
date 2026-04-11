"""CLI entry point for quicksight-gen."""

from __future__ import annotations

import json
from pathlib import Path

import click

from quicksight_gen.analysis import build_analysis, build_financial_dashboard
from quicksight_gen.config import load_config
from quicksight_gen.datasets import build_all_datasets, build_datasource
from quicksight_gen.recon_analysis import build_recon_analysis, build_recon_dashboard
from quicksight_gen.theme import build_theme


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    click.echo(f"  wrote {path}")


@click.group()
def main() -> None:
    """Generate AWS QuickSight analysis JSON for financial reporting."""


@main.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default="config.yaml",
    help="Path to configuration file.",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(),
    default="out",
    help="Directory to write generated JSON files.",
)
@click.option(
    "--theme-preset",
    "-t",
    type=str,
    default=None,
    help="Theme preset name (overrides config). e.g. default, sasquatch-bank",
)
def generate(config: str, output_dir: str, theme_preset: str | None) -> None:
    """Generate QuickSight JSON definitions."""
    cfg = load_config(config)
    if theme_preset is not None:
        cfg.theme_preset = theme_preset
    out = Path(output_dir)
    click.echo(f"Config: account={cfg.aws_account_id}, region={cfg.aws_region}")

    # Theme
    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    # Datasets (financial + reconciliation)
    datasets = build_all_datasets(cfg)
    for ds in datasets:
        _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())

    # Financial analysis
    financial = build_analysis(cfg)
    _write_json(out / "financial-analysis.json", financial.to_aws_json())

    # Reconciliation analysis
    recon = build_recon_analysis(cfg)
    _write_json(out / "recon-analysis.json", recon.to_aws_json())

    # Dashboards (public, link-shareable)
    fin_dash = build_financial_dashboard(cfg)
    _write_json(out / "financial-dashboard.json", fin_dash.to_aws_json())

    recon_dash = build_recon_dashboard(cfg)
    _write_json(out / "recon-dashboard.json", recon_dash.to_aws_json())

    click.echo(f"\nGenerated {1 + len(datasets) + 4} files in {out}/")


# ---------------------------------------------------------------------------
# Demo command group
# ---------------------------------------------------------------------------

@main.group()
def demo() -> None:
    """Manage demo database schema and sample data."""


@demo.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="demo/schema.sql",
    help="Output path for the schema SQL file.",
)
def schema(output: str) -> None:
    """Emit the PostgreSQL DDL for the demo database."""
    schema_path = Path(__file__).resolve().parent.parent.parent / "demo" / "schema.sql"
    if not schema_path.exists():
        raise click.ClickException(
            f"Schema file not found at {schema_path}. "
            "Ensure demo/schema.sql exists in the project root."
        )
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema_path.read_text())
    click.echo(f"Wrote schema to {out}")


@demo.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="demo/seed.sql",
    help="Output path for the seed data SQL file.",
)
def seed(output: str) -> None:
    """Emit INSERT statements with sasquatch coffee shop sample data."""
    from quicksight_gen.demo_data import generate_demo_sql

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_demo_sql())
    click.echo(f"Wrote seed data to {out}")


@demo.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default="config.yaml",
    help="Path to configuration file.",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(),
    default="out",
    help="Directory to write generated QuickSight JSON files.",
)
def apply(config: str, output_dir: str) -> None:
    """Apply schema + seed data to a database and generate QuickSight JSON.

    Requires demo_database_url in config or QS_GEN_DEMO_DATABASE_URL env var.
    Connects via psycopg2 and runs both schema and seed SQL in a transaction.
    Also generates QuickSight JSON with the sasquatch-bank theme preset.
    """
    cfg = load_config(config)
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

    from quicksight_gen.demo_data import generate_demo_sql

    # Read schema SQL
    schema_path = Path(__file__).resolve().parent.parent.parent / "demo" / "schema.sql"
    if not schema_path.exists():
        raise click.ClickException(f"Schema file not found at {schema_path}")
    schema_sql = schema_path.read_text()
    seed_sql = generate_demo_sql()

    # Apply to database
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

    # Generate QuickSight JSON with sasquatch-bank theme
    click.echo("\nGenerating QuickSight JSON with sasquatch-bank theme...")
    cfg.theme_preset = "sasquatch-bank"
    out = Path(output_dir)

    # Data source (uses demo_database_url credentials)
    datasource = build_datasource(cfg)
    _write_json(out / "datasource.json", datasource.to_aws_json())

    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    datasets = build_all_datasets(cfg)
    for ds in datasets:
        _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())

    financial = build_analysis(cfg)
    _write_json(out / "financial-analysis.json", financial.to_aws_json())

    recon = build_recon_analysis(cfg)
    _write_json(out / "recon-analysis.json", recon.to_aws_json())

    # Dashboards (public, link-shareable)
    fin_dash = build_financial_dashboard(cfg)
    _write_json(out / "financial-dashboard.json", fin_dash.to_aws_json())

    recon_dash = build_recon_dashboard(cfg)
    _write_json(out / "recon-dashboard.json", recon_dash.to_aws_json())

    click.echo(f"\nDone. {2 + len(datasets) + 4} JSON files in {out}/")
