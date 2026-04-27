"""Cleanup orphaned QuickSight resources managed by quicksight-gen.

Lists every resource in the configured account+region that carries the
``ManagedBy: quicksight-gen`` tag and is NOT present in the current
generate output directory, prints them, and (after a single y/n
confirmation) deletes them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import boto3
import click
from botocore.exceptions import ClientError

from quicksight_gen.common.config import Config


MANAGED_TAG_KEY = "ManagedBy"
MANAGED_TAG_VALUE = "quicksight-gen"
L2_INSTANCE_TAG_KEY = "L2Instance"


def _read_managed_tags(client, resource_arn: str) -> dict[str, str] | None:
    """Return the resource's tag map IF it carries ``ManagedBy: quicksight-gen``.

    Returns None if the resource is not ours (or we can't read its tags).
    Caller uses the returned map to additionally filter on ``L2Instance``
    when ``cfg.l2_instance_prefix`` is set (M.2d.3).
    """
    try:
        resp = client.list_tags_for_resource(ResourceArn=resource_arn)
    except ClientError:
        return None
    tag_map: dict[str, str] = {}
    for tag in resp.get("Tags", []):
        key = tag.get("Key")
        value = tag.get("Value")
        if isinstance(key, str) and isinstance(value, str):
            tag_map[key] = value
    if tag_map.get(MANAGED_TAG_KEY) != MANAGED_TAG_VALUE:
        return None
    return tag_map


def _expected_ids_from_out(out_dir: Path, cfg: Config) -> dict[str, set[str]]:
    """Collect the IDs of every resource produced by the current generate run.

    The currently-configured ``datasource_arn`` is always treated as active —
    ``generate`` never writes a datasource.json (only ``demo apply`` does), so
    without this the active datasource would be flagged stale on every run.
    """
    expected: dict[str, set[str]] = {
        "dashboard": set(),
        "analysis": set(),
        "dataset": set(),
        "theme": set(),
        "datasource": set(),
    }

    if cfg.datasource_arn:
        expected["datasource"].add(cfg.datasource_arn.rsplit("/", 1)[-1])

    if not out_dir.exists():
        return expected

    for path in out_dir.glob("*-dashboard.json"):
        expected["dashboard"].add(json.loads(path.read_text())["DashboardId"])
    for path in out_dir.glob("*-analysis.json"):
        expected["analysis"].add(json.loads(path.read_text())["AnalysisId"])
    datasets_dir = out_dir / "datasets"
    if datasets_dir.is_dir():
        for path in datasets_dir.glob("*.json"):
            expected["dataset"].add(json.loads(path.read_text())["DataSetId"])
    theme_path = out_dir / "theme.json"
    if theme_path.exists():
        expected["theme"].add(json.loads(theme_path.read_text())["ThemeId"])
    datasource_path = out_dir / "datasource.json"
    if datasource_path.exists():
        expected["datasource"].add(json.loads(datasource_path.read_text())["DataSourceId"])
    return expected


def _iter_dashboards(client, account_id: str) -> Iterable[tuple[str, str]]:
    paginator = client.get_paginator("list_dashboards")
    for page in paginator.paginate(AwsAccountId=account_id):
        for item in page.get("DashboardSummaryList", []):
            yield item["DashboardId"], item["Arn"]


def _iter_analyses(client, account_id: str) -> Iterable[tuple[str, str]]:
    paginator = client.get_paginator("list_analyses")
    for page in paginator.paginate(AwsAccountId=account_id):
        for item in page.get("AnalysisSummaryList", []):
            if item.get("Status") == "DELETED":
                continue
            yield item["AnalysisId"], item["Arn"]


def _iter_datasets(client, account_id: str) -> Iterable[tuple[str, str]]:
    paginator = client.get_paginator("list_data_sets")
    for page in paginator.paginate(AwsAccountId=account_id):
        for item in page.get("DataSetSummaries", []):
            yield item["DataSetId"], item["Arn"]


def _iter_themes(client, account_id: str) -> Iterable[tuple[str, str]]:
    paginator = client.get_paginator("list_themes")
    for page in paginator.paginate(AwsAccountId=account_id, Type="CUSTOM"):
        for item in page.get("ThemeSummaryList", []):
            yield item["ThemeId"], item["Arn"]


def _iter_datasources(client, account_id: str) -> Iterable[tuple[str, str]]:
    paginator = client.get_paginator("list_data_sources")
    for page in paginator.paginate(AwsAccountId=account_id):
        for item in page.get("DataSources", []):
            yield item["DataSourceId"], item["Arn"]


def _collect_stale(
    client,
    account_id: str,
    expected: dict[str, set[str]],
    *,
    l2_instance_prefix: str | None = None,
) -> dict[str, list[tuple[str, str]]]:
    """Return stale (id, arn) tuples grouped by resource type.

    When ``l2_instance_prefix`` is set (M.2d.3), only resources whose
    ``L2Instance`` tag matches are eligible for deletion. Untagged
    managed resources (legacy single-tenant deploys, or resources
    deployed before M.2d.3 landed) are skipped — they're owned by a
    different scope. When ``l2_instance_prefix`` is None, falls back
    to the legacy "any ManagedBy resource" sweep for backward compat
    with single-tenant out-dirs.
    """
    stale: dict[str, list[tuple[str, str]]] = {
        "dashboard": [],
        "analysis": [],
        "dataset": [],
        "theme": [],
        "datasource": [],
    }
    iterators = {
        "dashboard": _iter_dashboards,
        "analysis": _iter_analyses,
        "dataset": _iter_datasets,
        "theme": _iter_themes,
        "datasource": _iter_datasources,
    }
    for kind, it in iterators.items():
        for rid, arn in it(client, account_id):
            if rid in expected[kind]:
                continue
            tags = _read_managed_tags(client, arn)
            if tags is None:
                # Not ours.
                continue
            if l2_instance_prefix is not None:
                # Per-instance scope: only sweep matching-tag resources.
                if tags.get(L2_INSTANCE_TAG_KEY) != l2_instance_prefix:
                    continue
            stale[kind].append((rid, arn))
    return stale


def _delete_stale(
    client, account_id: str, stale: dict[str, list[tuple[str, str]]],
) -> int:
    """Delete stale resources in dependency order. Returns failure count."""
    failures = 0

    for rid, _ in stale["dashboard"]:
        click.echo(f"  deleting dashboard {rid}")
        try:
            client.delete_dashboard(AwsAccountId=account_id, DashboardId=rid)
        except ClientError as exc:
            click.echo(f"    error: {exc}")
            failures += 1
    for rid, _ in stale["analysis"]:
        click.echo(f"  deleting analysis {rid}")
        try:
            client.delete_analysis(
                AwsAccountId=account_id,
                AnalysisId=rid,
                ForceDeleteWithoutRecovery=True,
            )
        except ClientError as exc:
            click.echo(f"    error: {exc}")
            failures += 1
    for rid, _ in stale["dataset"]:
        click.echo(f"  deleting dataset {rid}")
        try:
            client.delete_data_set(AwsAccountId=account_id, DataSetId=rid)
        except ClientError as exc:
            click.echo(f"    error: {exc}")
            failures += 1
    for rid, _ in stale["theme"]:
        click.echo(f"  deleting theme {rid}")
        try:
            client.delete_theme(AwsAccountId=account_id, ThemeId=rid)
        except ClientError as exc:
            click.echo(f"    error: {exc}")
            failures += 1
    for rid, _ in stale["datasource"]:
        click.echo(f"  deleting datasource {rid}")
        try:
            client.delete_data_source(AwsAccountId=account_id, DataSourceId=rid)
        except ClientError as exc:
            click.echo(f"    error: {exc}")
            failures += 1
    return failures


def run_cleanup(
    cfg: Config, out_dir: Path, *, dry_run: bool = False, skip_confirm: bool = False,
) -> int:
    """Entrypoint for the `cleanup` CLI command."""
    client = boto3.client("quicksight", region_name=cfg.aws_region)
    account_id = cfg.aws_account_id

    scope_label = (
        f" scoped to L2Instance={cfg.l2_instance_prefix!r}"
        if cfg.l2_instance_prefix
        else ""
    )
    click.echo(
        f"Scanning QuickSight resources in {account_id} "
        f"({cfg.aws_region}){scope_label}..."
    )
    expected = _expected_ids_from_out(out_dir, cfg)
    stale = _collect_stale(
        client, account_id, expected,
        l2_instance_prefix=cfg.l2_instance_prefix,
    )

    total = sum(len(items) for items in stale.values())
    if total == 0:
        click.echo("No stale tagged resources found. Nothing to do.")
        return 0

    click.echo(f"\nFound {total} stale tagged resource(s):")
    for kind in ("dashboard", "analysis", "dataset", "theme", "datasource"):
        for rid, _ in stale[kind]:
            click.echo(f"  [{kind}] {rid}")

    if dry_run:
        click.echo("\n(dry-run) not deleting anything.")
        return 0

    if not skip_confirm:
        if not click.confirm("\nDelete all of these?", default=False):
            click.echo("Aborted.")
            return 0

    click.echo()
    failures = _delete_stale(client, account_id, stale)
    click.echo()
    if failures:
        click.echo(f"Completed with {failures} failure(s).")
        return 1
    click.echo("Cleanup complete.")
    return 0
