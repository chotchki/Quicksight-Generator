"""Capture per-sheet screenshots of the deployed L1 dashboard.

Walks the L1 Reconciliation Dashboard tree via ``ScreenshotHarness``
and writes one PNG per sheet to
``src/quicksight_gen/docs/walkthroughs/screenshots/l1/<sheet_id>.png``.
The handbook page (``docs/handbook/l1.md``) embeds these by file name.

Aurora cold-start handling per F12: warm the cluster with a `SELECT 1`
before fetching the embed URL — otherwise QuickSight surfaces a
generic "We can't open that dashboard" error during the first walk.

Usage::

    .venv/bin/python scripts/capture_l1_screenshots.py
    .venv/bin/python scripts/capture_l1_screenshots.py --skip-warmup

Requires the dashboard already deployed (``quicksight-gen deploy
l1-dashboard``) and ``run/config.yaml`` populated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
from quicksight_gen.apps.l1_dashboard.app import build_l1_dashboard_app
from quicksight_gen.common.browser.helpers import (
    click_sheet_tab,
    generate_dashboard_embed_url,
    wait_for_dashboard_loaded,
    webkit_page,
)
from quicksight_gen.common.config import load_config

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT_DIR = (
    _REPO_ROOT / "src" / "quicksight_gen" / "docs"
    / "walkthroughs" / "screenshots" / "l1"
)


def _warm_aurora(database_url: str) -> None:
    """Per F12: prevent QuickSight's "We can't open that dashboard"
    error during a cold-start dashboard load by issuing a `SELECT 1`
    against the cluster first."""
    import psycopg2  # type: ignore[import-untyped]
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchall()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=_REPO_ROOT / "run" / "config.yaml",
        help="path to config YAML (default: run/config.yaml)",
    )
    parser.add_argument(
        "--skip-warmup", action="store_true",
        help="skip the Aurora cold-start warmup query",
    )
    args = parser.parse_args()

    cfg = load_config(str(args.config))
    if not cfg.demo_database_url:
        print(
            f"FATAL: {args.config} has no demo_database_url",
            file=sys.stderr,
        )
        return 2

    if not args.skip_warmup:
        print("→ Warming Aurora (SELECT 1)...", end=" ", flush=True)
        _warm_aurora(cfg.demo_database_url)
        print("OK")

    # Build the L1 App tree so ScreenshotHarness can walk it. This is
    # the same tree the deployed dashboard was built from — emit_analysis()
    # resolves auto-IDs so sheet objects match deployed sheet IDs.
    inst = default_l2_instance()
    app = build_l1_dashboard_app(cfg, l2_instance=inst)
    app.emit_analysis()  # resolve auto-IDs

    dashboard_id = f"{cfg.resource_prefix}-l1-dashboard"
    print(f"→ Generating embed URL for {dashboard_id}...", end=" ", flush=True)
    url = generate_dashboard_embed_url(
        aws_account_id=cfg.aws_account_id,
        aws_region=cfg.aws_region,
        dashboard_id=dashboard_id,
    )
    print("OK")

    print(f"→ Writing screenshots to {_OUTPUT_DIR}...")
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Tall viewport so below-the-fold visuals don't virtualize before
    # the screenshot fires (project memory: QS virtualizes vertically).
    # Per the M.2b.12 footgun + CLAUDE.md "Operational Footguns": when
    # QS spinners hang indefinitely, `wait_for_visuals_present` will
    # time out — but the dashboard chrome IS up, just visual data is
    # late. Bypass the visuals-present check; sleep long enough for
    # QS to paint what it can, then snap the page. Visuals that are
    # still spinning will appear as spinners in the PNG (acceptable
    # for handbook docs — we re-run when QS recovers).
    results: dict = {}
    with webkit_page(headless=True, viewport=(1600, 4000)) as page:
        page.goto(url, timeout=120_000)
        wait_for_dashboard_loaded(page, timeout_ms=120_000)
        # Settle: 10s ought to be enough for the first visible sheet.
        page.wait_for_timeout(10_000)
        for sheet in app.analysis.sheets:
            click_sheet_tab(page, sheet.name, 60_000)
            # Per-sheet settle — clicks can require their own load.
            page.wait_for_timeout(8_000)
            sheet_id_safe = (
                str(sheet.sheet_id).replace("/", "-").replace(":", "-")
            )
            path = _OUTPUT_DIR / f"{sheet_id_safe}.png"
            page.screenshot(path=str(path), full_page=True)
            results[sheet] = path
            print(f"  {sheet.name:30s} → captured")

    print()
    for sheet, path in results.items():
        rel = path.relative_to(_REPO_ROOT)
        print(f"  {sheet.name:30s} → {rel}")
    print()
    print(f"Captured {len(results)} sheets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
