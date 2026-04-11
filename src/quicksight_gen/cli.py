"""CLI entry point for quicksight-gen."""

from __future__ import annotations

import json
from pathlib import Path

import click

from quicksight_gen.analysis import build_analysis
from quicksight_gen.config import load_config
from quicksight_gen.datasets import build_all_datasets
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
def generate(config: str, output_dir: str) -> None:
    """Generate QuickSight JSON definitions."""
    cfg = load_config(config)
    out = Path(output_dir)
    click.echo(f"Config: account={cfg.aws_account_id}, region={cfg.aws_region}")

    # Theme
    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    # Datasets
    datasets = build_all_datasets(cfg)
    for ds in datasets:
        _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())

    # Analysis
    analysis = build_analysis(cfg)
    _write_json(out / "analysis.json", analysis.to_aws_json())

    click.echo(f"\nGenerated {1 + len(datasets) + 1} files in {out}/")
