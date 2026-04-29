"""Standalone manual deploy of a harness-shaped L1 dashboard for live debugging.

Mimics what the harness does (per-test prefix, ephemeral L2 instance, full
schema+seed+matview-refresh, deploy both L1 + L2FT) but does NOT clean up
at the end — leaves the QuickSight resources live so you can open them in
the QS console and inspect interactively.

Usage:
    .venv/bin/python scripts/harness_manual_deploy.py [PREFIX]

Defaults to PREFIX=manual_inspect. Pass a different prefix to run alongside
existing manual deploys without colliding.

When done, sweep with:
    .venv/bin/python scripts/harness_manual_deploy.py --cleanup PREFIX
"""

from __future__ import annotations

import dataclasses
import sys
import tempfile
from datetime import date
from pathlib import Path

# Make tests/e2e importable
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "tests" / "e2e"))

import psycopg2
from quicksight_gen.common.config import load_config
from quicksight_gen.common.l2 import load_instance
from quicksight_gen.common.l2.primitives import Identifier
from quicksight_gen.common.deploy import deploy as deploy_apps

from _harness_seed import apply_db_seed  # noqa: E402
from _harness_deploy import (  # noqa: E402
    generate_apps,
    extract_dashboard_ids,
    build_embed_urls,
    HARNESS_APPS,
)
from _harness_cleanup import (  # noqa: E402
    sweep_qs_resources_by_tag,
    drop_prefixed_schema,
)


def main() -> int:
    args = sys.argv[1:]
    cleanup_mode = "--cleanup" in args
    if cleanup_mode:
        args.remove("--cleanup")
    prefix = args[0] if args else "manual_inspect"

    cfg = load_config(str(_REPO / "run" / "config.yaml"))
    hcfg = dataclasses.replace(
        cfg,
        # Clear the pre-derived datasource_arn so __post_init__ re-derives
        # it with the new l2_instance_prefix in the path. Without this,
        # datasets get created referencing the unprefixed datasource ARN
        # (which doesn't exist) — same pattern the harness_cfg fixture uses.
        datasource_arn=None,
        extra_tags={"TestUid": prefix, "Harness": "manual"},
        l2_instance_prefix=prefix,
    )

    if cleanup_mode:
        print(f"== CLEANUP for prefix={prefix!r} ==")
        import boto3
        qs = boto3.client("quicksight", region_name=hcfg.aws_region)
        counts = sweep_qs_resources_by_tag(
            qs, hcfg.aws_account_id,
            tag_key="TestUid", tag_value=prefix,
        )
        print(f"Swept QS resources: {counts}")
        if cfg.demo_database_url:
            conn = psycopg2.connect(cfg.demo_database_url)
            try:
                drop_prefixed_schema(conn, prefix)
                print(f"Dropped DB prefix: {prefix}")
            finally:
                conn.close()
        return 0

    print(f"== DEPLOY prefix={prefix!r} ==")
    print(f"  account: {hcfg.aws_account_id}")
    print(f"  region:  {hcfg.aws_region}")
    print(f"  datasource_arn: {hcfg.datasource_arn}")
    print()

    inst = load_instance(_REPO / "tests" / "l2" / "spec_example.yaml")
    inst = dataclasses.replace(inst, instance=Identifier(prefix))

    if cfg.demo_database_url is None:
        print("ERROR: cfg.demo_database_url not set", file=sys.stderr)
        return 1

    print("==> Seeding DB (schema + seed + matview refresh)...")
    conn = psycopg2.connect(cfg.demo_database_url)
    try:
        apply_db_seed(conn, inst, today=date.today())
    finally:
        conn.close()
    print(f"    Seed planted at today={date.today()}")

    out = Path(tempfile.mkdtemp(prefix=f"harness_manual_{prefix}_"))
    print(f"==> Generating JSON to {out}...")
    generate_apps(hcfg, inst, out)

    print("==> Deploying QS resources...")
    rc = deploy_apps(hcfg, out, list(HARNESS_APPS))
    if rc != 0:
        print("ERROR: deploy failed", file=sys.stderr)
        return rc

    ids = extract_dashboard_ids(out)
    urls = build_embed_urls(
        aws_account_id=hcfg.aws_account_id,
        aws_region=hcfg.aws_region,
        dashboard_ids=ids,
    )

    print()
    print("=" * 70)
    print("DEPLOYED — open these in the QuickSight console to inspect:")
    print()
    for app, did in ids.items():
        print(f"  {app}:")
        print(f"    DashboardId: {did}")
        print(f"    Console URL: https://{hcfg.aws_region}.quicksight.aws.amazon.com/sn/dashboards/{did}")
        print()
    print("Embed URLs (SINGLE-USE — open in incognito + expire in 60min):")
    for app, url in urls.items():
        print(f"  {app}:")
        print(f"    {url}")
        print()
    print("=" * 70)
    print(f"When done, clean up with:")
    print(f"  .venv/bin/python scripts/harness_manual_deploy.py --cleanup {prefix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
