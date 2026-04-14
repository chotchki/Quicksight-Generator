"""Browser tests: payment recon mutual table filtering."""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_first_row_of_visual,
    click_sheet_tab,
    count_table_total_rows,
    generate_dashboard_embed_url,
    read_visual_column_values,
    screenshot,
    wait_for_dashboard_loaded,
    wait_for_table_cells_present,
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


def test_clicking_external_txn_filters_payments(embed_url, page_timeout):
    """Clicking an External Transactions row should reduce the Internal Payments row count."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Payment Reconciliation", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=6, timeout_ms=page_timeout)
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        before = count_table_total_rows(
            page, "Internal Payments", timeout_ms=page_timeout,
        )
        assert before > 1, (
            f"Internal Payments table should have multiple rows before filtering, got {before}"
        )

        click_first_row_of_visual(page, "External Transactions", timeout_ms=page_timeout)
        after = wait_for_table_total_rows_to_change(
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


def test_clicking_internal_payment_filters_external_txns(embed_url, page_timeout):
    """Reverse mutual-filter direction: clicking an Internal Payments row
    should narrow the External Transactions table. Covers PLAN 2.15."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Payment Reconciliation", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=6, timeout_ms=page_timeout)
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        before = count_table_total_rows(
            page, "External Transactions", timeout_ms=page_timeout,
        )
        assert before > 1, (
            f"External Transactions should have multiple rows before "
            f"filtering, got {before}"
        )

        # Find the first Internal Payments row with a non-NULL
        # external_transaction_id (column 5 in the table). Clicking an
        # unmatched row sets the parameter to NULL, and the filter's
        # NullOption=ALL_VALUES means it silently shows everything.
        ext_col_values = read_visual_column_values(
            page, "Internal Payments", col_index=5,
        )
        matched_row = next(
            (i for i, v in enumerate(ext_col_values) if v and v != "null"),
            None,
        )
        assert matched_row is not None, (
            f"No Internal Payments row with a non-NULL "
            f"external_transaction_id visible; got {ext_col_values!r}"
        )
        # Tag and click the chosen row's first cell.
        page.evaluate(
            """({title, row}) => {
                const visuals = document.querySelectorAll(
                    '[data-automation-id="analysis_visual"]'
                );
                for (const v of visuals) {
                    const t = v.querySelector(
                        '[data-automation-id="analysis_visual_title_label"]'
                    );
                    if (!t || t.innerText.trim() !== title) continue;
                    const cell = v.querySelector(
                        `[data-automation-id="sn-table-cell-${row}-0"]`
                    );
                    if (cell) cell.setAttribute('data-e2e-target', '1');
                    return;
                }
            }""",
            {"title": "Internal Payments", "row": matched_row},
        )
        page.click('[data-e2e-target="1"]', timeout=page_timeout)
        page.evaluate(
            """() => document.querySelectorAll('[data-e2e-target]').forEach(
                e => e.removeAttribute('data-e2e-target')
            )"""
        )
        after = wait_for_table_total_rows_to_change(
            page, "External Transactions", before, timeout_ms=page_timeout,
        )
        screenshot(
            page,
            "recon_mutual_filter_payment_to_external",
            subdir="payment_recon",
        )
        assert 0 < after < before, (
            f"External Transactions should filter to < {before} rows "
            f"after click, got {after}"
        )
