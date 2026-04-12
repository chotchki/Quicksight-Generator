"""Browser tests: filter controls actually filter the underlying visuals.

We only validate the date-range filter on the Sales Overview sheet —
it's the most user-facing filter and exercises the same parameter /
filter-group machinery as the rest.
"""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_sheet_tab,
    generate_dashboard_embed_url,
    screenshot,
    wait_for_dashboard_loaded,
    wait_for_visuals_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture
def embed_url(qs_client, account_id, dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=dashboard_id,
    )


def _sales_detail_row_count(page) -> int:
    """Count rows in the Sales Detail table on the active sheet."""
    return page.evaluate(
        """() => {
            const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
            for (const v of visuals) {
                const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                if (!t || t.innerText.trim() !== 'Sales Detail') continue;
                const rows = new Set();
                v.querySelectorAll('[data-automation-id^="sn-table-cell-"]').forEach(c => {
                    const m = c.getAttribute('data-automation-id').match(/sn-table-cell-(\\d+)-/);
                    if (m) rows.add(m[1]);
                });
                return rows.size;
            }
            return -1;
        }"""
    )


def _set_date(page, picker_index: int, value: str, timeout_ms: int) -> None:
    """Fill one of the date-range pickers and commit with Enter."""
    selector = f'[data-automation-id="date_picker_{picker_index}"]'
    page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
    page.fill(selector, value)
    page.press(selector, "Enter")


def test_date_range_filter_narrows_sales_detail(embed_url, page_timeout):
    """Setting the date range to a future window should empty (or
    significantly reduce) the Sales Detail table on Sales Overview."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        # Sales Overview is the default sheet; ensure visuals + table cells
        wait_for_visuals_present(page, min_count=5, timeout_ms=page_timeout)
        page.wait_for_selector(
            '[data-automation-id^="sn-table-cell-0-0"]',
            timeout=page_timeout,
            state="attached",
        )

        before = _sales_detail_row_count(page)
        assert before > 1, (
            f"Sales Detail should have multiple rows before filtering, got {before}"
        )

        # Push the date range fully into the future — no demo sale falls in 2099
        _set_date(page, picker_index=0, value="2099/01/01", timeout_ms=page_timeout)
        _set_date(page, picker_index=1, value="2099/12/31", timeout_ms=page_timeout)

        # Filter application is async; poll for row count to drop
        page.wait_for_function(
            f"""() => {{
                const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
                for (const v of visuals) {{
                    const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                    if (!t || t.innerText.trim() !== 'Sales Detail') continue;
                    const rows = new Set();
                    v.querySelectorAll('[data-automation-id^="sn-table-cell-"]').forEach(c => {{
                        const m = c.getAttribute('data-automation-id').match(/sn-table-cell-(\\d+)-/);
                        if (m) rows.add(m[1]);
                    }});
                    return rows.size < {before};
                }}
                return false;
            }}""",
            timeout=page_timeout,
        )

        after = _sales_detail_row_count(page)
        screenshot(page, "filter_date_range_future")
        assert after < before, (
            f"Sales Detail should filter to < {before} rows after future date range, got {after}"
        )
