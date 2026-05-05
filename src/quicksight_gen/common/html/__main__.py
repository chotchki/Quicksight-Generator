"""X.2.spike.2 — manual smoke runner for the HTML dashboard server.

Builds a minimal Money-Trail-shaped tree ``App`` + ``Sheet`` with one
``Sankey`` visual, wires a stub data fetcher that returns
deterministic d3-sankey-shaped data (responsive to date params), and
runs uvicorn on http://127.0.0.1:8765.

    .venv/bin/python -m quicksight_gen.common.html

The smoke runner intentionally does NOT touch a database — spike.2
validates the swap-on-mutation pattern + d3 hydration, not the
DB-to-d3 pipeline. Phase.1 swaps the stub for a real Money Trail
query against ``<prefix>_inv_money_trail_edges``.

Browser checklist (per CLAUDE.md "use the feature in a browser"):

1. Open http://127.0.0.1:8765/.
2. The Sankey renders on initial page load.
3. Type any date in either input — after 200ms debounce the
   "Refresh" button's HTMX trigger fires, server returns a
   different fragment, d3 re-renders the Sankey.
4. Confirm the swap is fast (<100ms server-side; total <300ms
   including d3 redraw).
5. Confirm the JSON in the swap fragment differs based on the
   date inputs (proves the fetcher's params plumbing).
"""

from __future__ import annotations

import sys
from typing import Any

import uvicorn

from quicksight_gen.common.html.server import make_app
from quicksight_gen.common.ids import SheetId, VisualId
from quicksight_gen.common.tree.structure import Analysis, App, Sheet
from quicksight_gen.common.tree.visuals import ForceGraph, Sankey
from tests._test_helpers import make_test_config


def _build_smoke_app() -> tuple[App, Sheet]:
    cfg = make_test_config()
    app = App(name="x2-spike2-smoke", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="smoke-analysis",
        name="Spike 2 Smoke",
    ))
    sheet = analysis.add_sheet(Sheet(
        sheet_id=SheetId("money-trail"),
        name="MoneyTrail",
        title="Money Trail",
        description=(
            "Spike 2: pick a date range and watch the Sankey re-hydrate "
            "via HTMX swap + d3 from the swapped fragment."
        ),
    ))
    sheet.visuals.append(Sankey(
        title="Money Trail — Chain Sankey",
        subtitle=(
            "Stub data; phase.1 wires this to the real "
            "<prefix>_inv_money_trail_edges matview."
        ),
        visual_id=VisualId("smoke-sankey"),
    ))
    sheet.visuals.append(ForceGraph(
        title="Rails & Accounts — Force Layout",
        subtitle=(
            "X.4 capability test: d3-force renders an account "
            "topology like the existing graphviz pipeline does for "
            "docs. Click a node to anchor; drag-to-position is a "
            "phase.1 follow-on."
        ),
        visual_id=VisualId("smoke-force"),
    ))
    return app, sheet


def _stub_rails_accounts() -> dict[str, Any]:
    """Stub topology shaped like ``common/l2/topology.py`` projects:
    accounts as nodes (typed by ``account_type``), rails as
    undirected edges between them. Persona-blind labels.

    Phase.1 would feed this from ``build_topology_graph(l2_instance)``
    transformed into d3 force shape.
    """
    return {
        "nodes": [
            {"id": "ext_acquirer",      "label": "External Acquirer",      "group": "external_counter"},
            {"id": "customer_dda_a",    "label": "Customer DDA A",         "group": "dda"},
            {"id": "customer_dda_b",    "label": "Customer DDA B",         "group": "dda"},
            {"id": "merchant_dda",      "label": "Merchant DDA",           "group": "merchant_dda"},
            {"id": "gl_control",        "label": "GL Control",             "group": "gl_control"},
            {"id": "concentration",     "label": "Concentration Master",   "group": "concentration_master"},
            {"id": "funds_pool",        "label": "Funds Pool",             "group": "funds_pool"},
        ],
        "links": [
            {"source": "ext_acquirer",   "target": "customer_dda_a"},
            {"source": "ext_acquirer",   "target": "customer_dda_b"},
            {"source": "customer_dda_a", "target": "merchant_dda"},
            {"source": "customer_dda_b", "target": "merchant_dda"},
            {"source": "merchant_dda",   "target": "gl_control"},
            {"source": "gl_control",     "target": "concentration"},
            {"source": "concentration",  "target": "funds_pool"},
            {"source": "customer_dda_a", "target": "gl_control"},
        ],
    }


def _stub_money_trail_fetcher(
    visual_id: str, params: dict[str, str],
) -> dict[str, Any]:
    """Deterministic stub responsive to date + anchor params.

    Two interaction surfaces feed the stub:

    - **date_from / date_to** (form filter) — seed the link
      multipliers (primes 7/11/13/17) so date changes visibly
      shift the ratios.
    - **anchor** (clicked node name) — applies a per-link factor
      keyed off the anchor's character sum. Clicking a different
      node pivots the Sankey ratios in a fresh direction so the
      click-to-trace experiment is visible.

    Both seed and anchor are echoed into the first node label so a
    glance at any swap confirms the round-trip ran with the
    expected params (decouples "did the swap fire?" from "did the
    Sankey shape change?").
    """
    # Branch by visual: the ForceGraph wants a node/link topology,
    # the Sankey wants the date+anchor-keyed flow shape.
    if visual_id == "smoke-force":
        return _stub_rails_accounts()
    seed = sum(ord(c) for c in (params.get("date_from", "") + params.get("date_to", "")))
    anchor = params.get("anchor", "")
    anchor_factor = (sum(ord(c) for c in anchor) % 5 + 1) if anchor else 1
    label = f"seed={seed}, anchor={anchor or 'none'}"
    # L1-layer: keep persona-blind. Real Money Trail Sankey labels
    # come from <prefix>_inv_money_trail_edges (source/target_display)
    # which the L2 instance's persona block populates; the spike just
    # proves the swap pattern, not the labels.
    return {
        "nodes": [
            {"name": f"External Acquirer ({label})"},
            {"name": "Customer DDA"},
            {"name": "GL Control"},
            {"name": "Concentration"},
            {"name": "Funds Pool"},
        ],
        "links": [
            {"source": 0, "target": 1,
             "value": max(10, (seed * 7 * anchor_factor) % 100 + 10)},
            {"source": 1, "target": 2,
             "value": max(10, (seed * 11 * anchor_factor) % 100 + 10)},
            {"source": 2, "target": 3,
             "value": max(10, (seed * 13 * anchor_factor) % 100 + 10)},
            {"source": 3, "target": 4,
             "value": max(10, (seed * 17 * anchor_factor) % 100 + 10)},
        ],
    }


def main() -> int:
    tree_app, sheet = _build_smoke_app()
    asgi_app = make_app(
        tree_app=tree_app,
        sheet=sheet,
        data_fetcher=_stub_money_trail_fetcher,
        # Dev-log on for the smoke server: every HTMX event +
        # d3 click prints to stderr so the developer sees what
        # the browser is doing inline with the server log.
        dev_log=True,
    )
    print("Spike 2 smoke server: http://127.0.0.1:8765/")
    uvicorn.run(asgi_app, host="127.0.0.1", port=8765, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
