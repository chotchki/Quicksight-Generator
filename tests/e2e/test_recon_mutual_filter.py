"""Browser tests: payment recon mutual table filtering."""

from __future__ import annotations

import time

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


def _table_row_count(page, visual_title: str) -> int:
    """Count distinct rows in the table whose visual title matches."""
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


def _click_first_row_of_visual(page, visual_title: str, timeout_ms: int) -> None:
    """Click the first cell of the first row of the named visual.

    Scrolls the target visual into view first — QuickSight virtualizes
    cells in below-the-fold visuals, so they are absent from the DOM until
    the visual is on screen.
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

        before = _table_row_count(page, "Internal Payments")
        assert before > 1, (
            f"Internal Payments table should have multiple rows before filtering, got {before}"
        )

        _click_first_row_of_visual(page, "External Transactions", timeout_ms=page_timeout)
        # Filter application is async on the client; poll until row count drops
        page.wait_for_function(
            f"""() => {{
                const visuals = document.querySelectorAll('[data-automation-id="analysis_visual"]');
                for (const v of visuals) {{
                    const t = v.querySelector('[data-automation-id="analysis_visual_title_label"]');
                    if (!t || t.innerText.trim() !== 'Internal Payments') continue;
                    const rows = new Set();
                    v.querySelectorAll('[data-automation-id^="sn-table-cell-"]').forEach(c => {{
                        const m = c.getAttribute('data-automation-id').match(/sn-table-cell-(\\d+)-/);
                        if (m) rows.add(m[1]);
                    }});
                    return rows.size > 0 && rows.size < {before};
                }}
                return false;
            }}""",
            timeout=page_timeout,
        )

        after = _table_row_count(page, "Internal Payments")
        screenshot(page, "recon_mutual_filter_external_to_payments")
        assert 0 < after < before, (
            f"Internal Payments should filter to < {before} rows after click, got {after}"
        )
