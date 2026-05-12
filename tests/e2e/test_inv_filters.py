"""Browser tests: Investigation parameter sliders narrow the visuals.

Parametrized over ``[qs, app2]`` (X.2.u.3) via ``inv_dashboard_driver``.
Investigation's threshold knobs (σ / max-hops / min-amount) are
single-value ``ParameterSlider`` controls; their narrowing is pushed
into the dataset SQL as a scalar ``<<$param>>`` bind (Y.2.a/Y.3.c), so
moving the slider re-fetches a narrower result on *both* renderers.

- **app2** — runs the body. ``make_filter_specs_for_sheet`` emits a
  ``ParameterNumberSpec`` for each ``ParameterSlider`` (X.2.u.4.e) → an
  ``<input type="number" name="param_<name>">`` + a one-handle
  noUiSlider; ``App2Driver.set_slider`` writes the input + a bubbling
  ``change`` → the visual re-fetches with the new scalar bind.
- **qs** — still skipped. ``QsEmbedDriver.set_slider`` (DOM-driving the
  ``ParameterSliderControl`` widget) has no helper yet — the QS slider
  is a React-rendered handle with no editable value field, so the
  selector/drag mechanics need a UI sample to pin down before it's
  worth implementing (``feedback_aws_research``). Tracked as the QS half
  of X.2.u.4.e.

The slider-narrowing *behaviour* is additionally covered renderer-free
by the SQL-pushdown unit tests (``<<$pInvAnomaliesSigma>>`` →
``WHERE z_score >= …``, ``<<$pInvMoneyTrailMinAmount>>`` → ``… >= …``)
and the App2 substitution path by ``test_html2_*`` / ``test_dashboard_driver``.
"""

from __future__ import annotations

import pytest

from tests.e2e._drivers import DashboardDriver


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


def _skip_qs_until_slider_drive(driver: DashboardDriver) -> None:
    """The ``qs`` leg skips until ``QsEmbedDriver.set_slider`` lands —
    see the module docstring. The ``app2`` leg runs the body."""
    if driver.dialect == "qs":
        pytest.skip(
            "QsEmbedDriver.set_slider (ParameterSliderControl DOM-drive) "
            "not implemented yet — needs a QS-UI sample of the slider "
            "widget DOM (feedback_aws_research); QS half of X.2.u.4.e"
        )


def test_min_sigma_slider_shrinks_anomalies_kpi(inv_dashboard_driver):
    """Pushing the "Min sigma" slider to its max (4) must drop the
    Flagged Pair-Windows KPI below its default-σ value.

    Sigma threshold binds ``WHERE z_score >= <<$pInvAnomaliesSigma>>`` in
    the Volume Anomalies dataset SQL; the seed's z-scores cap in single
    digits, so σ=4 narrows the surviving rows hard.
    """
    driver, dashboard_arg = inv_dashboard_driver
    _skip_qs_until_slider_drive(driver)
    driver.open(dashboard_arg, sheet="Volume Anomalies")
    driver.wait_loaded("Flagged Pair-Windows")
    before = driver.kpi_value("Flagged Pair-Windows")

    driver.set_slider("Min sigma", 4, None)
    driver.wait_loaded("Flagged Pair-Windows")
    after = driver.kpi_value("Flagged Pair-Windows")

    driver.screenshot()
    assert after != before, (
        f"Flagged Pair-Windows should change at σ=4; "
        f"before={before!r} (default σ), after={after!r} (σ=4)"
    )


def test_min_hop_amount_slider_shrinks_money_trail_table(inv_dashboard_driver):
    """Pushing the "Min hop amount ($)" slider to its max ($1,000) must
    shrink the Money Trail Hop-by-Hop table vs its default ($0).

    Min-amount binds ``WHERE ... >= <<$pInvMoneyTrailMinAmount>>`` in the
    Money Trail dataset SQL.
    """
    driver, dashboard_arg = inv_dashboard_driver
    _skip_qs_until_slider_drive(driver)
    driver.open(dashboard_arg, sheet="Money Trail")
    driver.wait_loaded("Money Trail — Hop-by-Hop")
    before = len(driver.table_rows("Money Trail — Hop-by-Hop"))
    if before <= 0:
        pytest.skip(
            "Money Trail — Hop-by-Hop starts empty for the deployed L2 "
            "(no multi-hop edges seeded — spec_example declares zero "
            "chains and single-leg templates); the slider-narrowing guard "
            "has nothing to shrink. The empty-render path is covered by "
            "the sheet-visuals tests."
        )

    driver.set_slider("Min hop amount ($)", 1000, None)
    driver.wait_loaded("Money Trail — Hop-by-Hop")
    after = len(driver.table_rows("Money Trail — Hop-by-Hop"))

    driver.screenshot()
    assert after < before, (
        f"Hop-by-Hop should shrink at min hop=$1,000; "
        f"before={before}, after={after}"
    )
