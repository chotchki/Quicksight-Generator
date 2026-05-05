"""``quicksight-gen serve`` — self-hosted dashboards (App 2).

The serve group ships HTMX/d3 dashboards as a third dialect alongside
QuickSight JSON (``json``) and the audit PDF (``audit``). Each
sub-app hangs off a sub-group:

  app2 apply — start the App2 (HTMX dashboard) server.

X.4 will add ``app1`` (the YAML editor) under the same group.

App2 is a *server*, not a static artifact, so there is no ``--execute``
flag here — starting the server IS the operation, mirroring the
``docs serve`` shape (the ``apply`` verb is kept for surface symmetry
with the other artifact groups).

The fetcher wired here is the deterministic stub from
``common/html/_smoke_app.py`` — X.2.a.4 swaps it for a real
DB-backed factory keyed off the L2 instance + dialect.
"""

from __future__ import annotations

import click

from quicksight_gen.cli._helpers import (
    config_option,
    l2_instance_option,
    resolve_l2_for_demo,
)


@click.group()
def serve() -> None:
    """Self-hosted dashboard servers (App2 = HTMX/d3 renderer)."""


@serve.group("app2")
def app2() -> None:
    """App2 — self-hosted HTMX/d3 dashboards."""


@app2.command("apply")
@config_option(required_for_dialect_only=True)
@l2_instance_option()
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Bind address. Use 0.0.0.0 to expose on the network.",
)
@click.option(
    "--port",
    type=int,
    default=8765,
    show_default=True,
    help="TCP port to listen on.",
)
@click.option(
    "--dev-log/--no-dev-log",
    default=False,
    show_default=True,
    help=(
        "Forward HTMX + d3 click events to stderr for live debugging. "
        "Default off so production deploys stay silent."
    ),
)
def app2_apply(  # type: ignore[no-untyped-def]
    config,
    l2_instance_path,
    host: str,
    port: int,
    dev_log: bool,
) -> None:
    """Start the App2 HTMX/d3 dashboard server.

    Loads the config + L2 instance the same way the json / data /
    audit groups do, builds the App2 tree, and runs uvicorn. Until
    X.2.a.4 lands the real DataFetcher factory, the visual data
    comes from a deterministic stub responsive to the date-range
    form + click-anchor. Useful for iterating on the JS / page
    shell without a populated database.
    """
    # Imported lazily so the CLI module imports cheaply (uvicorn
    # pulls a lot of asyncio + httptools bootstrap into memory) and
    # so a `--help` invocation works without `serve` extras
    # installed.
    import uvicorn  # noqa: PLC0415

    from quicksight_gen.common.html._smoke_app import (  # noqa: PLC0415
        build_smoke_app,
        stub_money_trail_fetcher,
    )
    from quicksight_gen.common.html.server import make_app  # noqa: PLC0415

    cfg, _instance = resolve_l2_for_demo(config, l2_instance_path)
    tree_app, sheet = build_smoke_app(cfg)
    asgi_app = make_app(
        tree_app=tree_app,
        sheet=sheet,
        data_fetcher=stub_money_trail_fetcher,
        dev_log=dev_log,
    )
    click.echo(f"App2 server: http://{host}:{port}/")
    if dev_log:
        click.echo("dev-log: on (events forwarded to stderr)")
    uvicorn.run(asgi_app, host=host, port=port, log_level="info")
