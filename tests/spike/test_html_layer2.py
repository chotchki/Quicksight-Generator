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


def test_layer2_click_pivots_sankey(server_url: str) -> None:
    """Click a node rect → d3 click handler fires ``htmx.ajax`` with
    ``anchor`` merged into form values → server returns a new
    fragment → ``htmx:afterSwap`` re-runs hydration → SVG redraws
    with the anchor-pivoted data.

    Layer 1 (renderer-agnostic): ``_anchor_aware_fetcher`` returns
    a different first-link weight when ``anchor`` is set vs unset.
    Layer 2 (HTMX dialect): Playwright captures the first link's
    rendered ``stroke-width`` before and after the click, asserts
    they differ.

    Demonstrates the d3-clicks-fire-HTMX-via-htmx.ajax pattern:
    the SVG is d3's, the click is d3's, but the request is
    HTMX-shaped and reuses the swap pipeline.
    """
    # NOTE: this test installs its own ``page.route`` to override
    # the server's data fetcher, so the ``server_url`` fixture's
    # fetcher is irrelevant here.
    with playwright_sync_api.sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()

        # Override the server's fetcher: returns a 2-link payload
        # without anchor, a 4-link payload with anchor. Different
        # link COUNT (not just widths) makes the Layer 2 assertion
        # robust against d3-sankey's relative-width scaling
        # quirks — counting paths is unambiguous.
        def anchor_aware_route(route: Any) -> None:
            req = route.request
            body = req.post_data or ""
            anchor_present = "anchor=" in body and "anchor=&" not in body
            if anchor_present:
                payload: dict[str, Any] = {
                    "nodes": [
                        {"name": "ExternalAcquirer"},
                        {"name": "CustomerDDA"},
                        {"name": "GLControl"},
                        {"name": "Concentration"},
                        {"name": "FundsPool"},
                    ],
                    "links": [
                        {"source": 0, "target": 1, "value": 50},
                        {"source": 1, "target": 2, "value": 40},
                        {"source": 2, "target": 3, "value": 30},
                        {"source": 3, "target": 4, "value": 20},
                    ],
                }
            else:
                payload = {
                    "nodes": [
                        {"name": "ExternalAcquirer"},
                        {"name": "CustomerDDA"},
                        {"name": "GLControl"},
                    ],
                    "links": [
                        {"source": 0, "target": 1, "value": 5},
                        {"source": 1, "target": 2, "value": 5},
                    ],
                }
            import json as _json
            fragment = (
                '<script type="application/json" class="chart-data">'
                + _json.dumps(payload) + "</script>"
            )
            route.fulfill(
                status=200,
                content_type="text/html",
                body=fragment,
            )

        page.route("**/visual/**/data", anchor_aware_route)

        # Capture the POST bodies so failures distinguish "click
        # didn't fire" from "server saw the wrong body" from
        # "response wasn't applied".
        captured_bodies: list[str] = []
        page.on("request", lambda req: (
            captured_bodies.append(req.post_data or "")
            if "/visual/" in req.url and "/data" in req.url
            else None
        ))

        page.goto(server_url)
        # Initial swap to draw the Sankey (no anchor → small first link).
        with page.expect_response("**/visual/**/data") as init_resp:
            page.click("button[hx-post]")
        assert init_resp.value.status == 200
        sankey_svg = page.locator(
            'section[data-visual-kind="Sankey"] svg',
        )
        sankey_svg.wait_for(state="attached", timeout=5000)

        before_paths = sankey_svg.locator("path").count()

        # Click the first node rect — d3's handler fires htmx.ajax
        # with anchor=<node.name> merged in. ``expect_response``
        # waits for the round-trip to complete; without it we'd race
        # the swap + hydrate timeline.
        first_rect = sankey_svg.locator("rect").first
        with page.expect_response("**/visual/**/data") as click_resp:
            first_rect.click()
        assert click_resp.value.status == 200, (
            f"Click triggered a response with bad status. Bodies seen: "
            f"{captured_bodies}"
        )

        # Wait for d3 to redraw with a different link count.
        page.wait_for_function(
            "before => document.querySelectorAll("
            "'section[data-visual-kind=\"Sankey\"] svg path').length !== before",
            arg=before_paths,
            timeout=5000,
        )
        after_paths = sankey_svg.locator("path").count()
        browser.close()

    # Diagnostic: surface which requests fired so a future regression
    # can tell click-didn't-fire from wrong-body.
    assert len(captured_bodies) >= 2, (
        f"Expected ≥2 POSTs (initial button click + rect click), "
        f"saw {len(captured_bodies)}: {captured_bodies}"
    )
    assert "anchor=" in captured_bodies[1], (
        f"Second POST (the d3 click) didn't include anchor in body. "
        f"Body: {captured_bodies[1]!r}. fireAnchorRequest in the "
        f"bootstrap JS isn't merging anchor into values, OR the click "
        f"reached the wrong handler."
    )
    # Layer 1 promised 2 links unanchored, 4 anchored. Layer 2
    # asserts the SVG redrew with the post-anchor link count.
    assert before_paths == 2, (
        f"Initial render expected 2 paths (Layer 1 unanchored), "
        f"got {before_paths}."
    )
    assert after_paths == 4, (
        f"Post-click render expected 4 paths (Layer 1 anchored), "
        f"got {after_paths}. The click fired (anchor in body) but d3 "
        f"didn't re-render the new link set, OR the response wasn't "
        f"swapped into the visual-data div."
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
