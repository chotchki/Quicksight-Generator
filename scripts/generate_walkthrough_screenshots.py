"""Generate focused per-visual screenshots for walkthrough docs.

Reuses the e2e browser harness (Playwright + embed URL) to navigate
the deployed dashboard, scroll each requested visual into view, and
capture a tight per-visual PNG into ``docs/walkthroughs/screenshots/``.

Spike scope (Phase H.2): handful of shots for the existing Stuck in
Internal Transfer Suspense walkthrough so we can judge whether the
inline-toggle-screenshot UX actually helps.

Run from the repo root::

    .venv/bin/python scripts/generate_walkthrough_screenshots.py

Requires the same config as the e2e suite (run/config.yaml or env vars
for ``aws_account_id`` / ``aws_region`` / ``resource_prefix``) plus the
dashboard already deployed. Optionally set ``QS_E2E_USER_ARN`` to embed
for a non-default user.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import boto3  # noqa: E402
from e2e.browser_helpers import (  # noqa: E402
    click_sheet_tab,
    generate_dashboard_embed_url,
    wait_for_dashboard_loaded,
    wait_for_visual_titles_present,
    wait_for_visuals_rendered,
    webkit_page,
)

from quicksight_gen.common.config import load_config  # noqa: E402


PAGE_TIMEOUT = 60_000
VISUAL_TIMEOUT = 30_000
OUTPUT_ROOT = ROOT / "docs" / "walkthroughs" / "screenshots"

# Tall viewport defeats QuickSight's below-the-fold virtualization so every
# visual on a sheet hydrates at once. Same trick the e2e suite uses
# (test_ar_sheet_visuals.TALL_VIEWPORT).
SCREENSHOT_VIEWPORT = (1600, 12_000)


# Per-shot record. ``visual`` is the rendered title; ``title_index`` lets us
# pick the n-th visual when KPI + table share a title (KPI is index 0,
# table is index 1, etc., in render order).
def _shot(visual, slug, step, *, title_index=0, wait_for_cells=False):
    return {
        "app": "ar",
        "dashboard": "account-recon-dashboard",
        "sheet": "Exceptions",
        "visual": visual,
        "title_index": title_index,
        "slug": slug,
        "step": step,
        "wait_for_cells": wait_for_cells,
    }


# SHOTS are listed in TOP-DOWN sheet-layout order so Playwright only ever
# scrolls in one direction. After Playwright scrolls down to capture a
# lower visual, QuickSight may unload virtualized higher visuals — making
# any later "go back up" lookup fail. Top-down avoids that.
SHOTS: list[dict] = [
    # Batch B — baseline checks. Layout (top-down): kpi_row_a (Ledger
    # Drift Days, Sub-Ledger Drift Days, Non-Zero Transfers KPI),
    # kpi_row_b (Limit Breach Days, Overdraft Days), then 5 tables, then
    # 5 aging bars. KPI/table titles match for Non-Zero only (KPI=0,
    # table=1).

    # KPI row a (3 KPIs side-by-side): Ledger Drift, Sub-Ledger Drift, Non-Zero
    _shot("Ledger Drift Days",            "ledger-drift",            "01-kpi"),
    _shot("Sub-Ledger Drift Days",        "sub-ledger-drift",        "01-kpi"),
    _shot("Non-Zero Transfers",           "non-zero-transfers",      "01-kpi", title_index=0),
    # KPI row b (2 KPIs): Limit Breach, Overdraft
    _shot("Limit Breach Days",            "sub-ledger-limit-breach", "01-kpi"),
    _shot("Overdraft Days",               "sub-ledger-overdraft",    "01-kpi"),

    # Tables (paired half-width then full-width Overdraft)
    _shot("Ledger Balance Drift",         "ledger-drift",            "02-table", wait_for_cells=True),
    _shot("Sub-Ledger Balance Drift",     "sub-ledger-drift",        "02-table", wait_for_cells=True),
    _shot("Non-Zero Transfers",           "non-zero-transfers",      "02-table", title_index=1, wait_for_cells=True),
    _shot("Sub-Ledger Limit Breach",      "sub-ledger-limit-breach", "02-table", wait_for_cells=True),
    _shot("Sub-Ledger Overdraft",         "sub-ledger-overdraft",    "02-table", wait_for_cells=True),

    # Aging bars (5 in render order — same order as the data feeds)
    _shot("Ledger Drift by Age",          "ledger-drift",            "03-aging"),
    _shot("Sub-Ledger Drift by Age",      "sub-ledger-drift",        "03-aging"),
    _shot("Non-Zero Transfers by Age",    "non-zero-transfers",      "03-aging"),
    _shot("Limit Breaches by Age",        "sub-ledger-limit-breach", "03-aging"),
    _shot("Overdrafts by Age",            "sub-ledger-overdraft",    "03-aging"),

    # Stuck in Internal Transfer Suspense (F.5.7) — sits well below the
    # baseline section. Same shape: KPI + table (shared title) + aging.
    _shot("Stuck in Internal Transfer Suspense", "stuck-in-internal-transfer-suspense", "01-kpi", title_index=0),
    _shot("Stuck in Internal Transfer Suspense", "stuck-in-internal-transfer-suspense", "02-table", title_index=1, wait_for_cells=True),
    _shot("Stuck Internal Transfers by Age",     "stuck-in-internal-transfer-suspense", "03-aging"),
]


def _screenshot_visual(
    page, title: str, title_index: int, output_path: Path,
) -> None:
    """Tag the n-th title-matched visual with a marker attribute and let
    Playwright take a per-element screenshot of just that visual.

    Marker-attribute approach mirrors browser_helpers.click_first_row_of_visual
    (lines 199–227): page.evaluate sets data-e2e-target on the right element,
    Playwright targets that selector, attribute is cleared after.
    """
    page.wait_for_timeout(500)  # let any in-flight render settle
    found = page.evaluate(
        """({title, idx}) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            const matched = [];
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (t && t.innerText.trim() === title) matched.push(v);
            }
            if (idx >= matched.length) return false;
            matched[idx].setAttribute('data-screenshot-target', '1');
            return true;
        }""",
        {"title": title, "idx": title_index},
    )
    if not found:
        all_titles = page.evaluate(
            """() => Array.from(document.querySelectorAll(
                '[data-automation-id="analysis_visual_title_label"]'
            )).map(el => el.innerText.trim()).filter(Boolean)"""
        )
        raise RuntimeError(
            f"Visual not found by title: {title!r} (index {title_index})\n"
            f"Visible titles ({len(all_titles)}): {all_titles!r}"
        )
    try:
        page.locator('[data-screenshot-target="1"]').first.screenshot(
            path=str(output_path),
            timeout=VISUAL_TIMEOUT,
        )
    finally:
        page.evaluate(
            """() => document.querySelectorAll('[data-screenshot-target]').forEach(
                e => e.removeAttribute('data-screenshot-target')
            )"""
        )


def _resolve_dashboard_id(cfg, dashboard: str) -> str:
    return f"{cfg.resource_prefix}-{dashboard}"


def main() -> int:
    config_path = ROOT / "run" / "config.yaml"
    if not config_path.exists():
        config_path = ROOT / "config.yaml"
    if not config_path.exists():
        print(
            "Could not find run/config.yaml or config.yaml in repo root.",
            file=sys.stderr,
        )
        return 1

    cfg = load_config(str(config_path))
    qs = boto3.client("quicksight", region_name=cfg.aws_region)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    by_dashboard: dict[str, list[dict]] = {}
    for shot in SHOTS:
        by_dashboard.setdefault(shot["dashboard"], []).append(shot)

    for dashboard_suffix, shots in by_dashboard.items():
        dashboard_id = _resolve_dashboard_id(cfg, dashboard_suffix)
        print(f"==> {dashboard_id} ({len(shots)} shots)")

        embed_url = generate_dashboard_embed_url(
            qs_identity_client=qs,
            account_id=cfg.aws_account_id,
            dashboard_id=dashboard_id,
        )

        with webkit_page(headless=True, viewport=SCREENSHOT_VIEWPORT) as page:
            page.goto(embed_url, timeout=PAGE_TIMEOUT)
            wait_for_dashboard_loaded(page, PAGE_TIMEOUT)
            wait_for_visuals_rendered(page, PAGE_TIMEOUT)

            current_sheet: str | None = None
            for shot in shots:
                if shot["sheet"] != current_sheet:
                    click_sheet_tab(page, shot["sheet"], PAGE_TIMEOUT)
                    wait_for_visuals_rendered(page, PAGE_TIMEOUT)
                    current_sheet = shot["sheet"]

                wait_for_visual_titles_present(
                    page, [shot["visual"]], VISUAL_TIMEOUT,
                )

                shot_dir = OUTPUT_ROOT / shot["app"]
                shot_dir.mkdir(parents=True, exist_ok=True)
                output = shot_dir / f"{shot['slug']}-{shot['step']}.png"
                _screenshot_visual(
                    page, shot["visual"], shot["title_index"], output,
                )
                print(f"    wrote {output.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
