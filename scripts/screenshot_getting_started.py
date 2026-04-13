"""Ad-hoc: screenshot the Getting Started tab for each deployed dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import boto3  # noqa: E402
from e2e.browser_helpers import (  # noqa: E402
    SCREENSHOT_DIR,
    generate_dashboard_embed_url,
    screenshot,
    wait_for_dashboard_loaded,
    webkit_page,
)

from quicksight_gen.common.config import load_config  # noqa: E402


def main() -> None:
    cfg = load_config(str(ROOT / "run" / "config.yaml"))
    # Embed URL must be generated against the dashboard region, not us-east-1.
    qs = boto3.client("quicksight", region_name=cfg.aws_region)

    dashboards = [
        ("payment_recon", f"{cfg.resource_prefix}-payment-recon-dashboard"),
        ("account_recon", f"{cfg.resource_prefix}-account-recon-dashboard"),
    ]

    for subdir, dashboard_id in dashboards:
        print(f"==> {dashboard_id}")
        url = generate_dashboard_embed_url(
            qs_identity_client=qs,
            account_id=cfg.aws_account_id,
            dashboard_id=dashboard_id,
        )
        with webkit_page(headless=True, viewport=(1600, 2400)) as page:
            page.goto(url, timeout=30000)
            wait_for_dashboard_loaded(page, timeout_ms=30000)
            page.wait_for_timeout(2000)
            path = screenshot(page, "getting_started", subdir=subdir)
            print(f"    wrote {path}")


if __name__ == "__main__":
    main()
