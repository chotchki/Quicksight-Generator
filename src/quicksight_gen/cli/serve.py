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

By default ``apply`` wires the real DB-backed fetcher (X.2.a.4) which
hits the configured Postgres / Oracle / SQLite. Pass ``--stub`` to
swap in the deterministic stub from ``_smoke_app.py`` — useful when
iterating on the JS / page shell without a populated database.
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
@click.option(
    "--stub/--no-stub",
    default=False,
    show_default=True,
    help=(
        "Use the deterministic stub fetcher instead of querying the "
        "configured DB. Useful for iterating on the JS / page shell "
        "without a populated database."
    ),
)
@click.option(
    "--app",
    "app_name",
    type=click.Choice(
        ["smoke", "executives", "investigation", "l2_flow_tracing",
         "l1_dashboard"],
    ),
    default="smoke",
    show_default=True,
    help=(
        "Which App2 surface to serve. ``smoke`` is the spike fixture; "
        "``executives`` / ``investigation`` / ``l2_flow_tracing`` / "
        "``l1_dashboard`` build the real tree + wire its datasets "
        "through the generic tree fetcher."
    ),
)
def app2_apply(  # type: ignore[no-untyped-def]: Click decorator strips the function-decorator return type
    config,
    l2_instance_path,
    host: str,
    port: int,
    dev_log: bool,
    stub: bool,
    app_name: str,
) -> None:
    """Start the App2 HTMX/d3 dashboard server.

    Loads the config + L2 instance the same way the json / data /
    audit groups do, builds the App2 tree, and runs uvicorn. The
    visual data comes from the configured DB by default; pass
    ``--stub`` to swap in the deterministic stub fetcher (useful
    when there's no populated database, or when iterating on the
    JS / page shell only).
    """
    # Imported lazily so the CLI module imports cheaply (uvicorn
    # pulls a lot of asyncio + httptools bootstrap into memory) and
    # so a `--help` invocation works without `serve` extras
    # installed.
    import uvicorn  # noqa: PLC0415

    from quicksight_gen.common.html._db_fetcher import (  # noqa: PLC0415
        make_db_fetcher,
    )
    from quicksight_gen.common.html._smoke_app import (  # noqa: PLC0415
        SMOKE_FILTER_SPECS,
        build_smoke_app,
        stub_money_trail_fetcher,
    )
    from quicksight_gen.common.html.server import (  # noqa: PLC0415
        ServedDashboard,
        make_app,
    )
    from quicksight_gen.common.theme import (  # noqa: PLC0415
        resolve_l2_theme,
    )

    cfg, instance = resolve_l2_for_demo(config, l2_instance_path)
    needs_pool = app_name != "smoke"
    if app_name == "smoke":
        tree_app, sheet = build_smoke_app(cfg)
        smoke_filter_specs = SMOKE_FILTER_SPECS
    elif app_name in (
        "executives", "investigation", "l2_flow_tracing", "l1_dashboard",
    ):
        # X.2.g.{1,2} — real tree app via the generic tree fetcher.
        # build_all_datasets(cfg, ...) populates the SQL registry (via
        # build_dataset → register_sql); make_tree_db_fetcher reads
        # that registry at construction time so a missing entry fails
        # loudly here instead of inside a hot HTMX swap.
        if stub:
            raise click.UsageError(
                f"--stub is only supported for --app smoke. The "
                f"{app_name} app needs a real DB."
            )
        if app_name == "executives":
            from quicksight_gen.apps.executives.app import (  # noqa: PLC0415
                build_executives_app,
            )
            from quicksight_gen.apps.executives.datasets import (  # noqa: PLC0415
                build_all_datasets as build_app_datasets,
            )
            # Executives doesn't take l2_instance on build_all_datasets;
            # the per-app build_app_fn does, via the kwarg below.
            build_app_datasets(cfg)
            tree_app = build_executives_app(cfg, l2_instance=instance)
        elif app_name == "investigation":
            from quicksight_gen.apps.investigation.app import (  # noqa: PLC0415
                build_investigation_app,
            )
            from quicksight_gen.apps.investigation.datasets import (  # noqa: PLC0415
                build_all_datasets as build_inv_datasets,
            )
            # Investigation's build_all_datasets requires l2_instance
            # (App Info matview names need the prefix). Mirrors L1 /
            # L2FT signature.
            build_inv_datasets(cfg, instance)
            tree_app = build_investigation_app(cfg, l2_instance=instance)
        elif app_name == "l2_flow_tracing":  # Y.2.app2.cde.l2ft-wiring
            from quicksight_gen.apps.l2_flow_tracing.app import (  # noqa: PLC0415
                build_l2_flow_tracing_app,
            )
            from quicksight_gen.apps.l2_flow_tracing.datasets import (  # noqa: PLC0415
                build_all_l2_flow_tracing_datasets,
            )
            # L2FT's dataset builder requires l2_instance (App Info
            # matview names + the Rails/Chains/Templates pushdown
            # params' declared-value defaults are all L2-derived).
            build_all_l2_flow_tracing_datasets(cfg, instance)
            tree_app = build_l2_flow_tracing_app(cfg, l2_instance=instance)
        else:  # l1_dashboard (Y.2.g)
            from quicksight_gen.apps.l1_dashboard.app import (  # noqa: PLC0415
                build_l1_dashboard_app,
            )
            from quicksight_gen.apps.l1_dashboard.datasets import (  # noqa: PLC0415
                build_all_l1_dashboard_datasets,
            )
            # L1's dataset builder requires l2_instance (matview names
            # + Y.2.g pushdown-param defaults are all L2-derived).
            build_all_l1_dashboard_datasets(cfg, instance)
            tree_app = build_l1_dashboard_app(cfg, l2_instance=instance)

        if tree_app.analysis is None or not tree_app.analysis.sheets:
            raise click.UsageError(
                f"{app_name} app has no analysis sheets — bug in builder."
            )
        sheet = tree_app.analysis.sheets[0]
        smoke_filter_specs = ()
    else:
        # click.Choice(...) above prevents this branch.
        raise click.UsageError(f"Unknown --app value: {app_name!r}")

    theme = resolve_l2_theme(instance)
    if theme is not None:
        click.echo(f"theme: L2-driven ({theme.theme_name})")

    async def _serve() -> None:
        # X.2.g.2.d — keep pool + uvicorn in ONE event loop. Previously
        # ``asyncio.run(make_connection_pool(...))`` opened the psycopg
        # pool in loop A and then ``uvicorn.run()`` started loop B; the
        # pool's background filler task was bound to A and died when B
        # tried to use it ("error connecting in 'pool-1':" on first
        # request). Building the pool inside the same loop that runs
        # ``uvicorn.Server.serve()`` lets the filler keep running.
        pool = None
        if app_name == "smoke":
            if stub:
                fetcher = stub_money_trail_fetcher
                click.echo("data: stub fetcher (deterministic)")
            else:
                fetcher = make_db_fetcher(cfg, instance)
                click.echo(
                    f"data: DB-backed ({cfg.dialect.value}) → "
                    f"{cfg.l2_instance_prefix or instance.instance}"
                    f"_inv_money_trail_edges"
                )
        else:
            from quicksight_gen.common.db import (  # noqa: PLC0415
                make_connection_pool,
            )
            from quicksight_gen.common.html._tree_fetcher import (  # noqa: PLC0415
                make_tree_db_fetcher,
            )
            pool = await make_connection_pool(
                cfg, max_size=cfg.app2_db_pool_size,
            )
            fetcher = make_tree_db_fetcher(tree_app, cfg, pool=pool)
            click.echo(
                f"data: DB-backed ({cfg.dialect.value}) → "
                f"{app_name} tree fetcher "
                f"(prefix={cfg.l2_instance_prefix or instance.instance})"
            )
        try:
            asgi_app = make_app(
                dashboards={
                    app_name: ServedDashboard(
                        tree_app=tree_app,
                        sheet=sheet,
                        title=app_name.title(),
                        data_fetcher=fetcher,
                        theme=theme,
                        filter_specs=smoke_filter_specs,
                    ),
                },
                dev_log=dev_log,
            )
            click.echo(f"App2 server: http://{host}:{port}/")
            if dev_log:
                click.echo("dev-log: on (events forwarded to stderr)")
            config = uvicorn.Config(
                asgi_app, host=host, port=port, log_level="info",
            )
            server = uvicorn.Server(config)
            await server.serve()
        finally:
            if pool is not None:
                await pool.close()

    import asyncio  # noqa: PLC0415

    asyncio.run(_serve())
