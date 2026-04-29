"""Browser tests: L1 dashboard filter controls actually narrow the data.

M.2c.6. Both tests data-agnostic per the no-hardcoded-data rule:

- **Date-range narrow** is verified on a per-invariant sheet (Drift),
  NOT Today's Exceptions. The Today's Exceptions UNION SQL pre-filters
  to `MAX(business_day_start)` from current_daily_balances by design,
  so the dashboard's date picker is a structural no-op there. The
  per-invariant sheets have no SQL pre-filter, so the date filter on
  the dashboard layer narrows their tables. Future window (2099)
  empties the table — works regardless of what the seed plants.

- **Dropdown shape** is verified by walking the dropdown options and
  confirming the dropdown exposes ≥1 selectable value. Full
  "select-narrows-data" assertion is deferred until M.2b.14 plants
  enough diverse data (multiple accounts per check_type) that picking
  any one value reliably drops the row count from N to <N. Today's
  default seed plants 1 scenario per check kind → 1 row per dropdown
  value → narrowing matches whatever value is picked.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.browser.helpers import (
    click_sheet_tab,
    count_table_total_rows,
    generate_dashboard_embed_url,
    read_dropdown_options,
    screenshot,
    set_parameter_datetime_value,
    wait_for_dashboard_loaded,
    wait_for_table_cells_present,
    wait_for_table_total_rows_to_change,
    wait_for_visuals_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture
def embed_url(region, account_id, l1_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        aws_account_id=account_id,
        aws_region=region,
        dashboard_id=l1_dashboard_id,
    )


# Tall viewport so all visuals render above the fold during the walk.
TALL_VIEWPORT = (1600, 4000)


def test_date_range_filter_narrows_drift_sheet(
    embed_url, page_timeout,
):
    """Setting the date range to a 2099 future window must empty the
    Leaf Account Drift table — no L2 instance plants drift in 2099.

    Verifies the M.2b.1 parameter-bound TimeRangeFilter actually
    cascades from the date pickers through the params through the
    filter group's TimeRangeFilter into the dataset query.
    """
    with webkit_page(headless=True, viewport=TALL_VIEWPORT) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Drift", timeout_ms=page_timeout)
        wait_for_visuals_present(
            page, min_count=4, timeout_ms=page_timeout,
        )
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        before = count_table_total_rows(
            page, "Leaf Account Drift", timeout_ms=page_timeout,
        )
        assert before > 0, (
            f"Leaf Account Drift must have data pre-filter, got {before}"
        )

        # ParameterDateTimePicker pickers are separate sheet controls
        # (one per parameter), so target each by control title rather
        # than the indexed-range-picker selector AR uses.
        set_parameter_datetime_value(
            page, "Date From", "2099/01/01", timeout_ms=page_timeout,
        )
        set_parameter_datetime_value(
            page, "Date To", "2099/12/31", timeout_ms=page_timeout,
        )
        after = wait_for_table_total_rows_to_change(
            page, "Leaf Account Drift", before, timeout_ms=page_timeout,
        )
        assert after < before, (
            f"Leaf Account Drift should narrow with future date "
            f"range; before={before}, after={after}"
        )
        screenshot(
            page, "filter_date_future_drift", subdir="l1_dashboard",
        )


def test_check_type_dropdown_exposes_options(
    embed_url, page_timeout,
):
    """The Check Type dropdown on Today's Exceptions exposes the L1
    invariant view names (drift / ledger_drift / overdraft / etc.) as
    selectable values. Dropdown options come from the data — we don't
    hardcode what values appear, only that the dropdown is populated
    and openable.

    Full "select-narrows-data" assertion deferred until M.2b.14 plants
    enough diverse data that any single value-pick reliably drops the
    row count.
    """
    with webkit_page(headless=True, viewport=TALL_VIEWPORT) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Today's Exceptions", timeout_ms=page_timeout)
        wait_for_visuals_present(
            page, min_count=3, timeout_ms=page_timeout,
        )
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        options = read_dropdown_options(
            page, "Check Type", timeout_ms=page_timeout,
        )
        assert len(options) >= 1, (
            f"Check Type dropdown should expose ≥1 value, got {options}"
        )
