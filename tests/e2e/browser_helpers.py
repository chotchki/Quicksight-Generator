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


def count_table_rows(page, visual_title: str) -> int:
    """Count distinct table rows in the visual whose title matches.

    Returns -1 if no visual with that title is on the page. Returns 0 if
    the visual is present but empty. Caller is responsible for ensuring
    the visual is hydrated (use ``scroll_visual_into_view`` for
    below-the-fold tables).
    """
    return page.evaluate(
        """(title) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (!t || t.innerText.trim() !== title) continue;
                const rows = new Set();
                v.querySelectorAll('[data-automation-id^="sn-table-cell-"]').forEach(c => {
                    const m = c.getAttribute('data-automation-id').match(/sn-table-cell-(\\d+)-/);
                    if (m) rows.add(m[1]);
                });
                return rows.size;
            }
            return -1;
        }""",
        visual_title,
    )


def count_table_total_rows(page, visual_title: str, timeout_ms: int) -> int:
    """Return the full (post-filter) row count of a QS table visual.

    QS tables virtualize — ``count_table_rows`` only sees the ~10 rows
    currently mounted in the DOM. For filter-narrowing assertions where
    both pre and post totals exceed the viewport, DOM counts stay flat
    and the assertion silently passes. This helper:

    1. Focuses the visual (click title) to reveal ``simplePagedDisplayNav_*``.
    2. Sets page size to 10000 so all rows fit on one page.
    3. Scrolls the inner ``.grid-container`` to the bottom, tracking the
       highest ``sn-table-cell-N-*`` index seen.

    Use this helper when the table's row count may exceed ~10 and you need
    a precise total. Prefer ``count_table_rows`` when you already know the
    table fits in the viewport — it's much faster.

    Raises a timeout if the pagination controls never appear (i.e. the
    visual isn't actually a paged table).
    """
    # Scroll the visual into view. Use scroll_visual_into_view when the
    # table has data (cells present); otherwise fall back to a plain
    # element.scrollIntoView, which still positions QS's inner scroll
    # container correctly even when cells haven't mounted.
    try:
        scroll_visual_into_view(page, visual_title, timeout_ms=5000)
    except Exception:
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
        page.wait_for_timeout(2000)
    # Focus the visual via a JS click dispatched directly on the title
    # element. Playwright's locator.click() runs actionability checks that
    # trigger auto-scroll within QS's re-rendering content and race against
    # "element detached" errors — a raw DOM click avoids all of that and
    # still reliably reveals simplePagedDisplayNav_*.
    clicked = page.evaluate(
        """(title) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (t && t.innerText.trim() === title) {
                    t.click();
                    return true;
                }
            }
            return false;
        }""",
        visual_title,
    )
    assert clicked, f"No visual with title {visual_title!r}"
    # Brief settle — QS takes a beat to mount the paging controls after focus.
    page.wait_for_timeout(1500)
    # If the pagination controls mounted (focus took), bump page size to
    # 10000 so every row lives on one page. On repeat calls the controls
    # often don't re-mount (focus already consumed, or lost to a prior
    # filter interaction) — skip the resize and rely on the page size
    # set by the first successful call persisting through the session.
    try:
        page.wait_for_selector(
            '[data-automation-id="simplePagedDisplayNav_dropdown_pageSize"]',
            timeout=3000, state="visible",
        )
        page.locator(
            '[data-automation-id="simplePagedDisplayNav_dropdown_pageSize"]'
        ).first.click()
        page.wait_for_selector(
            '[data-automation-id="simplePagedDisplayNav_menuItem_pageSize_10000"]',
            timeout=timeout_ms, state="visible",
        )
        page.locator(
            '[data-automation-id="simplePagedDisplayNav_menuItem_pageSize_10000"]'
        ).first.click()
        page.wait_for_timeout(500)
    except Exception:
        pass

    return page.evaluate(
        """async (title) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            let target = null;
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (t && t.innerText.trim() === title) { target = v; break; }
            }
            if (!target) return -1;
            const container = target.querySelector('.grid-container');
            if (!container) return -2;
            const getMaxRow = () => {
                let max = -1;
                target.querySelectorAll('[data-automation-id^="sn-table-cell-"]').forEach(c => {
                    const m = c.getAttribute('data-automation-id').match(/sn-table-cell-(\\d+)-/);
                    if (m) {
                        const n = parseInt(m[1], 10);
                        if (n > max) max = n;
                    }
                });
                return max;
            };
            let max = getMaxRow();
            let stable = 0;
            for (let step = 0; step < 500; step++) {
                const prev = max;
                container.scrollTop = container.scrollTop + 400;
                await new Promise(r => setTimeout(r, 120));
                const now = getMaxRow();
                if (now > max) max = now;
                if (container.scrollTop + container.clientHeight >= container.scrollHeight - 1) {
                    await new Promise(r => setTimeout(r, 400));
                    max = Math.max(max, getMaxRow());
                    break;
                }
                if (now === prev) { stable++; if (stable > 3) break; }
                else { stable = 0; }
            }
            return max < 0 ? 0 : max + 1;
        }""",
        visual_title,
    )


def wait_for_table_total_rows_to_change(
    page, visual_title: str, before: int, timeout_ms: int,
) -> int:
    """Poll a table's total row count (via ``count_table_total_rows``) until
    it differs from ``before``. Returns the new total.

    Unlike ``wait_for_table_rows_to_change``, this compares *post-filter*
    totals, not DOM-visible rows — use it when the table may exceed the
    virtualization window.
    """
    import time
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        current = count_table_total_rows(page, visual_title, timeout_ms=timeout_ms)
        if current != before:
            return current
        page.wait_for_timeout(500)
    raise TimeoutError(
        f"{visual_title!r} total row count never changed from {before} "
        f"within {timeout_ms}ms"
    )


def count_chart_categories(page, visual_title: str) -> int:
    """Count distinct categorical entries (bars / slices / legend rows) in
    a chart visual. Heuristic: counts SVG ``<g class*="bar">`` /
    ``<path class*="slice">`` plus legend swatches and returns the max.

    QS doesn't expose a single "category count" automation ID, so this is
    intentionally lenient; use it to assert *change*, not exact value.
    """
    return page.evaluate(
        """(title) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (!t || t.innerText.trim() !== title) continue;
                const bars = v.querySelectorAll('g[class*="bar"], path[class*="slice"], rect[class*="bar"]').length;
                const legend = v.querySelectorAll('[class*="legend"] [class*="item"], [data-automation-id*="legend_item"]').length;
                return Math.max(bars, legend);
            }
            return -1;
        }""",
        visual_title,
    )


def wait_for_table_rows_to_change(
    page, visual_title: str, before: int, timeout_ms: int,
) -> int:
    """Poll a table visual's row count until it differs from ``before``.

    Returns the new row count. Raises a Playwright timeout if the count
    never changes. Use this after triggering a filter / drill action so
    the test doesn't sleep blindly.
    """
    page.wait_for_function(
        """({title, before}) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (!t || t.innerText.trim() !== title) continue;
                const rows = new Set();
                v.querySelectorAll('[data-automation-id^="sn-table-cell-"]').forEach(c => {
                    const m = c.getAttribute('data-automation-id').match(/sn-table-cell-(\\d+)-/);
                    if (m) rows.add(m[1]);
                });
                return rows.size !== before;
            }
            return false;
        }""",
        arg={"title": visual_title, "before": before},
        timeout=timeout_ms,
    )
    return count_table_rows(page, visual_title)


def set_date_range(
    page, start: str, end: str, timeout_ms: int,
    picker_indices: tuple[int, int] = (0, 1),
) -> None:
    """Fill the two date-range pickers and commit each with Enter.

    ``start`` / ``end`` use QuickSight's accepted text format (``YYYY/MM/DD``).
    ``picker_indices`` defaults to (0, 1) — the first date-range control on
    the active sheet. Override when a sheet has multiple ranges.
    """
    for picker_index, value in zip(picker_indices, (start, end)):
        selector = f'[data-automation-id="date_picker_{picker_index}"]'
        page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
        page.fill(selector, value)
        page.press(selector, "Enter")


def _open_control_dropdown(page, control_title: str, timeout_ms: int) -> None:
    """Open the FilterControl popover for the named sheet control.

    QuickSight renders each control as
    ``[data-automation-id="sheet_control"][data-automation-context="<title>"]``
    with the value picker at ``sheet_control_value`` (a Material-UI Select
    combobox). Opens the popover and waits for the listbox to be visible.
    """
    card_selector = (
        f'[data-automation-id="sheet_control"]'
        f'[data-automation-context="{control_title}"]'
    )
    page.wait_for_selector(card_selector, timeout=timeout_ms, state="visible")
    page.locator(
        f'{card_selector} [data-automation-id="sheet_control_value"]'
    ).first.click(timeout=timeout_ms)
    # MUI mounts the listbox in a portal; aria-haspopup="listbox" expands.
    page.wait_for_selector(
        '[role="listbox"] [role="option"]', timeout=timeout_ms, state="visible",
    )


def set_dropdown_value(
    page, control_title: str, value: str, timeout_ms: int,
) -> None:
    """Pick a single value from a SINGLE_SELECT FilterControl by title.

    Opens the dropdown for ``control_title`` and clicks the option whose
    text equals ``value``. Use ``clear_dropdown`` to reset to "All".
    """
    _open_control_dropdown(page, control_title, timeout_ms)
    page.locator('[role="listbox"] [role="option"]', has_text=value).first.click(
        timeout=timeout_ms,
    )


def set_multi_select_values(
    page, control_title: str, values: list[str], timeout_ms: int,
) -> None:
    """Pick one or more values from a MULTI_SELECT FilterControl by title.

    Deselects any currently-checked options first (via the option's
    aria-selected state), then ticks only the requested values. Commits
    by pressing Escape to dismiss the popover.
    """
    _open_control_dropdown(page, control_title, timeout_ms)
    # Snapshot the labels of currently-selected options so we can deselect
    # by label (clicking by index is racy — the listbox reorders as items
    # toggle).
    selected_labels = page.evaluate(
        """() => Array.from(
            document.querySelectorAll(
                '[role="listbox"] [role="option"][aria-selected="true"]'
            )
        ).map(o => o.innerText.trim())"""
    )
    targets = set(values)
    for label in selected_labels:
        if label in targets:
            targets.discard(label)
            continue
        page.locator(
            '[role="listbox"] [role="option"]', has_text=label,
        ).first.click(timeout=timeout_ms)
    for value in targets:
        page.locator(
            '[role="listbox"] [role="option"]', has_text=value,
        ).first.click(timeout=timeout_ms)
    page.keyboard.press("Escape")


def clear_dropdown(page, control_title: str, timeout_ms: int) -> None:
    """Reset a FilterControl to its "all values" default.

    Opens the dropdown and clicks the "Select all" / "All" entry. Works
    for both SINGLE_SELECT and MULTI_SELECT controls — QuickSight uses
    the same listbox markup for both.
    """
    _open_control_dropdown(page, control_title, timeout_ms)
    # QS labels the clear-all entry "Select all" on multi-select and
    # "All" on single-select; try the multi-select label first.
    options = page.locator('[role="listbox"] [role="option"]')
    for label in ("Select all", "All"):
        match = options.filter(has_text=label).first
        if match.count() > 0:
            match.click(timeout=timeout_ms)
            page.keyboard.press("Escape")
            return
    # Fallback: deselect every selected entry one by one.
    selected = page.locator(
        '[role="listbox"] [role="option"][aria-selected="true"]'
    )
    for i in range(selected.count()):
        selected.nth(i).click(timeout=timeout_ms)
    page.keyboard.press("Escape")


def screenshot(page, name: str, subdir: str | None = None) -> Path:
    """Save a screenshot under tests/e2e/screenshots/[subdir/].

    Pass ``subdir`` to namespace outputs per-app (e.g. ``"payment_recon"`` or
    ``"account_recon"``) so the two apps' screenshots don't overwrite each
    other when they happen to share a test name.
    """
    target_dir = SCREENSHOT_DIR / subdir if subdir else SCREENSHOT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path
