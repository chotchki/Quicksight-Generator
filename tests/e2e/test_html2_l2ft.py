"""Y.2.app2.cde.l2ft-wiring.c — L2 Flow Tracing Layer-2 e2e against the
HTMX dialect.

Builds the real L2FT tree, plugs in a stub fetcher returning deterministic
data per visual_id, spins the App2 Starlette server in a thread, and drives
Playwright (WebKit, headless) against ``/dashboards/l2ft``.

Asserts on:

- Sheet tabs render (Getting Started / Rails / Chains / Transfer Templates / …)
- The Rails sheet's filter bar carries the three MULTI_SELECT pushdown
  dropdowns auto-derived from the tree (``<select multiple
  name="param_pL2ftRail">`` + ``pL2ftStatus`` + ``pL2ftBundle``) — i.e.
  ``make_filter_specs_for_sheet`` (Y.2.app2.cde.l2ft-wiring.b) fired and
  the route rendered the specs.
- The Chains sheet carries its own dropdowns (``pL2ftChainsChain`` /
  ``pL2ftChainsCompletion``) — even if vacuous for the spec_example L2.
- Selecting a value in the rail multi-select re-fetches the sheet's
  visuals with ``param_pL2ftRail`` in the query string — the repeated-key
  shape ``_sql_executor``'s multi-valued expansion consumes.

Stub fetcher (not live PG) keeps the test fast + DB-free, same shape as
``test_html2_executives.py``. The live-PG variant is the ``app2`` chain
layer (``./run_tests.sh up_to=app2 …``) which runs this file with
``QS_GEN_E2E=1`` against a seeded container.

Gated by ``QS_GEN_E2E=1`` like every other tests/e2e/ file.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
from quicksight_gen.apps.l2_flow_tracing.app import build_l2_flow_tracing_app
from quicksight_gen.apps.l2_flow_tracing.datasets import (
    build_all_l2_flow_tracing_datasets,
)
from quicksight_gen.common.browser.helpers import webkit_page
from tests._test_helpers import make_test_config
from tests.e2e._harness_html2 import html2_server


# Playwright tracing / console capture on failure (Y.2.gate.c.11.app2);
# the importorskip gate keeps the module skippable without Playwright.
playwright_sync_api = pytest.importorskip("playwright.sync_api")


_TEST_INSTANCE = default_l2_instance()
_TEST_CFG = make_test_config().with_l2_instance_prefix(str(_TEST_INSTANCE.instance))
_DASHBOARD_ID = "l2ft"


_calls_log: list[tuple[str, dict[str, list[str]]]] = []


def _l2ft_stub_fetcher(
    visual_id: str, params: dict[str, list[str]],
) -> dict[str, Any]:
    """Deterministic per-visual-kind stub. Records every call into
    ``_calls_log`` so the dropdown-selection assertion can inspect what
    URL params landed. ``params`` is the URL multi-dict."""
    _calls_log.append((visual_id, dict(params)))
    vid = visual_id.lower()
    if "kpi" in vid:
        return {"values": [
            {"value": 12, "label": "Transactions", "format": "number"},
        ]}
    if "table" in vid:
        return {
            "columns": ["transaction_id", "rail_name", "status"],
            "rows": [["tx-1", "rail-a", "posted"], ["tx-2", "rail-b", "pending"]],
            "page_offset": 0, "page_size": 2, "total_rows": 2,
        }
    if "bar" in vid or "chart" in vid:
        return {
            "categories": ["rail-a", "rail-b"], "values": [3, 5],
            "x_label": "Rail", "y_label": "Count",
        }
    if "sankey" in vid:
        return {"nodes": [], "links": []}
    return {}


def _sheet_id_by_name(tree_app: Any, name: str) -> str:
    assert tree_app.analysis is not None
    return str(next(
        s.sheet_id for s in tree_app.analysis.sheets if s.name == name
    ))


@pytest.fixture
def l2ft_server() -> Iterator[tuple[str, Any]]:
    """App2 server with the real L2FT tree + stub fetcher. Yields
    ``(base_url, tree_app)`` so tests can resolve sheet ids."""
    _calls_log.clear()
    build_all_l2_flow_tracing_datasets(_TEST_CFG, _TEST_INSTANCE)
    tree_app = build_l2_flow_tracing_app(_TEST_CFG, l2_instance=_TEST_INSTANCE)
    assert tree_app.analysis is not None
    landing_sheet = tree_app.analysis.sheets[0]  # Getting Started
    with html2_server(
        tree_app=tree_app,
        sheet=landing_sheet,
        data_fetcher=_l2ft_stub_fetcher,
        dashboard_id=_DASHBOARD_ID,
        dashboard_title="L2 Flow Tracing",
    ) as base_url:
        yield base_url, tree_app


def test_l2ft_dashboard_landing_renders_with_sheet_tabs(
    l2ft_server: tuple[str, Any],
) -> None:
    base_url, _ = l2ft_server
    with webkit_page() as page:
        page.goto(f"{base_url}/dashboards/{_DASHBOARD_ID}")
        page.wait_for_load_state("networkidle")
        nav_html = page.locator("nav").inner_html()
        for expected in ("Getting Started", "Rails", "Chains", "Transfer Templates"):
            assert expected in nav_html, (
                f"Sheet tab {expected!r} missing from nav — got {nav_html[:300]}"
            )


def test_l2ft_rails_sheet_renders_three_multiselect_dropdowns(
    l2ft_server: tuple[str, Any],
) -> None:
    """Y.2.app2.cde.l2ft-wiring.b — the Rails sheet's filter bar carries
    the rail / status / bundle MULTI_SELECT dropdowns the tree-walk
    auto-derived, each rendered as a ``<select multiple>`` with options."""
    base_url, tree_app = l2ft_server
    rails_id = _sheet_id_by_name(tree_app, "Rails")
    with webkit_page() as page:
        page.goto(f"{base_url}/dashboards/{_DASHBOARD_ID}/sheets/{rails_id}")
        page.wait_for_load_state("networkidle")
        for param in ("pL2ftRail", "pL2ftStatus", "pL2ftBundle"):
            sel = page.locator(f'select[name="param_{param}"]')
            assert sel.count() == 1, f"missing <select name=param_{param}>"
            assert sel.first.evaluate("el => el.multiple") is True, (
                f"param_{param} should be a multi-select"
            )
            assert sel.locator("option").count() >= 1, (
                f"param_{param} has no options"
            )


def test_l2ft_chains_sheet_renders_its_dropdowns(
    l2ft_server: tuple[str, Any],
) -> None:
    """The Chains sheet carries its own auto-derived dropdowns. spec_example
    declares no chains, so the option lists may be empty — what matters is
    the ``<select multiple>`` widgets are present (wiring proof)."""
    base_url, tree_app = l2ft_server
    chains_id = _sheet_id_by_name(tree_app, "Chains")
    with webkit_page() as page:
        page.goto(f"{base_url}/dashboards/{_DASHBOARD_ID}/sheets/{chains_id}")
        page.wait_for_load_state("networkidle")
        for param in ("pL2ftChainsChain", "pL2ftChainsCompletion"):
            sel = page.locator(f'select[name="param_{param}"]')
            assert sel.count() == 1, f"missing <select name=param_{param}>"
            assert sel.first.evaluate("el => el.multiple") is True


def test_l2ft_rail_dropdown_selection_refetches_with_param(
    l2ft_server: tuple[str, Any],
) -> None:
    """Selecting a value in the rail multi-select fires a debounced refresh
    that re-fetches the sheet's visuals with ``param_pL2ftRail`` in the
    query string — the repeated-key wire shape the multi-valued executor
    consumes."""
    base_url, tree_app = l2ft_server
    rails_id = _sheet_id_by_name(tree_app, "Rails")
    with webkit_page() as page:
        page.goto(f"{base_url}/dashboards/{_DASHBOARD_ID}/sheets/{rails_id}")
        page.wait_for_load_state("networkidle")
        # Wait past the initial auto-load fetch before clearing the log.
        page.wait_for_timeout(400)
        _calls_log.clear()
        # Select the first rail option. ``select_option`` fires a change
        # event that the form's debounced listener broadcasts as refresh.
        page.select_option('select[name="param_pL2ftRail"]', index=0)
        page.wait_for_timeout(900)  # 300ms debounce + swap settle
    saw_rail_param = [
        params for _vid, params in _calls_log
        if params.get("param_pL2ftRail")
    ]
    assert saw_rail_param, (
        f"no fetch carried param_pL2ftRail after selecting a rail. "
        f"Calls: {[(v, dict(p)) for v, p in _calls_log[:8]]}"
    )
    # The selected value flows through as a single-element list.
    assert all(len(p["param_pL2ftRail"]) >= 1 for p in saw_rail_param)
