"""Helpers for driving QuickSight dashboards in a Playwright browser.

Used by both the e2e test suite (``tests/e2e/test_*.py``) and
production CLI code (the screenshot pipeline that renders handbook
images against a deployed dashboard). Promoted out of
``tests/e2e/`` in M.1.10 so production no longer has to import
from ``tests/``.

The QuickSight identity region (us-east-1) is where embed URL
generation and user operations live, even when the dashboard
itself is deployed in another region.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


# Failure-screenshot output directory used by the e2e test suite's
# ``screenshot()`` helper. Resolved relative to the current working
# directory (pytest runs from repo root per pyproject.toml's
# ``testpaths = ["tests"]``); override via ``QS_E2E_SCREENSHOT_DIR``
# if you need a different sink. Production CLI screenshot capture
# uses an explicit ``output_dir`` arg to ``ScreenshotHarness`` and
# does NOT touch this constant.
SCREENSHOT_DIR = Path(
    os.environ.get("QS_E2E_SCREENSHOT_DIR", "tests/e2e/screenshots")
).resolve()


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


def selected_sheet_name(page) -> str:
    """Return the label of the currently active sheet tab, or empty string."""
    el = page.query_selector('[data-automation-id="selectedTab_sheet_name"]')
    return el.inner_text().strip() if el else ""


def wait_for_sheet_tab(page, name: str, timeout_ms: int) -> None:
    """Block until the active sheet tab's label equals ``name``.

    Used after a drill-down click to confirm navigation landed on the
    expected sheet. For deliberate tab switches use ``click_sheet_tab``
    which also waits for prior-sheet visuals to tear down.
    """
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector('[data-automation-id="selectedTab_sheet_name"]');
            return el && el.innerText.trim() === {name!r};
        }}""",
        timeout=timeout_ms,
    )


def wait_for_table_cells_present(page, timeout_ms: int) -> None:
    """Wait until at least one table cell (row 0, col 0) renders on the
    active sheet. Useful after tab switches before asserting on row content.
    """
    page.wait_for_selector(
        '[data-automation-id^="sn-table-cell-0-0"]',
        timeout=timeout_ms,
        state="attached",
    )


def first_table_cell_text(page, row: int, col: int) -> str:
    """Return the text of cell ``(row, col)`` in the first detail table on
    the active sheet. Targets the global ``sn-table-cell-{row}-{col}``
    automation id — use ``click_first_row_of_visual`` when multiple tables
    are on the same sheet.
    """
    cell = page.query_selector(f'[data-automation-id="sn-table-cell-{row}-{col}"]')
    assert cell is not None, f"No cell at row={row} col={col}"
    return cell.inner_text().strip()


def click_first_row_of_visual(
    page, visual_title: str, timeout_ms: int,
) -> None:
    """Click the first data cell (row 0, col 0) of the named visual.

    Tags the cell with a unique ``data-e2e-target`` attribute first so the
    click selector is unambiguous even when multiple tables share the same
    global ``sn-table-cell-0-0``. Clears the marker after so subsequent
    calls don't pick up a stale target.
    """
    scroll_visual_into_view(page, visual_title, timeout_ms)
    ok = page.evaluate(
        """(title) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (!t || t.innerText.trim() !== title) continue;
                const cell = v.querySelector('[data-automation-id="sn-table-cell-0-0"]');
                if (cell) {
                    cell.setAttribute('data-e2e-target', '1');
                    return true;
                }
            }
            return false;
        }""",
        visual_title,
    )
    assert ok, f"Could not find first cell of visual {visual_title!r}"
    page.click('[data-e2e-target="1"]', timeout=timeout_ms)
    page.evaluate(
        """() => document.querySelectorAll('[data-e2e-target]').forEach(
            e => e.removeAttribute('data-e2e-target')
        )"""
    )


def right_click_first_row_of_visual(
    page, visual_title: str, timeout_ms: int,
) -> None:
    """Right-click the first data cell of the named visual.

    Mirror of ``click_first_row_of_visual`` but dispatches a contextmenu
    event so QuickSight opens the visual's DATA_POINT_MENU drill list.
    Tags the cell with ``data-e2e-target`` first so the click target is
    unambiguous when multiple tables share the same global cell selectors.
    """
    scroll_visual_into_view(page, visual_title, timeout_ms)
    ok = page.evaluate(
        """(title) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (!t || t.innerText.trim() !== title) continue;
                const cell = v.querySelector('[data-automation-id="sn-table-cell-0-0"]');
                if (cell) {
                    cell.setAttribute('data-e2e-target', '1');
                    return true;
                }
            }
            return false;
        }""",
        visual_title,
    )
    assert ok, f"Could not find first cell of visual {visual_title!r}"
    page.locator('[data-e2e-target="1"]').first.click(
        button="right", timeout=timeout_ms,
    )
    page.wait_for_timeout(800)
    page.evaluate(
        """() => document.querySelectorAll('[data-e2e-target]').forEach(
            e => e.removeAttribute('data-e2e-target')
        )"""
    )


def click_context_menu_item(page, item_text: str, timeout_ms: int) -> None:
    """Click an entry in QuickSight's data-point context menu by visible text.

    QS's right-click menu mounts as a portal with each entry as a
    ``[role="menuitem"]``. The drill action's `Name` parameter from the
    Python builder appears verbatim as the menu item's text.
    """
    page.wait_for_selector(
        '[role="menu"] [role="menuitem"]',
        timeout=timeout_ms,
        state="visible",
    )
    page.locator(
        '[role="menu"] [role="menuitem"]', has_text=item_text,
    ).first.click(timeout=timeout_ms)


def sheet_control_titles(page) -> list[str]:
    """Return the visible titles of filter controls on the active sheet."""
    els = page.query_selector_all('[data-automation-id="sheet_control_name"]')
    return [e.inner_text().strip() for e in els if e.inner_text().strip()]


def wait_for_sheet_controls_present(page, timeout_ms: int) -> None:
    """Wait until at least one filter control is attached on the active sheet."""
    page.wait_for_selector(
        '[data-automation-id="sheet_control_name"]',
        timeout=timeout_ms,
        state="attached",
    )


def _retry_on_playwright_timeout(call, *, timeout_ms: int):
    """Run ``call()``; if Playwright's wait timed out, retry once with the
    same budget. Aurora Serverless v2 cold-start can stall the first SELECT
    for ~30s — the conftest warm-up fixture covers session start, but ad-hoc
    reruns and idle-between-sheets gaps can still hit a cold cluster. One
    retry survives that window without papering over genuine render bugs
    (which fail twice).
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        return call()
    except PlaywrightTimeoutError:
        return call()


def wait_for_visual_titles_present(
    page, expected_titles, timeout_ms: int,
) -> None:
    """Block until every title in ``expected_titles`` is rendered as an
    ``analysis_visual_title_label``. Visual containers attach before their
    title labels hydrate, so a simple container count isn't enough when the
    test asserts on specific titles.
    """
    titles_list = sorted(set(expected_titles))
    script = f"""() => {{
        const want = new Set({titles_list!r});
        const have = new Set(
            Array.from(document.querySelectorAll(
                '[data-automation-id="analysis_visual_title_label"]'
            )).map(el => el.innerText.trim()).filter(Boolean)
        );
        for (const t of want) {{ if (!have.has(t)) return false; }}
        return true;
    }}"""
    _retry_on_playwright_timeout(
        lambda: page.wait_for_function(script, timeout=timeout_ms),
        timeout_ms=timeout_ms,
    )


def wait_for_visuals_present(page, min_count: int, timeout_ms: int) -> int:
    """Wait until at least `min_count` visual containers are rendered.

    Returns the actual count observed.
    """
    script = f"""() => document.querySelectorAll('{VISUAL_SELECTOR}').length >= {min_count}"""
    _retry_on_playwright_timeout(
        lambda: page.wait_for_function(script, timeout=timeout_ms),
        timeout_ms=timeout_ms,
    )
    return len(page.query_selector_all(VISUAL_SELECTOR))


def get_visual_titles(page) -> list[str]:
    """Return the title text of every visual currently on the page."""
    titles = page.query_selector_all('[data-automation-id="analysis_visual_title_label"]')
    return [t.inner_text().strip() for t in titles if t.inner_text().strip()]


def scroll_visual_into_view(
    page, visual_title: str, timeout_ms: int, *, wait_for_cells: bool = True,
) -> None:
    """Scroll the visual with the given title to the viewport center.

    QuickSight virtualizes below-the-fold visuals — table cells are absent
    from the DOM until the visual is on screen. Browser tests that click
    into such a table must call this first, or the click-target selector
    will return nothing.

    Pass ``wait_for_cells=False`` for chart visuals (bar / pie / line),
    which don't render ``sn-table-cell-*`` markers and would otherwise
    time out.
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
    if not wait_for_cells:
        page.wait_for_timeout(800)
        return
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
    """Count distinct categorical entries (bars / slices) in a chart.

    QS renders charts to ``<canvas>``, so there are no DOM bars/slices to
    count directly. Two signals we can read:

    1. **Chart aria-label**: QS publishes a screen-reader description like
       "This is a chart with type Bar chart ... the data for X is Y, the
       data for Z is W, ...". Counting ``the data for`` occurrences yields
       the category count reliably (works for bar + line + pie).
    2. **Legend rows** (``data-automation-id="visual_legend_item_value"``):
       present on pie/donut charts and any chart with a legend.

    Returns the max of the two signals, or ``-1`` if the visual isn't found.
    Use to assert *change*, not exact value (chart may hide low-freq series).
    """
    return page.evaluate(
        """(title) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (!t || t.innerText.trim() !== title) continue;
                let aria = 0;
                for (const e of v.querySelectorAll('[aria-label]')) {
                    const lbl = e.getAttribute('aria-label') || '';
                    if (lbl.includes('the data for')) {
                        aria = Math.max(aria, (lbl.match(/the data for/g) || []).length);
                    }
                }
                const legend = v.querySelectorAll(
                    '[data-automation-id="visual_legend_item_value"]'
                ).length;
                return Math.max(aria, legend);
            }
            return -1;
        }""",
        visual_title,
    )


def wait_for_chart_categories_to_change(
    page, visual_title: str, before: int, timeout_ms: int,
) -> int:
    """Poll ``count_chart_categories`` until the value differs from ``before``.
    Returns the new count. Mirrors ``wait_for_table_rows_to_change``.
    """
    import time
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        current = count_chart_categories(page, visual_title)
        if current != before and current >= 0:
            return current
        page.wait_for_timeout(250)
    raise TimeoutError(
        f"{visual_title!r} chart category count never changed from {before} "
        f"within {timeout_ms}ms"
    )


def read_chart_categories(page, visual_title: str) -> list[str]:
    """Return the ordered category labels (bar names / slice names) of a
    chart visual, parsed from QS's screen-reader aria-label.

    QS aria-labels a chart container with "...the data for <CAT> is <N>,
    the data for <CAT> is <N>, ...". Parse that into an ordered list.
    Returns [] if the visual isn't found or has no aria description.
    """
    return page.evaluate(
        """(title) => {
            const visuals = document.querySelectorAll(
                '[data-automation-id="analysis_visual"]'
            );
            for (const v of visuals) {
                const t = v.querySelector(
                    '[data-automation-id="analysis_visual_title_label"]'
                );
                if (!t || t.innerText.trim() !== title) continue;
                let best = [];
                for (const e of v.querySelectorAll('[aria-label]')) {
                    const lbl = e.getAttribute('aria-label') || '';
                    if (!lbl.includes('the data for')) continue;
                    const matches = [
                        ...lbl.matchAll(/the data for ([^,]+?) is /g)
                    ].map(m => m[1].trim());
                    if (matches.length > best.length) best = matches;
                }
                return best;
            }
            return [];
        }""",
        visual_title,
    )


def click_chart_bar(
    page, visual_title: str, index: int, timeout_ms: int,
) -> None:
    """Select the bar at ``index`` in a bar-chart visual via keyboard nav.

    QS renders charts to ``<canvas>``, so there's no DOM bar to click.
    The keyboard-accessible path (bar charts only — pie/donut don't
    expose it):

    1. Click the visual's container to give it focus.
    2. Tab 5 times to move focus into the inner bar group.
    3. Enter to highlight a bar.
    4. Right-arrow ``index`` times to cycle to the target bar.
    5. Enter to select (fires the same-sheet filter action).

    The visual must already be rendered and on-screen. Category order
    matches ``read_chart_categories``.
    """
    card = page.locator(
        f'[data-automation-id="analysis_visual"]:has('
        f'[data-automation-id="analysis_visual_title_label"]:text-is("{visual_title}"))'
    ).first
    card.wait_for(state="visible", timeout=timeout_ms)
    box = card.bounding_box()
    assert box, f"No bounding box for {visual_title!r}"
    # Click whitespace inside the card (just under the title) to focus
    # the visual without landing on the canvas / title / axis labels.
    page.mouse.click(
        box["x"] + box["width"] / 2,
        box["y"] + 30,
    )
    page.wait_for_timeout(300)
    for _ in range(5):
        page.keyboard.press("Tab")
        page.wait_for_timeout(100)
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    # Horizontal bar charts navigate with ArrowDown; try both to be
    # orientation-agnostic (extra presses on the wrong axis no-op).
    for _ in range(index):
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(120)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(120)
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)


def read_visual_column_values(
    page, visual_title: str, col_index: int,
) -> list[str]:
    """Return the text of every visible cell in column ``col_index`` within
    the table visual whose title matches ``visual_title``.

    Scoped to the specific visual (unlike the global ``sn-table-cell-{r}-{c}``
    lookup) so sibling tables can't contaminate the result. Caller is
    responsible for ensuring the visual is hydrated (use
    ``scroll_visual_into_view`` or ``count_table_total_rows`` first if the
    table is below-the-fold or paginated beyond the ~10-row viewport).
    """
    return page.evaluate(
        """({title, col}) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (!t || t.innerText.trim() !== title) continue;
                const out = [];
                v.querySelectorAll(
                    `[data-automation-id^="sn-table-cell-"]`
                ).forEach(c => {
                    const m = c.getAttribute('data-automation-id').match(
                        /sn-table-cell-(\\d+)-(\\d+)/
                    );
                    if (m && parseInt(m[2]) === col) {
                        out.push({row: parseInt(m[1]), text: c.innerText.trim()});
                    }
                });
                out.sort((a, b) => a.row - b.row);
                return out.map(o => o.text);
            }
            return null;
        }""",
        {"title": visual_title, "col": col_index},
    ) or []


def read_kpi_value(page, visual_title: str) -> str:
    """Return the displayed big-number text of a KPI visual.

    QS renders the value inside ``.visual-x-center`` (the actual text node).
    The ``kpi-display-value`` automation-id wraps the container but its
    innerText sometimes includes the comparison label — prefer the center
    node and fall back to the automation-id if unavailable.

    Raises ``AssertionError`` if the visual isn't found or has no value.
    """
    value = page.evaluate(
        """(title) => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (!t || t.innerText.trim() !== title) continue;
                const center = v.querySelector('.visual-x-center');
                if (center && center.innerText.trim()) return center.innerText.trim();
                const kpi = v.querySelector('[data-automation-id="kpi-display-value"]');
                if (kpi && kpi.innerText.trim()) return kpi.innerText.trim();
                return null;
            }
            return null;
        }""",
        visual_title,
    )
    assert value is not None, f"No KPI value found for {visual_title!r}"
    return value


def parse_kpi_number(text: str) -> float:
    """Strip ``$``, ``%``, ``,`` and ``K``/``M``/``B`` suffixes; return float.

    Handles QS's compact-number formatting: ``$1.2K`` -> 1200.0,
    ``45.3M`` -> 45_300_000.0. Unsuffixed strings parse straight.
    """
    s = text.strip().replace("$", "").replace(",", "").replace("%", "").strip()
    multiplier = 1.0
    if s and s[-1] in "KMB":
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9}[s[-1]]
        s = s[:-1]
    return float(s) * multiplier


def wait_for_kpi_text_nonempty(
    page, visual_title: str, timeout_ms: int,
) -> str:
    """Poll ``read_kpi_value`` until the KPI is readable, returning its
    text. Useful pre-filter when the KPI hydrates after the visual
    mounts but before the test wants to baseline its value.
    """
    import time
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        try:
            value = read_kpi_value(page, visual_title)
            if value:
                return value
        except AssertionError:
            pass
        page.wait_for_timeout(250)
    raise TimeoutError(
        f"{visual_title!r} KPI never became readable within {timeout_ms}ms"
    )


def wait_for_kpi_value_to_change(
    page, visual_title: str, before: str, timeout_ms: int,
) -> str:
    """Poll ``read_kpi_value`` until the displayed text differs from ``before``.
    Returns the new value. Raw string comparison — caller parses if needed.
    """
    import time
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        current = read_kpi_value(page, visual_title)
        if current != before:
            return current
        page.wait_for_timeout(250)
    raise TimeoutError(
        f"{visual_title!r} KPI value never changed from {before!r} "
        f"within {timeout_ms}ms"
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

    For parameter-driven date pickers (``ParameterDateTimePicker``,
    not ``FilterDateTimePicker.type=DATE_RANGE``), use
    :func:`set_parameter_datetime_value` instead — those render as
    separate sheet controls each with their own scoped DOM, not a
    shared 0-and-1-indexed range widget.
    """
    for picker_index, value in zip(picker_indices, (start, end)):
        selector = f'[data-automation-id="date_picker_{picker_index}"]'
        page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
        page.fill(selector, value)
        page.press(selector, "Enter")


def set_parameter_datetime_value(
    page, control_title: str, value: str, timeout_ms: int,
) -> None:
    """Fill a single ``ParameterDateTimePicker`` control by its title.

    Each ParameterDateTimePicker on a sheet renders as its own
    ``sheet_control`` card scoped by ``data-automation-context`` to
    the control's title. The date input lives at
    ``data-automation-id="date_picker_0"`` *within* that card. Targeting
    by title avoids the cross-control collision (each card has its own
    locally-indexed picker).

    ``value`` uses QuickSight's accepted text format (``YYYY/MM/DD``).
    """
    card_selector = (
        f'[data-automation-id="sheet_control"]'
        f'[data-automation-context="{control_title}"]'
    )
    picker_selector = (
        f'{card_selector} [data-automation-id="date_picker_0"]'
    )
    page.wait_for_selector(picker_selector, timeout=timeout_ms, state="visible")
    page.fill(picker_selector, value)
    page.press(picker_selector, "Enter")


def set_slider_range(
    page, control_title: str, low: int | None, high: int | None,
    timeout_ms: int,
) -> None:
    """Set a RANGE FilterSliderControl's min/max via its backing text inputs.

    QS renders each range slider with two MUI text inputs
    (``sheet_control_range_slider_min`` / ``_max``) wired to React state.
    Dragging the thumbs is fragile in Playwright, but filling the inputs
    and blurring them commits the value reliably. Pass ``None`` to leave
    a bound untouched.
    """
    card_selector = (
        f'[data-automation-id="sheet_control"]'
        f'[data-automation-context="{control_title}"]'
    )
    page.wait_for_selector(card_selector, timeout=timeout_ms, state="visible")
    for bound, value in (("min", low), ("max", high)):
        if value is None:
            continue
        selector = (
            f'{card_selector} '
            f'[data-automation-id="sheet_control_range_slider_{bound}"]'
        )
        loc = page.locator(selector).first
        loc.click(timeout=timeout_ms)
        loc.fill(str(value), timeout=timeout_ms)
        loc.press("Enter", timeout=timeout_ms)


# MUI v4 renders some FilterControl options inside ``[role="listbox"]``
# (most sheet controls) and others directly in the value-menu popover
# (Show-Only-X single-selects on Settlements/Payments). Match both.
_OPTION_SELECTOR = (
    '[role="listbox"] [role="option"], '
    '[data-automation-id="sheet_control_value-menu"] [role="option"]'
)
_SELECTED_OPTION_SELECTOR = (
    '[role="listbox"] [role="option"][aria-selected="true"], '
    '[data-automation-id="sheet_control_value-menu"] [role="option"][aria-selected="true"]'
)


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
    # MUI mounts the listbox in a portal; aria-haspopup="listbox" expands.
    # The first click sometimes no-ops if the sheet just mounted and the
    # combobox's onClick handler hasn't attached — retry until the listbox
    # appears or timeout.
    value_selector = (
        f'{card_selector} [data-automation-id="sheet_control_value"]'
    )
    page.locator(value_selector).first.click(timeout=timeout_ms)
    # MUI v4 sometimes renders options under role="listbox" inside the menu
    # popover, but some control instances skip the listbox role and put
    # options directly in the popover. Match either shape, but scope to
    # the just-opened control's popover so other (stale) popovers don't
    # pollute the option set.
    popover_selector = (
        f'[data-automation-id="sheet_control_value-menu"]'
        f'[data-automation-context="{control_title}"]'
    )
    page.wait_for_selector(
        f'{popover_selector} [role="option"], [role="listbox"] [role="option"]',
        timeout=timeout_ms, state="visible",
    )


def set_dropdown_value(
    page, control_title: str, value: str, timeout_ms: int,
) -> None:
    """Pick a single value from a SINGLE_SELECT FilterControl by title.

    Opens the dropdown for ``control_title`` and clicks the option whose
    text equals ``value``. Use ``clear_dropdown`` to reset to "All".
    Dismisses the popover with Escape so subsequent visual interactions
    aren't blocked by the listbox overlay.
    """
    _open_control_dropdown(page, control_title, timeout_ms)
    page.locator(
        _OPTION_SELECTOR, has_text=value,
    ).first.click(timeout=timeout_ms)
    page.keyboard.press("Escape")


def set_multi_select_values(
    page, control_title: str, values: list[str], timeout_ms: int,
) -> None:
    """Pick one or more values from a MULTI_SELECT FilterControl by title.

    Deselects any currently-checked options first (via the option's
    aria-selected state), then ticks only the requested values. Commits
    by pressing Escape to dismiss the popover.
    """
    _open_control_dropdown(page, control_title, timeout_ms)
    # MULTI_SELECT controls always render in ``[role="listbox"]``;
    # restrict to that path to avoid duplicate matches from the broader
    # popover selector used for SINGLE_SELECT Show-Only-X controls.
    mselect = '[role="listbox"] [role="option"]'
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
        page.locator(mselect, has_text=label).first.click(timeout=timeout_ms)
    for value in targets:
        page.locator(mselect, has_text=value).first.click(timeout=timeout_ms)
    page.keyboard.press("Escape")


def read_dropdown_options(
    page, control_title: str, timeout_ms: int,
) -> list[str]:
    """Return the data-value option labels in a FilterControl dropdown.

    Opens the dropdown for ``control_title``, reads every
    ``[role="option"]`` label, dismisses the popover, and returns the
    list with sentinel entries filtered out (``"Select all"``, ``"All"``,
    blanks). Used by data-agnostic e2e tests that need to pick a
    valid value from the dropdown without hardcoding what the values
    are — e.g., "pick the first selectable value to narrow the table."
    """
    _open_control_dropdown(page, control_title, timeout_ms)
    labels = page.evaluate(
        """() => Array.from(
            document.querySelectorAll('[role="listbox"] [role="option"]')
        ).map(o => o.innerText.trim())"""
    )
    page.keyboard.press("Escape")
    return [
        label for label in labels
        if label and label not in ("Select all", "All")
    ]


def clear_dropdown(page, control_title: str, timeout_ms: int) -> None:
    """Reset a FilterControl to its "all values" default.

    Opens the dropdown and clicks the "Select all" / "All" entry. Works
    for both SINGLE_SELECT and MULTI_SELECT controls — QuickSight uses
    the same listbox markup for both.
    """
    _open_control_dropdown(page, control_title, timeout_ms)
    options = page.locator(_OPTION_SELECTOR)
    for label in ("Select all", "All"):
        match = options.filter(has_text=label).first
        if match.count() > 0:
            match.click(timeout=timeout_ms)
            page.keyboard.press("Escape")
            return
    # SINGLE_SELECT: no listbox clear-all entry. Close popover and open
    # the control's options menu (``⋯``), then click its "Clear" item.
    page.keyboard.press("Escape")
    card_selector = (
        f'[data-automation-id="sheet_control"]'
        f'[data-automation-context="{control_title}"]'
    )
    page.locator(
        f'{card_selector} [data-automation-id="sheet_control_menu_button"]'
    ).first.click(timeout=timeout_ms)
    page.wait_for_selector(
        '[role="menu"] [role="menuitem"]', timeout=timeout_ms, state="visible",
    )
    items = page.locator('[role="menu"] [role="menuitem"]')
    for label in ("Clear selection", "Clear", "Reset"):
        match = items.filter(has_text=label).first
        if match.count() > 0:
            match.click(timeout=timeout_ms)
            return
    raise AssertionError(
        f"No Clear/Reset item in options menu for {control_title!r}"
    )


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
