"""Starlette ASGI server for the App2 (HTMX) dashboard renderer.

X.2.b shape — all-GET REST surface (no POSTs except dev-log):

- ``GET  /`` — 302 redirect to ``/dashboards``. The dashboards
  list IS the canonical entry; ``/`` is convenience.
- ``GET  /dashboards`` — landing page listing every dashboard the
  server is wired to serve. One link per dashboard, bookmarkable
  per entry.
- ``GET  /dashboards/{dashboard_id}`` — dashboard chrome + the
  served Sheet inline. 404 if the dashboard_id doesn't match
  what was wired.
- ``GET  /dashboards/{dashboard_id}/sheets/{sheet_id}/visuals/{visual_id}/data``
  — chart data fragment for HTMX swap. Filter values arrive as
  query string. GET-not-POST means every (visual, filter-set)
  tuple is a bookmarkable URL.
- ``POST /log`` (dev-only, gated by ``dev_log=True``) — the only
  POST route. Receives forwarded HTMX + d3 click events from the
  browser for live debugging.

The path mirrors the X.2.b REST shape: dashboards / sheets /
visuals nested. Today the server holds one ``dashboard_id`` /
``sheet`` pair (single-app wiring); X.2.b.3 swaps in the multi-
dashboard mapping that fans the listing route + per-dashboard
routes across all 4 apps from one L2 instance.

Pluggable data fetcher
----------------------

The server takes a ``DataFetcher`` callable so the spike + tests
can run without a database:

    def stub_fetcher(visual_id: str, params: dict[str, str]) -> Any:
        return {"nodes": [...], "links": [...]}

    app = make_app(
        tree_app=app, sheet=money_trail,
        dashboard_id="smoke", dashboard_title="Smoke Dashboard",
        data_fetcher=stub_fetcher,
    )

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
from collections.abc import Callable
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


def make_app(
    *,
    tree_app: App,
    sheet: Sheet,
    dashboard_id: str,
    data_fetcher: DataFetcher,
    dashboard_title: str | None = None,
    dev_log: bool = False,
) -> Starlette:
    """Build a Starlette ASGI app that serves a single tree Sheet.

    Args:
        tree_app: tree ``App`` node owning the analysis the sheet
            lives in. Internal IDs are resolved on the first
            ``emit_html`` call (idempotent thereafter).
        sheet: tree ``Sheet`` to serve at
            ``/dashboards/{dashboard_id}``. Must belong to
            ``tree_app.analysis.sheets`` — emit_html raises
            otherwise.
        dashboard_id: URL slug for this dashboard. Used in every
            data path under ``/dashboards/{dashboard_id}/...``.
            Route handlers validate the inbound path matches this
            string; mismatched ids 404. X.2.b.3 will replace the
            single dashboard_id with a mapping when multi-app
            wiring lands.
        data_fetcher: callable invoked on every GET to the visual
            data path. Receives the visual_id and a flat dict of
            query-string params (e.g. ``{"date_from":
            "2026-01-01", "date_to": "2026-05-05"}``). Returns
            d3-shaped chart data.
        dashboard_title: human-readable name shown on the
            ``/dashboards`` listing page. Defaults to
            ``tree_app.name`` so single-dashboard servers don't
            need to repeat themselves.
        dev_log: when True, the page emits a ``<meta
            name="dev-log">`` tag that activates the client-side
            event forwarder + a ``POST /log`` route is registered
            that prints each forwarded event to stderr. Off by
            default — keeps production deploys silent and zero-
            overhead. The developer tool / smoke server enables it.

    Returns:
        A ``starlette.Starlette`` ASGI application.
    """
    sheet_id = str(sheet.sheet_id)
    title = dashboard_title or tree_app.name

    async def index(_request: Request) -> RedirectResponse:
        # ``/`` is a convenience redirect; ``/dashboards`` is the
        # canonical list page. Status 302 (temporary) since which
        # dashboard a future multi-tenant home would land on
        # could shift per-user.
        return RedirectResponse("/dashboards", status_code=302)

    async def dashboards_list(_request: Request) -> HTMLResponse:
        return HTMLResponse(emit_dashboards_list([(dashboard_id, title)]))

    async def dashboard_view(request: Request) -> Response:
        if request.path_params["dashboard_id"] != dashboard_id:
            return Response(status_code=404)
        return HTMLResponse(emit_html(
            tree_app, sheet,
            dashboard_id=dashboard_id, dev_log=dev_log,
        ))

    async def visual_data(request: Request) -> Response:
        # 404 on stale URLs — the path's dashboard_id / sheet_id
        # MUST match what this server is wired for. The visual_id
        # gets validated implicitly (the fetcher raises for
        # unknown ids; that's the per-fetcher contract).
        if request.path_params["dashboard_id"] != dashboard_id:
            return Response(status_code=404)
        if request.path_params["sheet_id"] != sheet_id:
            return Response(status_code=404)
        visual_id = request.path_params["visual_id"]
        params: dict[str, str] = {}
        for key, value in request.query_params.items():
            params[str(key)] = str(value)
        data = data_fetcher(visual_id, params)
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
