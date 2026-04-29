"""Browser tests: PR cross-sheet drill-downs navigate to the target sheet.

L.11.4 — parametrized over every cross-sheet, left-click `Drill` the
tree declares (via `enumerate_cross_sheet_left_click_drills(pr_app)`).
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.browser.helpers import (
    click_first_row_of_visual,
    click_sheet_tab,
    generate_dashboard_embed_url,
    screenshot,
    selected_sheet_name,
    wait_for_dashboard_loaded,
    wait_for_sheet_tab,
    wait_for_visuals_present,
    webkit_page,
)
from .tree_validator import enumerate_cross_sheet_left_click_drills


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


def _pr_drill_specs():
    """Build the parametrize list at collection time. Same shape as
    `_ar_drill_specs()` in `test_ar_drilldown.py`.

    Parametrize runs at module import — *before* the e2e gate skip in
    `conftest.py` has a chance to fire — so on CI (no `config.yaml`,
    no `QS_GEN_*` env) `load_config(None)` would raise. Catching here
    and returning `[]` makes pytest mark the test as "no parameters"
    and skip cleanly; on a configured dev box the full enumeration
    runs as before.
    """
    from pathlib import Path

    from quicksight_gen.apps.payment_recon.app import build_payment_recon_app
    from quicksight_gen.common.config import load_config

    cfg = None
    for candidate in (Path("config.yaml"), Path("run/config.yaml")):
        if candidate.exists():
            cfg = load_config(str(candidate))
            break
    if cfg is None:
        try:
            cfg = load_config(None)
        except ValueError:
            return []
    app = build_payment_recon_app(cfg)
    app.emit_analysis()

    out = []
    for src_sheet, src_visual, tgt_sheet in (
        enumerate_cross_sheet_left_click_drills(app)
    ):
        title = getattr(src_visual, "title", None)
        if not title:
            continue
        out.append(pytest.param(
            src_sheet.name,
            title,
            tgt_sheet.name,
            id=f"{src_sheet.name}::{title}→{tgt_sheet.name}",
        ))
    return out


@pytest.fixture
def embed_url(region, account_id, dashboard_id) -> str:
    return generate_dashboard_embed_url(
        aws_account_id=account_id,
        aws_region=region,
        dashboard_id=dashboard_id,
    )


@pytest.mark.parametrize(
    "src_sheet_name,src_visual_title,tgt_sheet_name", _pr_drill_specs(),
)
def test_drill_navigates_to_target_sheet(
    embed_url, page_timeout,
    src_sheet_name, src_visual_title, tgt_sheet_name,
):
    """Click the first row of the source visual; the drill should switch
    the dashboard to the target sheet."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, src_sheet_name, timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=1, timeout_ms=page_timeout)
        click_first_row_of_visual(
            page, src_visual_title, timeout_ms=page_timeout,
        )
        wait_for_sheet_tab(page, tgt_sheet_name, timeout_ms=page_timeout)
        screenshot(
            page,
            f"drill_{src_sheet_name}_to_{tgt_sheet_name}".replace(" ", "_"),
            subdir="payment_recon",
        )
        assert selected_sheet_name(page) == tgt_sheet_name
