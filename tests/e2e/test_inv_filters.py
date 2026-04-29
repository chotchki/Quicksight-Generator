"""Browser tests: Investigation parameters narrow the underlying visuals.

Investigation uses ``ParameterSliderControl`` widgets (single-value
parameter sliders) rather than ``FilterSliderControl`` ranges, so the
existing ``set_slider_range`` helper's DOM target doesn't apply. Until
a ``set_parameter_slider_value`` helper lands, these tests exercise the
data-filter path via URL parameter (``#p.<name>=<value>``) — per the
``project_qs_url_parameter_no_control_sync`` memory, URL-set parameters
do filter the data even though they don't sync the on-screen control
widget. The slider's DOM-driven path is verified manually + structurally
(test_inv_dashboard_structure proves the filter group is parameter-bound).
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.browser.helpers import (
    click_sheet_tab,
    count_table_total_rows,
    generate_dashboard_embed_url,
    parse_kpi_number,
    screenshot,
    wait_for_dashboard_loaded,
    wait_for_kpi_text_nonempty,
    wait_for_visuals_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture
def embed_url(region, account_id, inv_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        aws_account_id=account_id,
        aws_region=region,
        dashboard_id=inv_dashboard_id,
    )


@pytest.mark.skip(
    reason=(
        "Deferred: appending '#p.<name>=<value>' to a generated embed URL "
        "breaks dashboard loading — wait_for_dashboard_loaded times out "
        "waiting for [role='tab']. The hash appears to interfere with the "
        "embed handshake (separate from the project_qs_url_parameter_no_control_sync "
        "issue, which is about controls not syncing once params are set). "
        "Need either: a ParameterSliderControl DOM helper to drive the "
        "on-screen widget, or a different way to apply parameter values "
        "post-load. Tracked for K.4.9 follow-up."
    )
)
def test_sigma_url_parameter_shrinks_anomalies_kpi(embed_url, page_timeout):
    """Loading the dashboard with ``#p.pInvAnomaliesSigma=99`` should
    drop the Flagged Pair-Windows KPI to zero (or near-zero).

    Sigma threshold is bound by NumericRangeFilter on z_score; the seed
    z-score distribution caps in single digits, so σ=99 narrows the KPI
    to no surviving rows. Compares the KPI value against a baseline pull
    where σ uses its default (2 — a permissive threshold).
    """
    # Baseline pull at default σ.
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Volume Anomalies", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=3, timeout_ms=page_timeout)
        before_text = wait_for_kpi_text_nonempty(
            page, "Flagged Pair-Windows", timeout_ms=page_timeout,
        )
        before = parse_kpi_number(before_text)
        assert before > 0, (
            f"Flagged Pair-Windows pre-σ should be > 0, got {before}"
        )

    # Re-load with σ=99 in the URL hash.
    extreme_url = f"{embed_url}#p.pInvAnomaliesSigma=99"
    with webkit_page(headless=True) as page:
        page.goto(extreme_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Volume Anomalies", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=3, timeout_ms=page_timeout)
        after_text = wait_for_kpi_text_nonempty(
            page, "Flagged Pair-Windows", timeout_ms=page_timeout,
        )
        after = parse_kpi_number(after_text)
        screenshot(page, "filter_sigma_url_high", subdir="investigation")
        assert after < before, (
            f"Flagged Pair-Windows should drop with σ=99 in URL; "
            f"before={before} (default σ), after={after} (σ=99)"
        )


@pytest.mark.skip(
    reason=(
        "Deferred: same '#p.<name>=<value>' embed-URL loading issue as "
        "test_sigma_url_parameter_shrinks_anomalies_kpi above. Tracked "
        "for K.4.9 follow-up."
    )
)
def test_min_hop_amount_url_parameter_shrinks_money_trail_table(
    embed_url, page_timeout,
):
    """Loading the dashboard with ``#p.pInvMoneyTrailMinAmount=999999999``
    should empty the Money Trail Hop-by-Hop table.

    The seed's largest hop is well under $1B; setting the floor that
    high forces the table to drop to zero rows.
    """
    # Baseline pull at default min-amount (0).
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Money Trail", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=2, timeout_ms=page_timeout)
        before = count_table_total_rows(
            page, "Money Trail — Hop-by-Hop", timeout_ms=page_timeout,
        )
        assert before > 0, (
            f"Money Trail Hop-by-Hop pre-filter should have rows, got {before}"
        )

    # Re-load with min hop amount $1B in the URL hash.
    extreme_url = f"{embed_url}#p.pInvMoneyTrailMinAmount=999999999"
    with webkit_page(headless=True) as page:
        page.goto(extreme_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Money Trail", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=2, timeout_ms=page_timeout)
        after = count_table_total_rows(
            page, "Money Trail — Hop-by-Hop", timeout_ms=page_timeout,
        )
        screenshot(
            page, "filter_min_hop_amount_url_high", subdir="investigation",
        )
        assert after < before, (
            f"Money Trail Hop-by-Hop should shrink with min hop=$1B in URL; "
            f"before={before}, after={after}"
        )
