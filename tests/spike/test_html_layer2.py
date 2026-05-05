"""X.2.spike.3 — Layer 2 (browser render) gate against the HTMX dialect.

Mirrors ``tests/e2e/_harness_l1_assertions.py``'s Layer 1 + Layer 2
shape against the Starlette HTML server instead of QuickSight:

- **Layer 1 (renderer-agnostic):** call the data fetcher directly
  with known params, capture its return value. This is the
  "ground truth" the rendered output must reflect.

- **Layer 2 (HTMX dialect):** spin up the Starlette server in a
  background thread, drive Playwright (WebKit, headless — same
  browser the QS harness uses) against it. Assert the rendered
  SVG carries the structure Layer 1 promised: N rects (one per
  node), M paths (one per link).

The dialect-comparison thesis: the harness's Layer 2 pattern
catches render bugs in HTMX the same way it catches them in QS.
Same shape — Layer 1 says what the data is, Layer 2 walks the
DOM and asserts it shows up. Different selectors
(``data-visual-kind``+ d3-rendered SVG vs QS's
``data-automation-id``), same gate.

POC scope — this is a single-test demonstration, not a full
harness port. Phase.1 would lift the runner into ``tests/e2e/``
alongside the QS harness, with the same fixture wiring.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn

playwright_sync_api = pytest.importorskip("playwright.sync_api")

from tests._test_helpers import make_test_config
from quicksight_gen.common.html.server import make_app
from quicksight_gen.common.ids import SheetId, VisualId
from quicksight_gen.common.tree.structure import Analysis, App, Sheet
from quicksight_gen.common.tree.visuals import Sankey


# Layer 1 ground truth: the fetcher's output for known inputs. The
# spike's stub varies link weights by date params; here we pin both
# to fixed strings so the layer-1 / layer-2 comparison is exact.
_FIXED_DATA: dict[str, Any] = {
    "nodes": [
        {"name": "External Acquirer"},
        {"name": "Customer DDA"},
        {"name": "GL Control"},
        {"name": "Concentration"},
        {"name": "Funds Pool"},
    ],
    "links": [
        {"source": 0, "target": 1, "value": 50},
        {"source": 1, "target": 2, "value": 40},
        {"source": 2, "target": 3, "value": 30},
        {"source": 3, "target": 4, "value": 20},
    ],
}


def _layer1_fetcher(visual_id: str, params: dict[str, str]) -> dict[str, Any]:
    """Return the fixed Layer 1 data regardless of params.

    A real fetcher (DB-backed) would interpolate ``params`` into a
    query against the matview. For the spike, the deterministic
    stub IS the source-of-truth: Layer 1 = ``_FIXED_DATA``.
    """
    del visual_id, params
    return _FIXED_DATA


def _build_smoke_sheet() -> tuple[App, Sheet]:
    cfg = make_test_config()
    app = App(name="spike3-layer2", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="spike3-analysis",
        name="Spike 3 Layer 2",
    ))
    sheet = analysis.add_sheet(Sheet(
        sheet_id=SheetId("money-trail"),
        name="MoneyTrail",
        title="Money Trail",
        description="X.2.spike.3 Layer 2 gate fixture.",
    ))
    sheet.visuals.append(Sankey(
        title="Money Trail — Chain Sankey",
        subtitle=None,
        visual_id=VisualId("smoke-sankey"),
    ))
    return app, sheet


@pytest.fixture
def server_url() -> Iterator[str]:
    """Spin up the Starlette server in a background thread on an
    ephemeral port; tear down on test exit."""
    tree_app, sheet = _build_smoke_sheet()
    asgi = make_app(
        tree_app=tree_app, sheet=sheet,
        data_fetcher=_layer1_fetcher,
    )
    config = uvicorn.Config(
        asgi, host="127.0.0.1", port=0, log_level="error",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait for the ASGI server to bind. ``server.started`` flips
    # True after the lifespan + bind finish.
    deadline = time.monotonic() + 5.0
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn failed to start within 5s")
        time.sleep(0.05)
    sock = server.servers[0].sockets[0]
    port = sock.getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_layer2_initial_load_renders_sankey(server_url: str) -> None:
    """Page loads → d3 hydrates the Sankey from initial fetcher data
    embedded server-side. Layer 1 says N nodes / M links → Layer 2
    asserts SVG has N rects / M paths.

    Mirrors the QS harness pattern: SQL says expected count, browser
    walks DOM and asserts rendered count matches."""
    expected_nodes = len(_FIXED_DATA["nodes"])
    expected_links = len(_FIXED_DATA["links"])

    with playwright_sync_api.sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()
        # Initial load fetches the page shell. The first Sankey
        # render needs an explicit POST — the page placeholder
        # carries no chart-data on first byte. Click Refresh to
        # trigger the swap, then wait for d3 to draw the SVG.
        page.goto(server_url)
        page.click("button[hx-post]")
        sankey_svg = page.locator(
            'section[data-visual-kind="Sankey"] svg',
        )
        sankey_svg.wait_for(state="attached", timeout=5000)
        # Layer 2 assertions: rect per node, path per link.
        actual_rects = sankey_svg.locator("rect").count()
        actual_paths = sankey_svg.locator("path").count()
        browser.close()

    assert actual_rects == expected_nodes, (
        f"Layer 2 (HTMX dialect): expected {expected_nodes} rects "
        f"(one per node from Layer 1 fetcher), got {actual_rects}. "
        f"d3 hydration didn't render the full node set."
    )
    assert actual_paths == expected_links, (
        f"Layer 2 (HTMX dialect): expected {expected_links} paths "
        f"(one per link from Layer 1 fetcher), got {actual_paths}. "
        f"d3 hydration didn't render the full link set."
    )


def test_layer2_catches_missing_chart_data_bug(server_url: str) -> None:
    """Negative parity check — if the swap fragment dropped the
    chart-data script (regression case for the wrapper-div /
    fragment-shape bugs found in spike.2), Layer 2 catches it: the
    SVG never appears.

    Demonstrates the dialect-comparison thesis: the same Layer 2
    shape that gates QS render bugs gates HTMX render bugs. We
    inject the bug by overriding the swap response via Playwright's
    route interception.
    """
    with playwright_sync_api.sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()

        # Intercept the fetcher endpoint, return an empty body —
        # simulates a regressed server fragment. Layer 2 should
        # then see no SVG and fail the wait.
        def intercept(route: Any) -> None:
            route.fulfill(status=200, body="")

        page.route("**/visual/**/data", intercept)
        page.goto(server_url)
        page.click("button[hx-post]")

        sankey_svg = page.locator(
            'section[data-visual-kind="Sankey"] svg',
        )
        with pytest.raises(playwright_sync_api.TimeoutError):
            sankey_svg.wait_for(state="attached", timeout=2000)
        browser.close()
