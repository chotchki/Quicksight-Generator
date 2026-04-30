"""CLI entry point for quicksight-gen."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import click

from quicksight_gen import __version__
from quicksight_gen.common.config import load_config
from quicksight_gen.common.theme import build_theme


APPS = (
    "investigation",
    "executives", "l1-dashboard", "l2-flow-tracing",
)


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
@click.version_option(version=__version__, prog_name="quicksight-gen")
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
        _generate_investigation(config, output_dir, theme_preset)
        _generate_executives(config, output_dir, theme_preset)
        _generate_l1_dashboard(config, output_dir, theme_preset)
        _generate_l2_flow_tracing(config, output_dir, theme_preset)
    else:
        click.echo(ctx.get_help())
        raise click.UsageError(
            "Specify an app (investigation, "
            "executives, l1-dashboard, l2-flow-tracing) "
            "or --all."
        )


@generate.command("executives")
@click.pass_context
def generate_executives_cmd(ctx: click.Context) -> None:
    """Generate Executives JSON."""
    _generate_executives(
        ctx.obj["config"], ctx.obj["output_dir"], ctx.obj["theme_preset"],
    )


@generate.command("investigation")
@click.pass_context
def generate_investigation_cmd(ctx: click.Context) -> None:
    """Generate Investigation JSON."""
    _generate_investigation(
        ctx.obj["config"], ctx.obj["output_dir"], ctx.obj["theme_preset"],
    )


@generate.command("l1-dashboard")
@click.option(
    "--l2-instance", "l2_instance_path",
    type=click.Path(exists=True), default=None,
    help=(
        "Path to an L2 instance YAML. Defaults to the persona-neutral "
        "spec_example.yaml fixture. Use this to deploy l1-dashboard "
        "against multiple L2 instances side-by-side without code edits."
    ),
)
@click.pass_context
def generate_l1_dashboard_cmd(
    ctx: click.Context, l2_instance_path: str | None,
) -> None:
    """Generate L1 Reconciliation Dashboard JSON (M.2a — L2-fed)."""
    _generate_l1_dashboard(
        ctx.obj["config"], ctx.obj["output_dir"], ctx.obj["theme_preset"],
        l2_instance_path=l2_instance_path,
    )


@generate.command("l2-flow-tracing")
@click.option(
    "--l2-instance", "l2_instance_path",
    type=click.Path(exists=True), default=None,
    help=(
        "Path to an L2 instance YAML. Defaults to the persona-neutral "
        "spec_example.yaml fixture. Use this to deploy l2-flow-tracing "
        "against multiple L2 instances side-by-side without code edits "
        "(M.3.9 surface)."
    ),
)
@click.pass_context
def generate_l2_flow_tracing_cmd(
    ctx: click.Context, l2_instance_path: str | None,
) -> None:
    """Generate L2 Flow Tracing dashboard JSON (M.3 — L2-fed)."""
    _generate_l2_flow_tracing(
        ctx.obj["config"], ctx.obj["output_dir"], ctx.obj["theme_preset"],
        l2_instance_path=l2_instance_path,
    )


def _generate_investigation(
    config_path: str, output_dir: str, theme_preset: str | None,
    *,
    l2_instance_path: str | None = None,
) -> None:
    from dataclasses import replace as _replace

    from quicksight_gen.apps.investigation.app import (
        build_investigation_app,
    )
    from quicksight_gen.apps.investigation.datasets import build_all_datasets
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
    from quicksight_gen.common.l2 import load_instance

    cfg = load_config(config_path)
    if theme_preset is not None:
        cfg.theme_preset = theme_preset
    out = Path(output_dir)

    # N.3.h — Investigation reads the same institution YAML the L1
    # dashboard does (per the N.2 audit). Load the L2 instance up
    # front and pre-stamp ``cfg.l2_instance_prefix`` so both
    # ``build_all_datasets`` and ``build_investigation_app`` see the
    # prefix without needing to thread the instance through every
    # builder.
    if l2_instance_path is not None:
        l2_instance = load_instance(Path(l2_instance_path))
    else:
        l2_instance = default_l2_instance()
    if cfg.l2_instance_prefix is None:
        cfg = _replace(cfg, l2_instance_prefix=str(l2_instance.instance))

    click.echo(
        f"Investigation: account={cfg.aws_account_id}, "
        f"region={cfg.aws_region}, l2_instance={l2_instance.instance}"
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

    # Build the app once + emit both Analysis + Dashboard so the L2
    # instance is consistent across both (mirrors L1 + L2FT).
    app = build_investigation_app(cfg, l2_instance=l2_instance)
    _write_json(
        out / "investigation-analysis.json",
        app.emit_analysis().to_aws_json(),
    )
    _write_json(
        out / "investigation-dashboard.json",
        app.emit_dashboard().to_aws_json(),
    )

    click.echo(f"\nGenerated {1 + len(datasets) + 2} files in {out}/")


def _generate_executives(
    config_path: str, output_dir: str, theme_preset: str | None,
) -> None:
    from quicksight_gen.apps.executives.app import (
        build_analysis,
        build_executives_dashboard,
    )
    from quicksight_gen.apps.executives.datasets import build_all_datasets

    cfg = load_config(config_path)
    if theme_preset is not None:
        cfg.theme_preset = theme_preset
    out = Path(output_dir)
    click.echo(
        f"Executives: account={cfg.aws_account_id}, region={cfg.aws_region}"
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
    _write_json(out / "executives-analysis.json", analysis.to_aws_json())

    dashboard = build_executives_dashboard(cfg)
    _write_json(out / "executives-dashboard.json", dashboard.to_aws_json())

    click.echo(f"\nGenerated {1 + len(datasets) + 2} files in {out}/")


def _generate_l1_dashboard(
    config_path: str, output_dir: str, theme_preset: str | None,
    *,
    l2_instance_path: str | None = None,
) -> None:
    from quicksight_gen.apps.l1_dashboard.app import (
        build_l1_dashboard_app,
    )
    from quicksight_gen.apps.l1_dashboard.datasets import (
        build_all_l1_dashboard_datasets,
    )
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
    from quicksight_gen.common.l2 import load_instance

    cfg = load_config(config_path)
    if theme_preset is not None:
        cfg.theme_preset = theme_preset
    out = Path(output_dir)

    if l2_instance_path is not None:
        l2_instance = load_instance(Path(l2_instance_path))
    else:
        l2_instance = default_l2_instance()

    click.echo(
        f"L1 Dashboard: account={cfg.aws_account_id}, "
        f"region={cfg.aws_region}, l2_instance={l2_instance.instance}"
    )

    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    datasets = build_all_l1_dashboard_datasets(cfg, l2_instance)
    _prune_stale_files(
        out / "datasets",
        keep=_all_dataset_filenames(cfg, keep_current=datasets),
    )
    for ds in datasets:
        _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())

    # Build the app once + emit both Analysis + Dashboard so the L2
    # instance is consistent across both. Same pattern as
    # _generate_l2_flow_tracing — avoids the redundant rebuild a shim
    # wrapper would trigger.
    app = build_l1_dashboard_app(cfg, l2_instance=l2_instance)
    _write_json(
        out / "l1-dashboard-analysis.json",
        app.emit_analysis().to_aws_json(),
    )
    _write_json(
        out / "l1-dashboard-dashboard.json",
        app.emit_dashboard().to_aws_json(),
    )

    click.echo(f"\nGenerated {1 + len(datasets) + 2} files in {out}/")


def _generate_l2_flow_tracing(
    config_path: str, output_dir: str, theme_preset: str | None,
    *,
    l2_instance_path: str | None = None,
) -> None:
    """Generate L2 Flow Tracing JSON.

    ``l2_instance_path``: optional YAML path. When unset, loads the
    persona-neutral spec_example fixture (the M.3.2 default). Use the
    flag to deploy l2-flow-tracing against any L2 instance — sasquatch_pr
    for the rich Sasquatch view, fuzz-seed-N for adversarial coverage,
    or an integrator-supplied YAML.
    """
    from quicksight_gen.apps.l2_flow_tracing.app import (
        build_l2_flow_tracing_app,
    )
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_all_l2_flow_tracing_datasets,
    )
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
    from quicksight_gen.common.l2 import load_instance

    cfg = load_config(config_path)
    if theme_preset is not None:
        cfg.theme_preset = theme_preset
    out = Path(output_dir)

    if l2_instance_path is not None:
        l2_instance = load_instance(Path(l2_instance_path))
    else:
        l2_instance = default_l2_instance()

    click.echo(
        f"L2 Flow Tracing: account={cfg.aws_account_id}, "
        f"region={cfg.aws_region}, l2_instance={l2_instance.instance}"
    )

    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    datasets = build_all_l2_flow_tracing_datasets(cfg, l2_instance)
    _prune_stale_files(
        out / "datasets",
        keep=_all_dataset_filenames(cfg, keep_current=datasets),
    )
    for ds in datasets:
        _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())

    # Build the app once + emit both Analysis + Dashboard from it so the
    # L2 instance is consistent across both. The shim wrappers
    # (build_analysis / build_l2_flow_tracing_dashboard) would each
    # re-invoke build_l2_flow_tracing_app — using the app directly
    # avoids the redundant build.
    app = build_l2_flow_tracing_app(cfg, l2_instance=l2_instance)
    _write_json(
        out / "l2-flow-tracing-analysis.json",
        app.emit_analysis().to_aws_json(),
    )
    _write_json(
        out / "l2-flow-tracing-dashboard.json",
        app.emit_dashboard().to_aws_json(),
    )

    click.echo(f"\nGenerated {1 + len(datasets) + 2} files in {out}/")


def _all_dataset_filenames(cfg, *, keep_current: list) -> set[str]:
    """Expected dataset filenames for both apps combined.

    ``keep_current`` is the list of DataSet models the current generate
    pass will write — always included. The other app's filenames are
    included so a single-app generate doesn't prune its sibling's output.
    """
    from dataclasses import replace as _replace

    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
    from quicksight_gen.apps.executives.datasets import (
        build_all_datasets as _exec,
    )
    from quicksight_gen.apps.investigation.datasets import (
        build_all_datasets as _inv,
    )
    from quicksight_gen.apps.l1_dashboard.datasets import (
        build_all_l1_dashboard_datasets as _l1,
    )
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_all_l2_flow_tracing_datasets as _l2ft,
    )

    # N.3.h: Investigation now requires ``cfg.l2_instance_prefix`` to
    # render its dataset SQL. When this helper is called from a sibling
    # app's generate flow (e.g. Executives), the cfg may not have the
    # prefix set. Pre-stamp from the default L2 instance to keep the
    # enumeration working without churning the caller. Once N.4
    # migrates Executives to L2-fed too, every app caller will already
    # set the prefix and this can simplify.
    default_l2 = default_l2_instance()
    cfg_with_prefix = (
        cfg if cfg.l2_instance_prefix is not None
        else _replace(cfg, l2_instance_prefix=str(default_l2.instance))
    )

    names: set[str] = {f"{ds.DataSetId}.json" for ds in keep_current}
    names.update(f"{ds.DataSetId}.json" for ds in _inv(cfg_with_prefix))
    names.update(f"{ds.DataSetId}.json" for ds in _exec(cfg_with_prefix))
    names.update(
        f"{ds.DataSetId}.json"
        for ds in _l1(cfg_with_prefix, default_l2)
    )
    names.update(
        f"{ds.DataSetId}.json"
        for ds in _l2ft(cfg_with_prefix, default_l2)
    )
    return names


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

APP_CHOICE = click.Choice([
    "investigation",
    "executives", "l1-dashboard", "l2-flow-tracing",
])

# Demo subcommands (schema / seed / etl-example / apply) target the v5
# demo-data pipeline only. `l1-dashboard` and `l2-flow-tracing` are the
# L2-fed apps — their data comes from the L2 prefixed schema + M.2.2's
# L2 seed via the L2 pipeline (e.g. `m2_6_verify.sh`), NOT from the v5
# demo_data.py generators here. Keeping them out of DEMO_APP_CHOICE
# means `demo seed l1-dashboard` / `demo seed l2-flow-tracing` fails
# with a Click validation error pointing the user at the right surface.
DEMO_APP_CHOICE = click.Choice([
    "investigation", "executives",
])


@main.group()
def demo() -> None:
    """Manage demo database schema and sample data."""


@demo.command("schema")
@click.argument("app", type=DEMO_APP_CHOICE, required=False)
@click.option("--all", "all_apps", is_flag=True, help="Emit schema for all apps.")
@click.option(
    "--output", "-o",
    type=click.Path(), default="demo/schema.sql",
    help="Output path for the schema SQL file.",
)
def demo_schema(app: str | None, all_apps: bool, output: str) -> None:
    """Emit the PostgreSQL DDL for the demo database."""
    _resolve_app(app, all_apps, allow_all=True)
    # Schema covers both apps — they share the `transactions` +
    # `daily_balances` base tables and AR-only dimension tables.
    from quicksight_gen.schema import generate_schema_sql

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_schema_sql())
    click.echo(f"Wrote schema to {out}")


@demo.command("seed")
@click.argument("app", type=DEMO_APP_CHOICE, required=False)
@click.option("--all", "all_apps", is_flag=True, help="Emit seeds for all apps.")
@click.option(
    "--output", "-o",
    type=click.Path(), default="demo/seed.sql",
    help="Output path for the seed data SQL file.",
)
def demo_seed(app: str | None, all_apps: bool, output: str) -> None:
    """Emit INSERT statements with demo data."""
    app = _resolve_app(app, all_apps, allow_all=True)
    from quicksight_gen.apps.investigation.demo_data import (
        generate_demo_sql as generate_inv_sql,
    )

    if app == "investigation":
        sql = generate_inv_sql()
    else:  # all
        sql = generate_inv_sql()

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sql)
    click.echo(f"Wrote seed data to {out}")


@demo.command("etl-example")
@click.argument("app", type=DEMO_APP_CHOICE, required=False)
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
    from quicksight_gen.apps.investigation.etl_examples import (
        generate_etl_examples_sql as generate_inv_examples,
    )

    if app == "investigation":
        sql = generate_inv_examples()
    else:  # all
        sql = generate_inv_examples()

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sql)
    click.echo(f"Wrote ETL examples to {out}")


@demo.command("seed-l2")
@click.argument(
    "yaml_path",
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--output", "-o",
    type=click.Path(), default=None,
    help="Output path for the SQL (default: stdout).",
)
@click.option(
    "--lock", is_flag=True,
    help=(
        "After emitting the SQL, write its SHA256 back into the YAML's "
        "`seed_hash:` field (creating the field if absent). Use this "
        "after a reviewed change to the L2 spec drifts the seed output."
    ),
)
@click.option(
    "--check-hash", is_flag=True,
    help=(
        "Exit 1 if the YAML's `seed_hash:` field doesn't match the "
        "actual SHA256 of the auto-generated seed. Use in CI to guard "
        "against unreviewed L2 spec drift. Only meaningful in the "
        "default --mode l1_invariants — broad / l1_plus_broad modes "
        "have their hashes locked in tests/test_l2_seed_contract.py."
    ),
)
@click.option(
    "--mode",
    type=click.Choice(["l1_invariants", "broad", "l1_plus_broad"]),
    default="l1_invariants",
    help=(
        "Which scenario plants to emit. `l1_invariants` (default) "
        "plants one of every L1 SHOULD-violation kind. `broad` "
        "plants per-rail firings for every Rail with materialized "
        "accounts (M.4.2 — for visual review of the L2 surface). "
        "`l1_plus_broad` is the union (used by the M.4.1 end-to-end "
        "harness)."
    ),
)
def demo_seed_l2(
    yaml_path: str,
    output: str | None,
    lock: bool,
    check_hash: bool,
    mode: str,
) -> None:
    """Auto-generate a deterministic L1-exception seed from an L2 YAML.

    Walks the L2 instance and plants one of every L1 exception kind
    (drift, overdraft, limit-breach, stuck-pending, stuck-unbundled,
    supersession) using deterministic heuristics — no hand-authored
    scenario required. Plants that can't be derived from the YAML
    (e.g., no LimitSchedule declared) are omitted with a one-line
    warning.

    Hash semantics: the auto-seed is hashed against a fixed canonical
    reference date (2030-01-01) so the SHA256 is stable across days.
    `--lock` writes the current hash into the YAML; `--check-hash`
    verifies the YAML's declared hash matches.
    """
    from datetime import date
    import hashlib
    from quicksight_gen.common.l2 import load_instance
    from quicksight_gen.common.l2.auto_scenario import (
        ScenarioMode,
        default_scenario_for,
    )
    from quicksight_gen.common.l2.seed import emit_seed
    from typing import cast

    p = Path(yaml_path)
    instance = load_instance(p)

    # The hash is computed against the canonical reference date so the
    # SHA256 lives independently of the day the CLI runs.
    canonical_today = date(2030, 1, 1)
    report = default_scenario_for(
        instance, today=canonical_today, mode=cast(ScenarioMode, mode),
    )
    sql = emit_seed(instance, report.scenario)
    actual_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()

    for kind, reason in report.omitted:
        click.echo(f"  [warn] omitted {kind}: {reason}", err=True)

    if check_hash:
        declared = instance.seed_hash
        if declared is None:
            click.echo(
                "  [error] --check-hash requested but YAML has no "
                "`seed_hash:` field; run with --lock first.",
                err=True,
            )
            raise SystemExit(1)
        if declared != actual_hash:
            click.echo(
                f"  [error] seed_hash mismatch:\n"
                f"    YAML  : {declared}\n"
                f"    actual: {actual_hash}\n"
                f"  Re-run with --lock if the change was intentional.",
                err=True,
            )
            raise SystemExit(1)
        click.echo(f"  [ok] seed_hash matches ({actual_hash})", err=True)

    if lock:
        _rewrite_seed_hash_in_yaml(p, actual_hash)
        click.echo(f"  [lock] wrote seed_hash={actual_hash} into {p}", err=True)

    if output is None:
        click.echo(sql)
    else:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(sql)
        click.echo(f"Wrote auto-seed to {out}", err=True)


def _rewrite_seed_hash_in_yaml(yaml_path: Path, new_hash: str) -> None:
    """Idempotently set ``seed_hash: <new_hash>`` on a YAML file.

    Preserves comments + ordering by treating the file as text — never
    parses + re-emits via PyYAML (that would lose every comment and
    re-order keys). Either replaces an existing top-level
    ``seed_hash:`` line, or appends one to the file.
    """
    text = yaml_path.read_text()
    lines = text.splitlines(keepends=True)
    new_line = f"seed_hash: {new_hash}\n"
    seen = False
    for i, line in enumerate(lines):
        # Match top-level seed_hash (no leading whitespace) followed by
        # a colon. A more permissive regex would catch indented uses
        # too but we don't want to mutate nested fields named the same.
        if re.match(r"^seed_hash\s*:", line):
            lines[i] = new_line
            seen = True
            break
    if not seen:
        # Append, ensuring the file ends with a newline first.
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        lines.append(new_line)
    yaml_path.write_text("".join(lines))


@demo.command("topology")
@click.option(
    "--l2-instance", "l2_instance_path",
    type=click.Path(exists=True, dir_okay=False), required=True,
    help="Path to the L2 instance YAML to render.",
)
@click.option(
    "--output", "-o",
    type=click.Path(), required=True,
    help="Output path for the SVG file (parent directories created).",
)
@click.option(
    "--engine", type=click.Choice(
        ["dot", "neato", "sfdp", "fdp", "twopi", "circo"],
    ),
    default="dot", show_default=True,
    help=(
        "Graphviz layout engine. 'dot' is hierarchical (good for chain "
        "DAGs); the rest are force-directed (better when the topology has "
        "many bidirectional edges between counterparties)."
    ),
)
def demo_topology(
    l2_instance_path: str, output: str, engine: str,
) -> None:
    """Render an L2 instance topology diagram to SVG.

    Walks the L2 YAML and emits a Graphviz SVG showing roles,
    rails (bundled when parallel), single-leg self-loops, transfer
    templates as clusters of their leg rails, and chain edges between
    parent and child rails / templates.

    Requires the system `dot` binary (Homebrew: 'brew install
    graphviz'; Debian/Ubuntu: 'apt install graphviz') and the Python
    `graphviz` package (already a runtime dependency).
    """
    from quicksight_gen.common.l2 import load_instance
    from quicksight_gen.common.l2.topology import render_topology

    instance = load_instance(Path(l2_instance_path))
    try:
        rendered = render_topology(
            instance, Path(output), engine=engine,
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wrote topology SVG to {rendered}")


@demo.command("apply")
@click.argument("app", type=DEMO_APP_CHOICE, required=False)
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

    ``app`` is one of ``investigation``, ``executives``, or ``all``.
    Schema is always applied in full — apps share the DB — so the only
    thing that varies is which seed SQL gets loaded and which analyses
    get generated.
    """
    from dataclasses import replace as _replace

    from quicksight_gen.apps.executives.app import (
        build_analysis as build_exec_analysis,
        build_executives_dashboard,
    )
    from quicksight_gen.apps.executives.datasets import (
        build_all_datasets as build_exec_datasets,
    )
    from quicksight_gen.apps.investigation.app import (
        build_analysis as build_inv_analysis,
        build_investigation_dashboard,
    )
    from quicksight_gen.apps.investigation.datasets import (
        build_all_datasets as build_inv_datasets,
    )
    from quicksight_gen.apps.investigation.demo_data import (
        generate_demo_sql as generate_inv_sql,
    )
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance

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

    from quicksight_gen.schema import generate_schema_sql
    schema_sql = generate_schema_sql()

    seed_parts: list[str] = []
    if app in ("investigation", "all"):
        seed_parts.append(generate_inv_sql())
    seed_sql = "\n".join(seed_parts)

    click.echo(f"Connecting to {cfg.demo_database_url.split('@')[-1]}...")
    conn = psycopg2.connect(cfg.demo_database_url)
    try:
        with conn.cursor() as cur:
            click.echo("  Applying schema...")
            cur.execute(schema_sql)
            click.echo("  Inserting seed data...")
            cur.execute(seed_sql)
            click.echo("  Refreshing materialized views...")
            cur.execute("REFRESH MATERIALIZED VIEW ar_unified_exceptions;")
            cur.execute("REFRESH MATERIALIZED VIEW inv_pair_rolling_anomalies;")
            cur.execute("REFRESH MATERIALIZED VIEW inv_money_trail_edges;")
        conn.commit()
        click.echo("  Database ready.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # N.1.g: PRESETS now contains only the ``default`` preset; per-app
    # branded palettes moved to inline ``theme:`` blocks on the L2
    # YAMLs. L1 + L2FT pick up the L2-sourced theme via
    # ``resolve_l2_theme(l2_instance)``; Exec stays on the registry
    # default until N.4 migrates it to L2-fed.
    preset = "default"
    click.echo(f"\nGenerating QuickSight JSON with {preset} theme...")
    cfg.theme_preset = preset

    # N.3.h: pre-stamp ``cfg.l2_instance_prefix`` from the default L2
    # instance so Investigation's prefix-aware dataset builders can
    # render their SQL. Same shape as ``_generate_investigation``.
    # NOTE (N.3.i): seed SQL above still plants flat-table data; the
    # prefix-aware seed lift lands in N.3.i. This keeps demo apply
    # generating the QuickSight JSON correctly mid-flight.
    inv_l2 = default_l2_instance()
    if cfg.l2_instance_prefix is None:
        cfg = _replace(cfg, l2_instance_prefix=str(inv_l2.instance))

    out = Path(output_dir)

    datasource = build_datasource(cfg)
    _write_json(out / "datasource.json", datasource.to_aws_json())

    theme = build_theme(cfg)
    _write_json(out / "theme.json", theme.to_aws_json())

    json_count = 2  # datasource + theme
    if app in ("investigation", "all"):
        inv_datasets = build_inv_datasets(cfg)
        for ds in inv_datasets:
            _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())
        _write_json(
            out / "investigation-analysis.json",
            build_inv_analysis(cfg, l2_instance=inv_l2).to_aws_json(),
        )
        _write_json(
            out / "investigation-dashboard.json",
            build_investigation_dashboard(
                cfg, l2_instance=inv_l2,
            ).to_aws_json(),
        )
        json_count += len(inv_datasets) + 2

    if app in ("executives", "all"):
        # Executives has no demo seed of its own — reads what PR/AR/Inv
        # plant. Just emit the JSON.
        exec_datasets = build_exec_datasets(cfg)
        for ds in exec_datasets:
            _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())
        _write_json(
            out / "executives-analysis.json",
            build_exec_analysis(cfg).to_aws_json(),
        )
        _write_json(
            out / "executives-dashboard.json",
            build_executives_dashboard(cfg).to_aws_json(),
        )
        json_count += len(exec_datasets) + 2

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
        if app_name in ("investigation", "all"):
            _generate_investigation(config, output_dir, theme_preset)
        if app_name in ("executives", "all"):
            _generate_executives(config, output_dir, theme_preset)
        if app_name in ("l1-dashboard", "all"):
            _generate_l1_dashboard(config, output_dir, theme_preset)
        if app_name in ("l2-flow-tracing", "all"):
            _generate_l2_flow_tracing(config, output_dir, theme_preset)

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
# Export (bundled docs + training kit)
# ---------------------------------------------------------------------------

@main.group()
def export() -> None:
    """Extract bundled documentation and training material."""


def _bundled_dir(name: str) -> Path:
    """Return a real Path to a bundled package data directory."""
    from importlib.resources import as_file, files

    traversable = files("quicksight_gen") / name
    # as_file() materializes to a real Path even when imported from a zip.
    # Closing the context manager when the wheel is on-disk is a no-op.
    with as_file(traversable) as path:
        if not path.is_dir():
            raise click.ClickException(
                f"Bundled '{name}/' directory not found in installed package."
            )
        return path


def _copy_tree(src: Path, dst: Path) -> int:
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return sum(1 for p in dst.rglob("*") if p.is_file())


# -- Whitelabel substitution (used by `export training --mapping`) ----------
#
# Phase L will likely replace this with template-rendered docs (persona-typed
# Jinja or similar) so canonical strings stop being load-bearing. Until then,
# this is a small string-substitution pipeline scoped to one command.

_WHITELABEL_LEAF_RE = re.compile(r'^\s*(?:"([^"]+)"|([^:\s][^:]*?))\s*:\s*(.*?)\s*$')

_WHITELABEL_LEFTOVER_PATTERNS = [
    r"Sasquatch", r"\bSNB\b", r"Bigfoot", r"Big Meadow",
    r"Cascade Timber", r"Pinecrest", r"Harvest Moon",
]


@dataclass
class _WhitelabelResult:
    files_processed: int = 0
    total_substitutions: int = 0
    leftovers: list[tuple[str, str]] = field(default_factory=list)
    per_file: list[tuple[str, int]] = field(default_factory=list)


def _parse_mapping(path: Path) -> dict[str, str]:
    """Parse the YAML-subset mapping file used by `export training`.

    Supported syntax: ``key: value`` or ``"key with spaces": "value"`` per
    line; ``#`` comments; nested group headers ignored; empty values skipped.
    """
    subs: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw = raw_line.rstrip("\n")
        stripped = raw.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        idx = raw.find(" #")
        if idx >= 0:
            raw = raw[:idx]
        m = _WHITELABEL_LEAF_RE.match(raw)
        if not m:
            continue
        key = m.group(1) or m.group(2)
        val = m.group(3).strip()
        if not val:
            continue
        if (val.startswith('"') and val.endswith('"')) or \
           (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        if not val:
            continue
        subs[key] = val
    return subs


def _apply_whitelabel(
    source: Path,
    output: Path,
    mapping: dict[str, str] | None = None,
    *,
    dry_run: bool = False,
) -> _WhitelabelResult:
    """Copy ``source`` to ``output`` applying string substitutions.

    Longest keys substitute first so prefixes (e.g. ``SNB`` inside
    ``Sasquatch National Bank``) don't get rewritten in the wrong order.
    Returns counts plus a list of files where canonical SNB-pattern strings
    survived the rewrite (suggests a missing mapping entry).
    """
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source}")

    subs = mapping or {}
    ordered_keys = sorted(subs.keys(), key=len, reverse=True)
    result = _WhitelabelResult()

    if not dry_run:
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)

    for src_file in sorted(source.rglob("*")):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(source)
        try:
            content = src_file.read_text(encoding="utf-8")
            is_text = True
        except UnicodeDecodeError:
            content = ""
            is_text = False

        file_subs = 0
        if is_text:
            for key in ordered_keys:
                hits = content.count(key)
                if hits:
                    content = content.replace(key, subs[key])
                    file_subs += hits

        result.files_processed += 1
        result.total_substitutions += file_subs
        result.per_file.append((str(rel), file_subs))

        if not dry_run:
            dst = output / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if is_text:
                dst.write_text(content, encoding="utf-8")
            else:
                shutil.copy2(src_file, dst)

        if is_text:
            for pat in _WHITELABEL_LEFTOVER_PATTERNS:
                if re.search(pat, content):
                    result.leftovers.append((str(rel), pat))
                    break

    return result


@export.command("docs")
@click.option(
    "--output", "-o",
    type=click.Path(), required=True,
    help="Target directory; created if missing, merged into if existing.",
)
def export_docs_cmd(output: str) -> None:
    """Copy the operator + engineering handbooks (mkdocs source) to a folder."""
    src = _bundled_dir("docs")
    dst = Path(output)
    count = _copy_tree(src, dst)
    click.echo(f"Wrote {count} documentation files to {dst}")


@export.command("training")
@click.option(
    "--output", "-o",
    type=click.Path(), required=True,
    help="Target directory; created if missing, replaced if existing.",
)
@click.option(
    "--mapping",
    type=click.Path(exists=True),
    help="Optional whitelabel mapping file (YAML subset). "
         "When set, applies branding substitutions to every shipped file.",
)
@click.option("--dry-run", "-n", is_flag=True, help="Report what would happen; write nothing.")
def export_training_cmd(output: str, mapping: str | None, dry_run: bool) -> None:
    """Copy the training handbook to a folder, optionally whitelabeled.

    Without --mapping, ships the canonical Sasquatch-named copy. With
    --mapping pointing at a populated mapping.yaml (see the bundled
    mapping.yaml.example for the template), every occurrence of the
    canonical strings is rewritten to your organization's names.
    """
    src = _bundled_dir("training") / "handbook"
    dst = Path(output)

    subs: dict[str, str] = {}
    if mapping:
        subs = _parse_mapping(Path(mapping))
        if not subs:
            click.echo(
                f"WARNING: No non-empty substitutions in {mapping}; "
                "output will match source verbatim.",
                err=True,
            )

    result = _apply_whitelabel(src, dst, subs, dry_run=dry_run)

    verb = "Would write" if dry_run else "Wrote"
    click.echo(
        f"{verb} {result.files_processed} files, "
        f"{result.total_substitutions} substitutions, to {dst}"
    )

    if result.leftovers:
        click.echo(
            "\nWARNING: Possible untranslated canonical strings remain:",
            err=True,
        )
        for rel, pat in result.leftovers:
            click.echo(f"  {rel}  matches /{pat}/", err=True)
        click.echo(
            "Update the mapping and re-run, or accept if intentional.",
            err=True,
        )


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
        raise click.UsageError(
            "Specify an app (investigation) or --all."
        )
    return app


