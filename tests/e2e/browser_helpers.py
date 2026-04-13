"""Helpers for browser-based e2e tests against deployed dashboards.

The QuickSight identity region (us-east-1) is where embed URL generation
and user operations live, even when the dashboard itself is in another region.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCREENSHOT_DIR = Path(__file__).parent / "screenshots"


def get_user_arn() -> str:
    """Return the QuickSight user ARN to embed for.

    Set QS_E2E_USER_ARN to override. Defaults to the root-linked IAM
    default-namespace user already validated for this account.
    """
    arn = os.environ.get("QS_E2E_USER_ARN")
    if arn:
        return arn
    # Default for this project — see PLAN.md Resolved Questions #1
    return "arn:aws:quicksight:us-east-1:470656905821:user/default/470656905821"


def generate_dashboard_embed_url(
    qs_identity_client,
    account_id: str,
    dashboard_id: str,
    user_arn: str | None = None,
    session_lifetime_minutes: int = 60,
) -> str:
    """Generate a pre-authenticated embed URL for a dashboard.

    Uses the identity-region client (us-east-1) regardless of where the
    dashboard is deployed.
    """
    resp = qs_identity_client.generate_embed_url_for_registered_user(
        AwsAccountId=account_id,
        SessionLifetimeInMinutes=session_lifetime_minutes,
        UserArn=user_arn or get_user_arn(),
        ExperienceConfiguration={
            "Dashboard": {"InitialDashboardId": dashboard_id},
        },
    )
    return resp["EmbedUrl"]


@contextmanager
def webkit_page(headless: bool = True, viewport: tuple[int, int] = (1600, 1000)) -> Iterator:
    """Yield a Playwright WebKit page; tears down browser on exit."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.webkit.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
        )
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


def wait_for_dashboard_loaded(page, timeout_ms: int) -> None:
    """Wait for the QuickSight dashboard chrome (sheet tabs) to appear.

    networkidle alone fires before visuals render; wait for the sheet
    tab strip as a stronger signal that the dashboard skeleton is up.
    """
    # networkidle alone fires before tabs appear; we then poll for the
    # sheet tab list, which is the strongest signal the dashboard chrome
    # is hydrated. Use the same timeout budget for each phase.
    page.wait_for_load_state("networkidle", timeout=timeout_ms)
    page.wait_for_selector('[role="tab"]', timeout=timeout_ms, state="attached")


def wait_for_visuals_rendered(page, timeout_ms: int, min_visuals: int = 1) -> None:
    """Wait for visual containers to finish their loading state.

    QuickSight visuals show a loading skeleton while data fetches. We
    poll for the absence of skeleton/loading classes within visual cells.
    """
    page.wait_for_function(
        f"""() => {{
            const cells = document.querySelectorAll('[data-automation-id*="visual"], [class*="visual-container"]');
            if (cells.length < {min_visuals}) return false;
            // No element should still be in a loading state
            const loading = document.querySelectorAll('[class*="loading"], [class*="Loading"], [aria-busy="true"]');
            return loading.length === 0;
        }}""",
        timeout=timeout_ms,
    )


def get_sheet_tab_names(page) -> list[str]:
    """Return the visible sheet tab labels in order."""
    tabs = page.query_selector_all('[role="tab"]')
    return [t.inner_text().strip() for t in tabs if t.inner_text().strip()]


VISUAL_SELECTOR = '[data-automation-id="analysis_visual"]'


def click_sheet_tab(page, name: str, timeout_ms: int) -> None:
    """Activate a sheet tab by its visible name and wait for the switch.

    QuickSight tears down the prior sheet's visuals on switch. We
    snapshot the current visual titles before the click, then wait
    for them to be replaced — otherwise a wait that just checks
    "≥ N visuals present" can be satisfied by the prior sheet.
    """
    # No-op if we're already on the target sheet
    selected_el = page.query_selector('[data-automation-id="selectedTab_sheet_name"]')
    if selected_el and selected_el.inner_text().strip() == name:
        return
    prior_titles = sorted(set(get_visual_titles(page)))
    tab = page.locator('[role="tab"]', has_text=name).first
    tab.click(timeout=timeout_ms)
    # 1. Selected-tab name indicator updates to the target sheet
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-automation-id="selectedTab_sheet_name"]');
            return el && el.innerText.trim() === {name!r};
        }}""",
        timeout=timeout_ms,
    )
    # 2. The prior sheet's visual titles are no longer in the DOM
    if prior_titles:
        page.wait_for_function(
            f"""() => {{
                const prior = new Set({prior_titles!r});
                const labels = document.querySelectorAll('[data-automation-id="analysis_visual_title_label"]');
                for (const l of labels) {{
                    if (prior.has(l.innerText.trim())) return false;
                }}
                return true;
            }}""",
            timeout=timeout_ms,
        )


def wait_for_visuals_present(page, min_count: int, timeout_ms: int) -> int:
    """Wait until at least `min_count` visual containers are rendered.

    Returns the actual count observed.
    """
    page.wait_for_function(
        f"""() => document.querySelectorAll('{VISUAL_SELECTOR}').length >= {min_count}""",
        timeout=timeout_ms,
    )
    return len(page.query_selector_all(VISUAL_SELECTOR))


def get_visual_titles(page) -> list[str]:
    """Return the title text of every visual currently on the page."""
    titles = page.query_selector_all('[data-automation-id="analysis_visual_title_label"]')
    return [t.inner_text().strip() for t in titles if t.inner_text().strip()]


def scroll_visual_into_view(page, visual_title: str, timeout_ms: int) -> None:
    """Scroll the visual with the given title to the viewport center and
    wait for its first table cell to hydrate.

    QuickSight virtualizes below-the-fold visuals — table cells are absent
    from the DOM until the visual is on screen. Browser tests that click
    into such a table must call this first, or the click-target selector
    will return nothing.
    """
    page.evaluate(
        """(title) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (t && t.innerText.trim() === title) {
                    v.scrollIntoView({block: 'center'});
                    return;
                }
            }
        }""",
        visual_title,
    )
    page.wait_for_function(
        """(title) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (!t || t.innerText.trim() !== title) continue;
                return v.querySelector('[data-automation-id="sn-table-cell-0-0"]') !== null;
            }
            return false;
        }""",
        arg=visual_title,
        timeout=timeout_ms,
    )


def screenshot(page, name: str) -> Path:
    """Save a screenshot under tests/e2e/screenshots/."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path
