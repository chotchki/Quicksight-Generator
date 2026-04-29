"""Capture full-sheet screenshots of the AR Daily Statement walkthrough examples.

Drives the deployed AR dashboard to the three worked examples documented in
``docs/walkthroughs/etl/how-do-i-validate-a-single-account-day.md``:

1. Clean reconciling day  — gl-1010-cash-due-frb (yesterday)
2. Drift day              — cust-900-0001-bigfoot-brews (5 days ago)
3. Overdraft day          — cust-900-0002-sasquatch-sips (6 days ago)

For each, sets the Account + Balance Date parameters, waits for the KPIs and
table to repaint, and writes a tall full-page PNG to
``docs/walkthroughs/screenshots/ar/daily-statement-NN-<scenario>.png``.

Run from the repo root::

    .venv/bin/python scripts/screenshot_daily_statement.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from quicksight_gen.apps.account_recon.demo_data import (
    _OVERDRAFT_PLANT,
    _SUBLEDGER_DRIFT_PLANT,
)
from quicksight_gen.common.browser.helpers import (
    click_sheet_tab,
    generate_dashboard_embed_url,
    set_dropdown_value,
    wait_for_dashboard_loaded,
    wait_for_sheet_controls_present,
    wait_for_visual_titles_present,
    wait_for_visuals_rendered,
    webkit_page,
)
from quicksight_gen.common.config import load_config

ROOT = Path(__file__).resolve().parents[1]


PAGE_TIMEOUT = 60_000
VISUAL_TIMEOUT = 30_000
OUTPUT_ROOT = ROOT / "docs" / "walkthroughs" / "screenshots" / "ar"

# Tall enough to fit the full Daily Statement sheet (5 KPIs + table) without
# QuickSight's below-the-fold virtualization unloading the lower half.
SCREENSHOT_VIEWPORT = (1600, 2400)


def _drift_days_ago(account_id: str) -> int:
    for sid, days_ago, _delta in _SUBLEDGER_DRIFT_PLANT:
        if sid == account_id:
            return days_ago
    raise KeyError(f"{account_id} not in _SUBLEDGER_DRIFT_PLANT")


def _overdraft_days_ago(account_id: str) -> int:
    for sid, days_ago, _amt, _memo in _OVERDRAFT_PLANT:
        if sid == account_id:
            return days_ago
    raise KeyError(f"{account_id} not in _OVERDRAFT_PLANT")


# (slug, account_id, days_ago) for each walkthrough example.
SCENARIOS: list[tuple[str, str, int]] = [
    ("01-clean",     "gl-1010-cash-due-frb",         1),
    ("02-drift",     "cust-900-0001-bigfoot-brews",  _drift_days_ago("cust-900-0001-bigfoot-brews")),
    ("03-overdraft", "cust-900-0002-sasquatch-sips", _overdraft_days_ago("cust-900-0002-sasquatch-sips")),
]


def _set_balance_date(page, when: date) -> None:
    """Fill the single ``Balance Date`` parameter date picker.

    The Daily Statement uses a single ParameterDateTimePickerControl. QS
    renders it as ``[data-automation-id="date_picker_0"]`` (the only date
    input on the sheet). Format is ``YYYY/MM/DD``.
    """
    selector = '[data-automation-id="date_picker_0"]'
    page.wait_for_selector(selector, timeout=VISUAL_TIMEOUT, state="visible")
    page.fill(selector, when.strftime("%Y/%m/%d"))
    page.press(selector, "Enter")


def main() -> int:
    config_path = ROOT / "run" / "config.yaml"
    if not config_path.exists():
        config_path = ROOT / "config.yaml"
    if not config_path.exists():
        print("Could not find run/config.yaml or config.yaml", file=sys.stderr)
        return 1

    cfg = load_config(str(config_path))
    dashboard_id = f"{cfg.resource_prefix}-account-recon-dashboard"
    print(f"==> {dashboard_id}")

    embed_url = generate_dashboard_embed_url(
        aws_account_id=cfg.aws_account_id,
        aws_region=cfg.aws_region,
        dashboard_id=dashboard_id,
    )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    with webkit_page(headless=True, viewport=SCREENSHOT_VIEWPORT) as page:
        page.goto(embed_url, timeout=PAGE_TIMEOUT)
        wait_for_dashboard_loaded(page, PAGE_TIMEOUT)
        wait_for_visuals_rendered(page, PAGE_TIMEOUT)

        click_sheet_tab(page, "Daily Statement", PAGE_TIMEOUT)
        wait_for_sheet_controls_present(page, PAGE_TIMEOUT)
        # The Account parameter defaults to empty; with NullOption=NON_NULLS_ONLY
        # the visuals don't render at all until the dropdown is picked. So set
        # parameters first, then wait for visual titles to appear.

        for slug, account_id, days_ago in SCENARIOS:
            when = date.today() - timedelta(days=days_ago)
            print(f"  -> {slug}: {account_id} on {when}")

            set_dropdown_value(page, "Account", account_id, VISUAL_TIMEOUT)
            _set_balance_date(page, when)
            wait_for_visual_titles_present(
                page, ["Opening Balance", "Transaction Detail"], VISUAL_TIMEOUT,
            )
            # Let the KPIs + table finish their re-query against the new params.
            page.wait_for_timeout(2500)

            output = OUTPUT_ROOT / f"daily-statement-{slug}.png"
            page.screenshot(path=str(output), full_page=True)
            print(f"     wrote {output.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
