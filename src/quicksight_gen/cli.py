"""CLI entry point for quicksight-gen."""

from __future__ import annotations

import json
import re
import shutil
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
@click.option("--all", "all_apps", is_flag=True, help="Generate every app.")
@click.pass_context
def generate(
    ctx: click.Context, config: str, output_dir: str,
    all_apps: bool,
) -> None:
    """Generate QuickSight JSON definitions."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["output_dir"] = output_dir
    if ctx.invoked_subcommand is not None:
        return
    if all_apps:
        _generate_investigation(config, output_dir)
        _generate_executives(config, output_dir)
        _generate_l1_dashboard(config, output_dir)
        _generate_l2_flow_tracing(config, output_dir)
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
    _generate_executives(ctx.obj["config"], ctx.obj["output_dir"])


@generate.command("investigation")
@click.pass_context
def generate_investigation_cmd(ctx: click.Context) -> None:
    """Generate Investigation JSON."""
    _generate_investigation(ctx.obj["config"], ctx.obj["output_dir"])


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
        ctx.obj["config"], ctx.obj["output_dir"],
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
        ctx.obj["config"], ctx.obj["output_dir"],
        l2_instance_path=l2_instance_path,
    )


def _generate_investigation(
    config_path: str, output_dir: str,
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
    from quicksight_gen.common.theme import resolve_l2_theme

    cfg = load_config(config_path)
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
        cfg = cfg.with_l2_instance_prefix(str(l2_instance.instance))

    click.echo(
        f"Investigation: account={cfg.aws_account_id}, "
        f"region={cfg.aws_region}, l2_instance={l2_instance.instance}"
    )

    theme = build_theme(cfg, resolve_l2_theme(l2_instance))
    if theme is not None:
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
    config_path: str, output_dir: str,
    *,
    l2_instance_path: str | None = None,
) -> None:
    from dataclasses import replace as _replace

    from quicksight_gen.apps.executives.app import (
        build_executives_app,
    )
    from quicksight_gen.apps.executives.datasets import build_all_datasets
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
    from quicksight_gen.common.l2 import load_instance
    from quicksight_gen.common.theme import resolve_l2_theme

    cfg = load_config(config_path)
    out = Path(output_dir)

    # N.4.d — Executives reads the same institution YAML the L1
    # dashboard does (per the N.2 audit). Load the L2 instance up
    # front and pre-stamp ``cfg.l2_instance_prefix`` so both
    # ``build_all_datasets`` and ``build_executives_app`` see the
    # prefix without needing to thread the instance through every
    # builder.
    if l2_instance_path is not None:
        l2_instance = load_instance(Path(l2_instance_path))
    else:
        l2_instance = default_l2_instance()
    if cfg.l2_instance_prefix is None:
        cfg = cfg.with_l2_instance_prefix(str(l2_instance.instance))

    click.echo(
        f"Executives: account={cfg.aws_account_id}, "
        f"region={cfg.aws_region}, l2_instance={l2_instance.instance}"
    )

    theme = build_theme(cfg, resolve_l2_theme(l2_instance))
    if theme is not None:
        _write_json(out / "theme.json", theme.to_aws_json())

    datasets = build_all_datasets(cfg)
    _prune_stale_files(
        out / "datasets",
        keep=_all_dataset_filenames(cfg, keep_current=datasets),
    )
    for ds in datasets:
        _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())

    # Build the app once + emit both Analysis + Dashboard so the L2
    # instance is consistent across both (mirrors L1 / L2FT / Inv).
    app = build_executives_app(cfg, l2_instance=l2_instance)
    _write_json(
        out / "executives-analysis.json",
        app.emit_analysis().to_aws_json(),
    )
    _write_json(
        out / "executives-dashboard.json",
        app.emit_dashboard().to_aws_json(),
    )

    click.echo(f"\nGenerated {1 + len(datasets) + 2} files in {out}/")


def _generate_l1_dashboard(
    config_path: str, output_dir: str,
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
    from quicksight_gen.common.theme import resolve_l2_theme

    cfg = load_config(config_path)
    out = Path(output_dir)

    if l2_instance_path is not None:
        l2_instance = load_instance(Path(l2_instance_path))
    else:
        l2_instance = default_l2_instance()

    click.echo(
        f"L1 Dashboard: account={cfg.aws_account_id}, "
        f"region={cfg.aws_region}, l2_instance={l2_instance.instance}"
    )

    theme = build_theme(cfg, resolve_l2_theme(l2_instance))
    if theme is not None:
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
    config_path: str, output_dir: str,
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
    from quicksight_gen.common.theme import resolve_l2_theme

    cfg = load_config(config_path)
    out = Path(output_dir)

    if l2_instance_path is not None:
        l2_instance = load_instance(Path(l2_instance_path))
    else:
        l2_instance = default_l2_instance()

    click.echo(
        f"L2 Flow Tracing: account={cfg.aws_account_id}, "
        f"region={cfg.aws_region}, l2_instance={l2_instance.instance}"
    )

    theme = build_theme(cfg, resolve_l2_theme(l2_instance))
    if theme is not None:
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
        else cfg.with_l2_instance_prefix(str(default_l2.instance))
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
        # P.5.b — seed_hash is now per-dialect dict on L2Instance. The
        # CLI's emit_seed call uses the default Postgres dialect; check
        # against the ``postgres`` entry only.
        declared = instance.seed_hash
        if declared is None:
            click.echo(
                "  [error] --check-hash requested but YAML has no "
                "`seed_hash:` field; run with --lock first.",
                err=True,
            )
            raise SystemExit(1)
        expected = declared.get("postgres")
        if expected is None:
            click.echo(
                "  [error] --check-hash requested but YAML's `seed_hash:` "
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
        click.echo(f"Wrote auto-seed to {out}", err=True)


def _rewrite_seed_hash_in_yaml(yaml_path: Path, new_hash: str) -> None:
    """Idempotently set ``seed_hash.postgres: <new_hash>`` on a YAML
    file.

    P.5.b — seed_hash is now a per-dialect dict in YAML. ``--lock`` only
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
        # Find the end of the block: either the next top-level key or
        # the end of file. A "top-level key" is a line with no leading
        # whitespace and a ``:`` separator.
        end_at = len(lines)
        existing_oracle: str | None = None
        for j in range(seen_at + 1, len(lines)):
            stripped = lines[j].lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            if not lines[j][:1].isspace():
                end_at = j
                break
            # Capture the existing oracle hash so we don't lose it
            # when --lock only refreshes the postgres value.
            m = re.match(r"\s+oracle\s*:\s*(\w+)", lines[j])
            if m:
                existing_oracle = m.group(1)
        # Reassemble preserving the oracle entry if it was present.
        if existing_oracle is not None:
            new_block = (
                f"seed_hash:\n"
                f"  postgres: {new_hash}\n"
                f"  oracle: {existing_oracle}\n"
            )
        lines = lines[:seen_at] + [new_block] + lines[end_at:]
    else:
        # Append, ensuring the file ends with a newline first.
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        lines.append(new_block)
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


def _oracle_dsn(url: str) -> str:
    """Translate a SQLAlchemy-style Oracle URL into an oracledb DSN.

    Accepts either form:
    - ``oracle+oracledb://user:pass@host:port/?service_name=XEPDB1``
    - ``user/pass@host:port/XEPDB1`` (oracledb's native format)

    Returns a string oracledb.connect() understands.
    """
    if url.startswith(("oracle://", "oracle+oracledb://")):
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(url)
        user = parsed.username or ""
        pw = parsed.password or ""
        host = parsed.hostname or "localhost"
        port = parsed.port or 1521
        service = (
            parse_qs(parsed.query).get("service_name", [None])[0]
            or parsed.path.lstrip("/")
            or "FREEPDB1"
        )
        return f"{user}/{pw}@{host}:{port}/{service}"
    return url


def _execute_script(cur, sql: str, *, dialect) -> None:
    """Run a multi-statement SQL string against the cursor.

    Postgres (psycopg2): the whole string in one execute call works.
    Oracle (oracledb): cursor.execute requires single statements (not
    PL/SQL blocks; not "; "-separated). Split + execute per-statement,
    handling PL/SQL blocks (BEGIN…END;) as a unit.
    """
    from quicksight_gen.common.sql import Dialect
    if dialect is Dialect.POSTGRES:
        cur.execute(sql)
        return
    # Oracle: split on bare ";" outside PL/SQL blocks.
    for i, stmt in enumerate(_split_oracle_script(sql)):
        try:
            cur.execute(stmt)
        except Exception as e:
            # Surface which statement (out of N) failed + show its first
            # 200 chars so the failure is debuggable without re-emitting
            # the full DDL script.
            preview = stmt.strip()[:1500]
            raise RuntimeError(
                f"Oracle stmt #{i} failed ({type(e).__name__}: {e})\n"
                f"  Preview: {preview}"
            ) from e


def _split_oracle_script(sql: str) -> list[str]:
    """Split an Oracle-style script into individual statements.

    Handles PL/SQL blocks (anything starting with ``BEGIN`` or
    ``DECLARE`` and ending with ``END;``) as one unit; everything else
    splits on bare ``;``.

    Trailing-semicolon contract differs between the two:

    - **PL/SQL blocks**: the ``;`` is part of the ``END;`` terminator
      and Oracle's parser rejects the block without it
      (PLS-00103 "encountered end-of-file"). Keep it.
    - **Plain SQL statements**: ``oracledb.Cursor.execute`` rejects
      a trailing ``;`` ("invalid character"). Strip it.
    """
    statements: list[str] = []
    buffer: list[str] = []
    in_plsql = False
    for raw_line in sql.splitlines():
        line = raw_line.rstrip()
        # Strip the trailing ``-- comment`` before checking for the
        # statement terminator; a ``;`` inside a SQL line-comment is
        # commentary, not a statement boundary, and treating it as one
        # falsely splits the next CREATE block off into a comment-only
        # "statement" that Oracle rejects with ORA-00900.
        code = line.split("--", 1)[0].rstrip()
        stripped_code = code.strip()
        if not in_plsql and stripped_code.upper().startswith(
            ("BEGIN ", "DECLARE")
        ):
            in_plsql = True
        buffer.append(line)
        if in_plsql:
            # PL/SQL block ends at "END;" (the ; is the PL/SQL
            # statement terminator — keep it, the parser needs it).
            if stripped_code.upper().endswith("END;"):
                statements.append("\n".join(buffer).rstrip())
                buffer = []
                in_plsql = False
        else:
            if stripped_code.endswith(";"):
                # Plain SQL: oracledb rejects the trailing ; — strip.
                stmt = "\n".join(buffer).rstrip().rstrip(";")
                # Skip comment-only buffers (`split("--")` left side is
                # empty, so the buffer is all whitespace + comment text).
                # We only need stripped-code non-empty here; the actual
                # SQL body content doesn't matter for emit.
                if stripped_code:
                    statements.append(stmt)
                buffer = []
    # Trailing buffer (no final semicolon)
    tail = "\n".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


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
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance

    cfg = load_config(config_path)
    if not cfg.demo_database_url:
        raise click.ClickException(
            "demo_database_url is required for 'demo apply'. "
            "Set it in your config YAML or via QS_GEN_DEMO_DATABASE_URL."
        )

    from quicksight_gen.common.sql import Dialect
    if cfg.dialect is Dialect.POSTGRES:
        try:
            import psycopg2  # type: ignore[import-untyped]
        except ImportError:
            raise click.ClickException(
                "psycopg2 is required for 'demo apply' against Postgres. "
                "Install it with: pip install 'quicksight-gen[demo]'"
            )
        connect_fn = psycopg2.connect
    elif cfg.dialect is Dialect.ORACLE:
        try:
            import oracledb  # type: ignore[import-untyped]
        except ImportError:
            raise click.ClickException(
                "oracledb is required for 'demo apply' against Oracle. "
                "Install it with: pip install 'quicksight-gen[demo-oracle]'"
            )
        connect_fn = lambda url: oracledb.connect(_oracle_dsn(url))
    else:
        raise click.ClickException(
            f"Unknown dialect {cfg.dialect!r}. "
            "Set 'dialect: postgres' or 'dialect: oracle' in your config."
        )

    from quicksight_gen.common.l2.schema import (
        emit_schema as emit_l2_schema,
        refresh_matviews_sql,
    )
    from quicksight_gen.common.l2.seed import emit_seed as emit_l2_seed
    from quicksight_gen.common.l2.auto_scenario import default_scenario_for

    # Pre-stamp ``cfg.l2_instance_prefix`` from the default L2 instance
    # before opening the DB connection: the REFRESH MATERIALIZED VIEW
    # calls below reference ``<prefix>_inv_*`` and would land on
    # ``None_inv_pair_rolling_anomalies`` if the prefix isn't set yet.
    # Clear ``datasource_arn`` at the same time so ``Config.__post_init__``
    # re-derives it with the prefix included (otherwise the per-app
    # builders bake the unprefixed ``qs-gen-demo-datasource`` ARN into
    # the dataset JSON, and deploy fails with "Invalid dataSourceArn").
    inv_l2 = default_l2_instance()
    if cfg.l2_instance_prefix is None:
        cfg = cfg.with_l2_instance_prefix(str(inv_l2.instance))

    # The L2 instance carries its full per-prefix DDL — base tables
    # (``<prefix>_transactions`` / ``<prefix>_daily_balances``), Current*
    # views, L1 invariant matviews, AND the Inv matviews (N.3.n /
    # N.4.h). The legacy global ``schema.sql`` was retired in P.1.
    l2_schema_sql = emit_l2_schema(inv_l2, dialect=cfg.dialect)

    # Plant the L2-shape demo seed: every L1 SHOULD-violation kind
    # (drift / overdraft / limit-breach / stuck-pending /
    # stuck-unbundled / supersession) plus the Investigation
    # InvFanoutPlant — landed via the auto-derived scenario picker.
    # P.1 retired the legacy ``apps/investigation/demo_data.py``
    # (which planted v5-shape flat-table data into the now-deleted
    # unprefixed ``transactions`` / ``daily_balances`` tables).
    seed_sql = emit_l2_seed(
        inv_l2, default_scenario_for(inv_l2).scenario,
        dialect=cfg.dialect,
    )

    click.echo(f"Connecting to {cfg.demo_database_url.split('@')[-1]}...")
    conn = connect_fn(cfg.demo_database_url)
    try:
        with conn.cursor() as cur:
            click.echo("  Applying L2 instance schema...")
            _execute_script(cur, l2_schema_sql, dialect=cfg.dialect)
            click.echo("  Inserting seed data...")
            _execute_script(cur, seed_sql, dialect=cfg.dialect)
            click.echo("  Refreshing materialized views...")
            # Refresh every per-instance L1 + Inv matview in dependency
            # order: leaves (current_*) → helpers (computed_*) → L1
            # invariants (drift / overdraft / limit_breach / stuck_*) →
            # dashboard-shape rollups (daily_statement_summary /
            # todays_exceptions) → Inv matviews. Without this the
            # dashboards render empty even though emit_seed planted the
            # base-table rows — the matviews themselves stay empty.
            # ``refresh_matviews_sql`` returns one statement per line
            # (REFRESHes first, then ANALYZEs). Route through
            # ``_execute_script`` so the per-dialect splitter handles
            # the Oracle PL/SQL ``END;`` terminator correctly (Oracle
            # rejects ``BEGIN ... END`` without the trailing ``;``).
            refresh_sql = refresh_matviews_sql(inv_l2, dialect=cfg.dialect)
            _execute_script(cur, refresh_sql, dialect=cfg.dialect)
        conn.commit()
        click.echo("  Database ready.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # N.4.j: theme is fully L2-driven. ``demo apply`` uses the
    # default L2 instance for both Investigation + Executives, so the
    # theme comes from that instance via ``resolve_l2_theme``. When
    # the instance has no ``theme:`` block (the silent-fallback
    # contract), ``build_theme`` returns None and we skip writing
    # ``theme.json`` — AWS QuickSight CLASSIC takes over at deploy.
    # ``inv_l2`` + ``cfg.l2_instance_prefix`` were pre-stamped above
    # so the REFRESH MATERIALIZED VIEW calls had a valid prefix.
    from quicksight_gen.common.datasource import build_datasource
    from quicksight_gen.common.theme import resolve_l2_theme

    click.echo("\nGenerating QuickSight JSON...")

    out = Path(output_dir)

    datasource = build_datasource(cfg)
    _write_json(out / "datasource.json", datasource.to_aws_json())

    theme = build_theme(cfg, resolve_l2_theme(inv_l2))
    if theme is not None:
        _write_json(out / "theme.json", theme.to_aws_json())

    json_count = 1 + (1 if theme is not None else 0)  # datasource (+ theme)
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
        # Executives has no demo seed of its own — reads what
        # Investigation plants. N.4.d: now L2-fed; passes the same
        # default L2 instance Investigation uses (one institution YAML
        # drives all four apps per the N.2 audit).
        exec_datasets = build_exec_datasets(cfg)
        for ds in exec_datasets:
            _write_json(out / "datasets" / f"{ds.DataSetId}.json", ds.to_aws_json())
        _write_json(
            out / "executives-analysis.json",
            build_exec_analysis(cfg, l2_instance=inv_l2).to_aws_json(),
        )
        _write_json(
            out / "executives-dashboard.json",
            build_executives_dashboard(
                cfg, l2_instance=inv_l2,
            ).to_aws_json(),
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
def deploy_cmd(
    app: str | None, all_apps: bool, config: str, output_dir: str,
    generate_first: bool,
) -> None:
    """Deploy generated JSON to AWS QuickSight (delete-then-create)."""
    from quicksight_gen.common.deploy import deploy

    app_name = _resolve_app(app, all_apps, allow_all=True)

    if generate_first:
        if app_name in ("investigation", "all"):
            _generate_investigation(config, output_dir)
        if app_name in ("executives", "all"):
            _generate_executives(config, output_dir)
        if app_name in ("l1-dashboard", "all"):
            _generate_l1_dashboard(config, output_dir)
        if app_name in ("l2-flow-tracing", "all"):
            _generate_l2_flow_tracing(config, output_dir)

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
# Export (bundled docs)
# ---------------------------------------------------------------------------

@main.group()
def export() -> None:
    """Extract bundled documentation."""


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


@export.command("docs")
@click.option(
    "--output", "-o",
    type=click.Path(), required=True,
    help="Target directory; created if missing, merged into if existing.",
)
@click.option(
    "--l2-instance",
    type=click.Path(exists=True),
    help=(
        "Optional path to the L2 institution YAML to bind the rendered "
        "docs against. The path is validated here; the actual binding "
        "happens at mkdocs build time via the QS_DOCS_L2_INSTANCE env "
        "var. The CLI echoes the right command to run after copying."
    ),
)
def export_docs_cmd(output: str, l2_instance: str | None) -> None:
    """Copy the unified docs site (mkdocs source) to a folder.

    The exported tree is a complete mkdocs source layout — run
    ``mkdocs build`` (or ``mkdocs serve``) from inside it to render.
    Pass ``--l2-instance`` to validate an L2 YAML path; the CLI then
    echoes the env var the integrator should set so the rendered docs
    pull vocabulary from that institution instead of the default
    ``spec_example``.
    """
    src = _bundled_dir("docs")
    dst = Path(output)
    count = _copy_tree(src, dst)
    click.echo(f"Wrote {count} documentation files to {dst}")

    if l2_instance is not None:
        l2_path = Path(l2_instance).resolve()
        click.echo("")
        click.echo(
            "L2 instance bound: " + str(l2_path) + "\n"
            "To render against this instance, run:\n"
            f"    QS_DOCS_L2_INSTANCE={l2_path} mkdocs build -f {dst}/mkdocs.yml"
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


