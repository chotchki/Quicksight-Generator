"""Browser tests: PR filter controls actually filter the underlying visuals.

Covers the shared date-range filter across pipeline sheets plus the
optional-metadata and payment-method filter matrix. See PLAN.md Phase 2.
"""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_sheet_tab,
    count_table_total_rows,
    generate_dashboard_embed_url,
    screenshot,
    set_date_range,
    wait_for_dashboard_loaded,
    wait_for_table_total_rows_to_change,
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


# (sheet_name, target_table_title) — the pipeline sheets scoped by
# ``fg-date-range``. Each sheet's detail table is the filter-propagation
# witness; if the filter is live, this table will empty when the date
# window excludes the demo seed.
_PIPELINE_DETAIL_TABLES = [
    ("Sales Overview", "Sales Detail"),
    ("Settlements", "Settlement Detail"),
    ("Payments", "Payment Detail"),
]


@pytest.mark.parametrize("sheet,table", _PIPELINE_DETAIL_TABLES)
def test_date_range_future_empties_pipeline_table(
    embed_url, page_timeout, sheet, table,
):
    """Pushing the date range to a future window should shrink every
    pipeline sheet's detail table below its pre-filter row count."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, sheet, timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=3, timeout_ms=page_timeout)

        before = count_table_total_rows(page, table, timeout_ms=page_timeout)
        assert before > 1, f"{table!r} should have rows pre-filter, got {before}"

        set_date_range(page, "2099/01/01", "2099/12/31", timeout_ms=page_timeout)
        after = wait_for_table_total_rows_to_change(
            page, table, before, timeout_ms=page_timeout,
        )
        screenshot(
            page, f"filter_date_range_future_{sheet.replace(' ', '_').lower()}",
            subdir="payment_recon",
        )
        assert after < before, (
            f"{table!r} on {sheet!r} should shrink from {before} rows "
            f"after future date range, got {after}"
        )


def test_date_range_demo_window_preserves_settlements(embed_url, page_timeout):
    """Setting a date range that covers the full demo period (anchor
    2026-01-15, sales span ~90 days back) should *not* reduce the
    Settlement Detail count — proves the filter is active but non-
    destructive when the window contains all data. Complements 2.1/2.2
    which prove the filter narrows on out-of-window ranges."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Settlements", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=3, timeout_ms=page_timeout)
        page.wait_for_selector(
            '[data-automation-id^="sn-table-cell-0-0"]',
            timeout=page_timeout,
            state="attached",
        )

        before = count_table_total_rows(
            page, "Settlement Detail", timeout_ms=page_timeout,
        )
        assert before > 1

        set_date_range(page, "2025/01/01", "2026/12/31", timeout_ms=page_timeout)
        # Give the filter a moment to settle; then confirm no drop.
        page.wait_for_timeout(2000)
        after = count_table_total_rows(
            page, "Settlement Detail", timeout_ms=page_timeout,
        )
        assert after == before, (
            f"Wide window covering full demo should preserve row count; "
            f"before={before}, after={after}"
        )


def test_date_range_past_empties_sales_detail(embed_url, page_timeout):
    """A past-window range (pre-demo) should also empty the table, proving
    the filter isn't one-sided (upper-bound-only) — covers PLAN 2.2."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Sales Overview", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=5, timeout_ms=page_timeout)

        before = count_table_total_rows(
            page, "Sales Detail", timeout_ms=page_timeout,
        )
        assert before > 1

        set_date_range(page, "2000/01/01", "2000/12/31", timeout_ms=page_timeout)
        after = wait_for_table_total_rows_to_change(
            page, "Sales Detail", before, timeout_ms=page_timeout,
        )
        assert after < before, (
            f"Sales Detail should shrink with a past-window range, "
            f"before={before}, after={after}"
        )
