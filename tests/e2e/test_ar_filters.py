"""Browser tests: AR filter controls narrow the underlying visuals.

We verify the shared date-range filter by pushing it to a future window
and confirming the Transaction Detail table empties out. The date-range
filter is bound to ``ar_transactions.posted_at`` with ALL_DATASETS
cross-dataset scoping, so the Transactions sheet is where the filter
binding is most direct — a simpler target than the balance-drift views,
which key off ``balance_date`` and rely on column-name matching.
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
def embed_url(qs_client, account_id, ar_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=ar_dashboard_id,
    )


def _table_row_count(page, visual_title: str) -> int:
    """Count distinct table rows in the visual with this title."""
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


def _set_date(page, picker_index: int, value: str, timeout_ms: int) -> None:
    selector = f'[data-automation-id="date_picker_{picker_index}"]'
    page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
    page.fill(selector, value)
    page.press(selector, "Enter")


def test_date_range_filter_narrows_transactions(embed_url, page_timeout):
    """Setting the date range to a future window should empty (or
    significantly reduce) the Transaction Detail table."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Transactions", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=5, timeout_ms=page_timeout)
        page.wait_for_selector(
            '[data-automation-id^="sn-table-cell-0-0"]',
            timeout=page_timeout,
            state="attached",
        )

        before = _table_row_count(page, "Transaction Detail")
        assert before > 1, (
            f"Transaction Detail should have multiple rows pre-filter, "
            f"got {before}"
        )

        _set_date(page, 0, "2099/01/01", timeout_ms=page_timeout)
        _set_date(page, 1, "2099/12/31", timeout_ms=page_timeout)

        page.wait_for_function(
            f"""() => {{
                const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
                for (const v of visuals) {{
                    const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                    if (!t || t.innerText.trim() !== 'Transaction Detail') continue;
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

        after = _table_row_count(page, "Transaction Detail")
        screenshot(
            page, "filter_date_range_future", subdir="account_recon",
        )
        assert after < before, (
            f"Transaction Detail should shrink from {before} rows "
            f"after future date range, got {after}"
        )
