"""Ad-hoc: screenshot the Getting Started tab for each deployed dashboard."""

from __future__ import annotations

from pathlib import Path

from quicksight_gen.common.browser.helpers import (
    SCREENSHOT_DIR,
    generate_dashboard_embed_url,
    screenshot,
    wait_for_dashboard_loaded,
    webkit_page,
)
from quicksight_gen.common.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cfg = load_config(str(ROOT / "run" / "config.yaml"))
    # Embed URL must be generated against the dashboard region, not us-east-1.

    dashboards = [
        ("payment_recon", f"{cfg.resource_prefix}-payment-recon-dashboard"),
        ("account_recon", f"{cfg.resource_prefix}-account-recon-dashboard"),
    ]

    for subdir, dashboard_id in dashboards:
        print(f"==> {dashboard_id}")
        url = generate_dashboard_embed_url(
            aws_account_id=cfg.aws_account_id,
            aws_region=cfg.aws_region,
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
