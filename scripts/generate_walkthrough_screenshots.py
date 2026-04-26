"""Generate focused per-visual screenshots for walkthrough docs.

Reuses the e2e browser harness (Playwright + embed URL) to navigate
the deployed dashboard, scroll each requested visual into view, and
capture a tight per-visual PNG into the published walkthroughs
screenshots directory (``src/quicksight_gen/docs/walkthroughs/screenshots/``).

Phase K.1.6.a.2 layout: SHOTS list rebuilt around the unified Today's
Exceptions sheet + Exceptions Trends sheet. Three shared shots from
Today's Exceptions, five from Trends, and one filtered-table shot per
check type (×14) — driven by the multi-select Check Type sheet control.

Run from the repo root::

    .venv/bin/python scripts/generate_walkthrough_screenshots.py

Requires the same config as the e2e suite (run/config.yaml or env vars
for ``aws_account_id`` / ``aws_region`` / ``resource_prefix``) plus the
dashboard already deployed. Optionally set ``QS_E2E_USER_ARN`` to embed
for a non-default user.
"""

from __future__ import annotations

import re
from pathlib import Path

import boto3
from playwright.sync_api import TimeoutError as PWTimeoutError
from quicksight_gen.common.browser.helpers import (
    _open_control_dropdown,
    click_sheet_tab,
    generate_dashboard_embed_url,
    wait_for_dashboard_loaded,
    wait_for_visual_titles_present,
    wait_for_visuals_rendered,
    webkit_page,
)
from quicksight_gen.common.config import load_config

ROOT = Path(__file__).resolve().parents[1]


PAGE_TIMEOUT = 60_000
VISUAL_TIMEOUT = 30_000
OUTPUT_ROOT = (
    ROOT / "src" / "quicksight_gen" / "docs" / "walkthroughs" / "screenshots"
)

# Tall viewport defeats QuickSight's below-the-fold virtualization so every
# visual on a sheet hydrates at once. Same trick the e2e suite uses
# (test_ar_sheet_visuals.TALL_VIEWPORT).
SCREENSHOT_VIEWPORT = (1600, 12_000)

SHEET_TODAYS_EXCEPTIONS = "Today's Exceptions"
SHEET_TRENDS = "Exceptions Trends"

# 14 check_type literals, exactly as they appear in the unified-exceptions
# dataset SQL (datasets.py: build_ar_unified_exceptions_dataset). The slug
# matches the per-check walkthrough filename in
# src/quicksight_gen/docs/walkthroughs/ar/<slug>.md so the per-check
# screenshot lands at todays-exceptions-filtered-<slug>.png next to the
# doc that references it.
PER_CHECK: list[tuple[str, str]] = [
    ("Sub-Ledger Drift",                         "sub-ledger-drift"),
    ("Ledger Drift",                             "ledger-drift"),
    ("Non-Zero Transfer",                        "non-zero-transfers"),
    ("Sub-Ledger Limit Breach",                  "sub-ledger-limit-breach"),
    ("Sub-Ledger Overdraft",                     "sub-ledger-overdraft"),
    ("Sweep Target Non-Zero EOD",                "sweep-target-non-zero"),
    ("Concentration Master Sweep Drift",         "concentration-master-sweep-drift"),
    ("ACH Origination Settlement Non-Zero EOD",  "ach-origination-non-zero"),
    ("ACH Sweep Without Fed Confirmation",       "ach-sweep-no-fed-confirmation"),
    ("Fed Activity Without Internal Catch-Up",   "fed-card-no-internal-catchup"),
    ("GL vs Fed Master Drift",                   "gl-vs-fed-master-drift"),
    ("Internal Transfer Stuck in Suspense",      "stuck-in-internal-transfer-suspense"),
    ("Internal Transfer Suspense Non-Zero EOD",  "internal-transfer-suspense-non-zero"),
    ("Internal Reversal Uncredited",             "internal-reversal-uncredited"),
]


def _shot(
    *,
    sheet: str,
    visual: str | None,
    filename: str,
    title_index: int = 0,
    mode: str = "visual",
    filter_check_type: str | None = None,
) -> dict:
    """Per-shot record.

    ``mode="visual"`` (default) tags the n-th title-matched visual and takes
    a per-element screenshot. ``mode="full_sheet"`` clips a screenshot of
    the whole active sheet from y=0 down to the bottom-most visual.
    ``filter_check_type`` (when set) drives the Check Type multi-select to
    that single value before the shot.
    """
    return {
        "app": "ar",
        "dashboard": "account-recon-dashboard",
        "sheet": sheet,
        "visual": visual,
        "filename": filename,
        "title_index": title_index,
        "mode": mode,
        "filter_check_type": filter_check_type,
    }


# Order: visit each sheet in one pass with no filter, then come back to
# Today's Exceptions for the per-check filtered shots. The Check Type
# control is CrossSheet (Today's Exceptions ↔ Trends) so applying a
# filter on Today's Exceptions would also narrow the Trends visuals —
# capturing Trends BEFORE applying any filter keeps those shots clean.
SHOTS: list[dict] = [
    # ---------------------------------------------------------------------
    # Today's Exceptions — shared overview shots (no Check Type filter).
    # ---------------------------------------------------------------------
    _shot(
        sheet=SHEET_TODAYS_EXCEPTIONS,
        visual=None,
        filename="todays-exceptions-overview",
        mode="full_sheet",
    ),
    _shot(
        sheet=SHEET_TODAYS_EXCEPTIONS,
        visual="Exceptions by Check",
        filename="todays-exceptions-breakdown",
    ),
    _shot(
        sheet=SHEET_TODAYS_EXCEPTIONS,
        visual="Open Exceptions",
        filename="todays-exceptions-table",
    ),
    # ---------------------------------------------------------------------
    # Exceptions Trends — five trend / rollup visuals (no Check Type filter).
    # The two rollups are KPI + table pairs in the layout, but QS doesn't
    # render a title label on KPI visuals — only the table side carries the
    # ``analysis_visual_title_label`` for that title. So title_index=0 lands
    # on the table for both rollups, which is the visual the walkthroughs
    # reference for row-level detail.
    # ---------------------------------------------------------------------
    _shot(
        sheet=SHEET_TRENDS,
        visual="Balance Drift Timelines",
        filename="trends-drift-timelines",
    ),
    _shot(
        sheet=SHEET_TRENDS,
        visual="Two-Sided Post Mismatch",
        filename="trends-two-sided-rollup",
    ),
    _shot(
        sheet=SHEET_TRENDS,
        visual="Accounts Expected Zero at EOD",
        filename="trends-expected-zero-rollup",
    ),
    _shot(
        sheet=SHEET_TRENDS,
        visual="Aging by Check",
        filename="trends-aging-by-check",
    ),
    _shot(
        sheet=SHEET_TRENDS,
        visual="Exceptions per Check, by Day",
        filename="trends-per-check-by-day",
    ),
    # ---------------------------------------------------------------------
    # Today's Exceptions — per-check filtered tables (×14). Each shot sets
    # Check Type to one literal value and captures only the unified table.
    # Filename matches the per-check walkthrough's slug so docs and PNGs
    # line up directly.
    # ---------------------------------------------------------------------
    *[
        _shot(
            sheet=SHEET_TODAYS_EXCEPTIONS,
            visual="Open Exceptions",
            filename=f"todays-exceptions-filtered-{slug}",
            filter_check_type=check_type,
        )
        for check_type, slug in PER_CHECK
    ],
]


def _screenshot_visual(
    page, title: str, title_index: int, output_path: Path,
) -> None:
    """Tag the n-th title-matched visual with a marker attribute and let
    Playwright take a per-element screenshot of just that visual.

    Marker-attribute approach mirrors browser_helpers.click_first_row_of_visual:
    page.evaluate sets data-screenshot-target on the right element,
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


def _screenshot_full_sheet(page, output_path: Path) -> None:
    """Clip a screenshot covering all visuals on the active sheet.

    The tall (12000px) viewport leaves the bottom of the page as empty
    whitespace. Compute the bottom y of the lowest visual on the sheet
    and clip the screenshot to that height so the resulting PNG isn't
    8000px of blank canvas.
    """
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(400)
    extent = page.evaluate(
        """() => {
            let max = 0;
            document.querySelectorAll(
                '[data-automation-id="analysis_visual"]'
            ).forEach(v => {
                const r = v.getBoundingClientRect();
                const bottom = r.top + r.height + window.scrollY;
                if (bottom > max) max = bottom;
            });
            return Math.ceil(max);
        }"""
    )
    height = max(int(extent) + 60, 600)  # 60px footer margin
    page.screenshot(
        path=str(output_path),
        clip={"x": 0, "y": 0, "width": SCREENSHOT_VIEWPORT[0], "height": height},
    )


def _click_listbox_option_exact(page, text: str, timeout_ms: int) -> None:
    """Click a listbox option by exact innerText.

    Two concerns the naive Playwright path trips on:

    - **Listbox virtualization.** MUI's listbox keeps off-screen options
      out of the rendered tree until they scroll into view. The QS
      check_type listbox holds 14 options but only mounts ~10 at a
      time. We scroll the listbox container in chunks until the target
      gets mounted, then ``scrollIntoView`` to center it before click.
    - **Substring matching.** ``has_text="Ledger Drift"`` matches both
      "Ledger Drift" and "Sub-Ledger Drift" options, since the latter
      contains the former. Anchor with ``^…$`` regex.
    """
    found = page.evaluate(
        """async (text) => {
            const lb = document.querySelector('[role="listbox"]');
            if (!lb) return false;
            // Walk the listbox top-to-bottom in half-screen steps,
            // checking after each scroll whether MUI mounted the
            // option we want. scrollHeight + clientHeight are stable
            // because the virtualizer reserves total space up front.
            const sleep = (ms) => new Promise(r => setTimeout(r, ms));
            const findAndCenter = () => {
                const opts = lb.querySelectorAll('[role="option"]');
                for (const o of opts) {
                    if (o.innerText.trim() === text) {
                        o.scrollIntoView({block: 'center'});
                        return true;
                    }
                }
                return false;
            };
            if (findAndCenter()) return true;
            const step = Math.max(50, Math.floor(lb.clientHeight / 2));
            const maxTop = lb.scrollHeight - lb.clientHeight;
            for (let pos = 0; pos <= maxTop + step; pos += step) {
                lb.scrollTop = Math.min(pos, maxTop);
                await sleep(120);  // give the virtualizer time to mount
                if (findAndCenter()) return true;
            }
            return false;
        }""",
        text,
    )
    if not found:
        raise RuntimeError(f"Listbox option not in DOM after scroll: {text!r}")
    page.wait_for_timeout(150)
    page.locator(
        '[role="listbox"] [role="option"]',
        has_text=re.compile(f"^{re.escape(text)}$"),
    ).first.click(timeout=timeout_ms)


def _set_check_type_filter(page, value: str, timeout_ms: int) -> None:
    """Narrow the Check Type multi-select to exactly one value.

    Strategy: open the listbox, snapshot the currently-selected labels,
    select the target FIRST (if not already selected), then deselect
    every other label. Selecting first guarantees we never reach a
    zero-selected state — MUI sometimes auto-closes the popover when
    the last selection drops, which would strand the operation.
    """
    title = "Check Type"
    _open_control_dropdown(page, title, timeout_ms)

    selected_labels: list[str] = page.evaluate(
        """() => Array.from(
            document.querySelectorAll(
                '[role="listbox"] [role="option"][aria-selected="true"]'
            )
        ).map(o => o.innerText.trim())
         .filter(l => l && l !== 'Select all' && l !== 'All')"""
    )

    if value not in selected_labels:
        _click_listbox_option_exact(page, value, timeout_ms)
        page.wait_for_timeout(200)

    for label in selected_labels:
        if label == value:
            continue
        _click_listbox_option_exact(page, label, timeout_ms)
        page.wait_for_timeout(200)

    page.keyboard.press("Escape")
    page.wait_for_timeout(800)  # let visuals re-render after filter change


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
            current_filter: str | None = None
            for shot in shots:
                if shot["sheet"] != current_sheet:
                    click_sheet_tab(page, shot["sheet"], PAGE_TIMEOUT)
                    wait_for_visuals_rendered(page, PAGE_TIMEOUT)
                    current_sheet = shot["sheet"]

                if shot["filter_check_type"] != current_filter:
                    # Script only ever NARROWS the filter — no shot after
                    # a filtered one needs to clear back to unfiltered, so
                    # we don't handle the None → None ← value transition.
                    if shot["filter_check_type"] is not None:
                        _set_check_type_filter(
                            page, shot["filter_check_type"], PAGE_TIMEOUT,
                        )
                        # wait_for_visuals_rendered polls for the absence of
                        # any "loading" class — sometimes a stale chrome
                        # element keeps that signal pegged after a filter
                        # change. Fall back to a fixed settle interval so a
                        # transient loading-class blip doesn't fail the
                        # whole batch; the screenshot helper has its own
                        # title-label wait that will catch real failures.
                        try:
                            wait_for_visuals_rendered(page, PAGE_TIMEOUT)
                        except PWTimeoutError:
                            page.wait_for_timeout(5000)
                    current_filter = shot["filter_check_type"]

                shot_dir = OUTPUT_ROOT / shot["app"]
                shot_dir.mkdir(parents=True, exist_ok=True)
                output = shot_dir / f"{shot['filename']}.png"

                if shot["mode"] == "full_sheet":
                    _screenshot_full_sheet(page, output)
                else:
                    wait_for_visual_titles_present(
                        page, [shot["visual"]], VISUAL_TIMEOUT,
                    )
                    _screenshot_visual(
                        page, shot["visual"], shot["title_index"], output,
                    )
                print(f"    wrote {output.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
