"""Starlette ASGI server for the App2 (HTMX) dashboard renderer.

X.2.b shape — all-GET REST surface (no POSTs except dev-log):

- ``GET  /`` — 302 redirect to ``/dashboards``. The dashboards
  list IS the canonical entry; ``/`` is convenience.
- ``GET  /dashboards`` — landing page listing every dashboard the
  server is wired to serve. One link per dashboard, bookmarkable
  per entry.
- ``GET  /dashboards/{dashboard_id}`` — dashboard chrome + the
  served Sheet inline. 404 if the dashboard_id isn't in the
  wired ``dashboards`` mapping.
- ``GET  /dashboards/{dashboard_id}/sheets/{sheet_id}/visuals/{visual_id}/data``
  — chart data fragment for HTMX swap. Filter values arrive as
  query string. GET-not-POST means every (visual, filter-set)
  tuple is a bookmarkable URL.
- ``POST /log`` (dev-only, gated by ``dev_log=True``) — the only
  POST route. Receives forwarded HTMX + d3 click events from the
  browser for live debugging.

X.2.b.3: ``make_app`` takes a ``dashboards`` mapping so one server
can host multiple apps. Each value is a ``ServedDashboard`` carrying
its own tree, sheet, title, and data fetcher (different apps query
different matviews via different fetchers). X.2.g wires the four
QS apps (Executives / Investigation / L2 Flow Tracing / L1
Dashboard) into this mapping from one L2 instance.

Pluggable data fetcher
----------------------

Each ``ServedDashboard`` owns a ``DataFetcher`` callable so the
spike + tests can run without a database:

    def stub(visual_id: str, params: dict[str, str]) -> Any:
        return {"nodes": [...], "links": [...]}

    app = make_app(dashboards={
        "smoke": ServedDashboard(
            tree_app=app, sheet=money_trail,
            title="Smoke", data_fetcher=stub,
        ),
    })

Production deploys wire the same callable to a DB-backed factory
(see ``_db_fetcher.make_db_fetcher``).

Stateless on purpose
--------------------

No sessions, no auth, no in-process caching. Each GET executes the
fetcher fresh. Cache-Control headers (X.2.b.4) push caching to
edge / browser layers — the URL IS the cache key, by design.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from quicksight_gen.common.html.render import (
    emit_dashboards_list,
    emit_html,
    emit_visual_data_fragment,
)
from quicksight_gen.common.tree.structure import App, Sheet


# (visual_id, filter_params) → chart data shaped for the visual's
# d3 hydrator. The renderer just JSON-serializes whatever the
# fetcher returns; the per-visual shape contract lives in the
# bootstrap.js renderXxx functions.
DataFetcher = Callable[[str, dict[str, str]], Any]


@dataclass(frozen=True)
class ServedDashboard:
    """One dashboard's wiring for the App2 server.

    Each App2 server holds a mapping ``{dashboard_id: ServedDashboard}``
    so one process can serve multiple apps from one L2 instance
    (X.2.g wires Executives + Investigation + L2FT + L1 from one
    L2). Per-dashboard fetcher means apps that query different
    matviews don't have to share a routing layer.

    Attributes:
        tree_app: tree ``App`` node owning the analysis the sheet
            lives in. Internal IDs are resolved on first emit
            (idempotent).
        sheet: tree ``Sheet`` rendered at ``/dashboards/{id}``. Must
            belong to ``tree_app.analysis.sheets``.
        title: human-readable name for the ``/dashboards`` listing.
        data_fetcher: per-dashboard fetcher invoked on every GET to
            the visual data path. Returns d3-shaped chart data.
    """
    tree_app: App
    sheet: Sheet
    title: str
    data_fetcher: DataFetcher


def make_app(
    *,
    dashboards: Mapping[str, ServedDashboard],
    dev_log: bool = False,
) -> Starlette:
    """Build a Starlette ASGI app serving multiple dashboards.

    Args:
        dashboards: ``{dashboard_id: ServedDashboard}`` mapping.
            One entry per dashboard. The server validates inbound
            path slugs against this mapping; unknown ids 404.
        dev_log: when True, the page emits a ``<meta
            name="dev-log">`` tag that activates the client-side
            event forwarder + a ``POST /log`` route is registered
            that prints each forwarded event to stderr. Off by
            default — keeps production deploys silent and zero-
            overhead. The developer tool / smoke server enables it.

    Returns:
        A ``starlette.Starlette`` ASGI application.
    """
    if not dashboards:
        raise ValueError(
            "make_app requires at least one dashboard in the "
            "`dashboards` mapping."
        )

    # Snapshot the per-dashboard sheet ids so the visual_data
    # handler can validate the URL slug without re-deriving it
    # on every request.
    sheet_ids: dict[str, str] = {
        dash_id: str(d.sheet.sheet_id)
        for dash_id, d in dashboards.items()
    }
    listing: list[tuple[str, str]] = [
        (dash_id, d.title) for dash_id, d in dashboards.items()
    ]

    async def index(_request: Request) -> RedirectResponse:
        # ``/`` is a convenience redirect; ``/dashboards`` is the
        # canonical list page. Status 302 (temporary) since which
        # dashboard a future multi-tenant home would land on
        # could shift per-user.
        return RedirectResponse("/dashboards", status_code=302)

    async def dashboards_list(_request: Request) -> HTMLResponse:
        return HTMLResponse(emit_dashboards_list(listing))

    async def dashboard_view(request: Request) -> Response:
        dash_id = request.path_params["dashboard_id"]
        served = dashboards.get(dash_id)
        if served is None:
            return Response(status_code=404)
        return HTMLResponse(emit_html(
            served.tree_app, served.sheet,
            dashboard_id=dash_id, dev_log=dev_log,
        ))

    async def visual_data(request: Request) -> Response:
        # 404 on stale URLs — both ids must resolve. The visual_id
        # gets validated implicitly (the fetcher raises for
        # unknown ids; that's the per-fetcher contract).
        dash_id = request.path_params["dashboard_id"]
        served = dashboards.get(dash_id)
        if served is None:
            return Response(status_code=404)
        if request.path_params["sheet_id"] != sheet_ids[dash_id]:
            return Response(status_code=404)
        visual_id = request.path_params["visual_id"]
        params: dict[str, str] = {}
        for key, value in request.query_params.items():
            params[str(key)] = str(value)
        data = served.data_fetcher(visual_id, params)
        return HTMLResponse(emit_visual_data_fragment(visual_id, data))

    async def log_event(request: Request) -> Response:
        try:
            payload = await request.json()
        except (json.JSONDecodeError, ValueError):
            payload = {"event": "dev-log:bad-json"}
        # Print to stderr so it interleaves cleanly with uvicorn's
        # access log on stdout. The ``DEV-LOG`` prefix makes
        # forwarded events grep-friendly.
        print(f"DEV-LOG {json.dumps(payload)}", file=sys.stderr, flush=True)
        return Response(status_code=204)

    # Tailwind CSS lives next to this module in assets/; built by
    # ``.venv/bin/tailwindcss -i .../assets/input.css -o
    # .../assets/output.css``. Page shell links it as
    # ``/static/output.css``. Tracked in git so the spike runs
    # without forcing the user to build CSS first.
    assets_dir = Path(__file__).parent / "assets"

    routes: list[Route | Mount] = [
        Route("/", index, methods=["GET"]),
        Route("/dashboards", dashboards_list, methods=["GET"]),
        Route(
            "/dashboards/{dashboard_id}",
            dashboard_view, methods=["GET"],
        ),
        Route(
            "/dashboards/{dashboard_id}/sheets/{sheet_id}"
            "/visuals/{visual_id}/data",
            visual_data,
            methods=["GET"],
        ),
        Mount(
            "/static",
            app=StaticFiles(directory=str(assets_dir)),
            name="static",
        ),
    ]
    if dev_log:
        routes.append(Route("/log", log_event, methods=["POST"]))
    return Starlette(debug=False, routes=routes)
