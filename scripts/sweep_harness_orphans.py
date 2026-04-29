"""Bulk-delete every QuickSight resource left behind by harness runs.

Harness tests deploy per-test ephemeral QS resources tagged with
``Harness: e2e`` (plus a per-test ``TestUid``). When a test fails
mid-run, teardown may not complete and the resources orphan. This
script sweeps every resource carrying the ``Harness: e2e`` tag —
production deploys don't carry that tag, so they're safe.

Usage::

    .venv/bin/python scripts/sweep_harness_orphans.py            # dry-run (default)
    .venv/bin/python scripts/sweep_harness_orphans.py --confirm  # actually delete

Reads ``run/config.yaml`` (or ``config.yaml``) for the AWS account /
region, builds a boto3 QS client in the dashboard region, and calls
``sweep_qs_resources_by_tag`` from the existing harness cleanup
helper. Returns a per-resource-type deletion count.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "e2e"))

import boto3  # noqa: E402

from _harness_cleanup import sweep_qs_resources_by_tag  # noqa: E402
from quicksight_gen.common.config import load_config  # noqa: E402


HARNESS_TAG_KEY = "Harness"
HARNESS_TAG_VALUE = "e2e"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete (default is dry-run — list only).",
    )
    args = parser.parse_args()

    config_path = ROOT / "run" / "config.yaml"
    if not config_path.exists():
        config_path = ROOT / "config.yaml"
    if not config_path.exists():
        print("Could not find run/config.yaml or config.yaml", file=sys.stderr)
        return 1

    cfg = load_config(str(config_path))
    client = boto3.client("quicksight", region_name=cfg.aws_region)

    if not args.confirm:
        # Dry-run: collect matching resources but don't delete.
        from _harness_cleanup import _collect_resources_matching_tag

        matched = _collect_resources_matching_tag(
            client, cfg.aws_account_id,
            tag_key=HARNESS_TAG_KEY, tag_value=HARNESS_TAG_VALUE,
        )
        print(
            f"==> DRY RUN — would delete resources tagged "
            f"{HARNESS_TAG_KEY}={HARNESS_TAG_VALUE} in "
            f"{cfg.aws_region}:"
        )
        total = 0
        for kind, items in matched.items():
            print(f"    {kind}: {len(items)}")
            total += len(items)
            for resource_id, _arn in items:
                print(f"      - {resource_id}")
        print(f"    total: {total}")
        if total > 0:
            print("\nRe-run with --confirm to actually delete.")
        return 0

    print(
        f"==> Sweeping resources tagged "
        f"{HARNESS_TAG_KEY}={HARNESS_TAG_VALUE} in {cfg.aws_region}"
    )
    counts = sweep_qs_resources_by_tag(
        client, cfg.aws_account_id,
        tag_key=HARNESS_TAG_KEY, tag_value=HARNESS_TAG_VALUE,
    )
    print(f"==> Deleted: {counts}")
    print(f"    total: {sum(counts.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
