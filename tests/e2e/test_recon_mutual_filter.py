"""Browser tests: payment recon mutual table filtering."""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_sheet_tab,
    count_table_rows,
    generate_dashboard_embed_url,
    screenshot,
    scroll_visual_into_view,
    wait_for_dashboard_loaded,
    wait_for_table_rows_to_change,
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


def _click_first_row_of_visual(page, visual_title: str, timeout_ms: int) -> None:
    """Click the first cell of the first row of the named visual."""
    scroll_visual_into_view(page, visual_title, timeout_ms)
    selector = page.evaluate(
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
    assert selector, f"Could not find first cell of visual {visual_title!r}"
    page.click('[data-e2e-target="1"]', timeout=timeout_ms)


def test_clicking_external_txn_filters_payments(embed_url, page_timeout):
    """Clicking an External Transactions row should reduce the Internal Payments row count."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Payment Reconciliation", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=6, timeout_ms=page_timeout)
        page.wait_for_selector(
            '[data-automation-id^="sn-table-cell-0-0"]',
            timeout=page_timeout,
            state="attached",
        )

        before = count_table_rows(page, "Internal Payments")
        assert before > 1, (
            f"Internal Payments table should have multiple rows before filtering, got {before}"
        )

        _click_first_row_of_visual(page, "External Transactions", timeout_ms=page_timeout)
        after = wait_for_table_rows_to_change(
            page, "Internal Payments", before, timeout_ms=page_timeout,
        )
        screenshot(
            page,
            "recon_mutual_filter_external_to_payments",
            subdir="payment_recon",
        )
        assert 0 < after < before, (
            f"Internal Payments should filter to < {before} rows after click, got {after}"
        )
