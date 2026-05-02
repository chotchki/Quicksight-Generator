"""``quicksight-gen docs`` — mkdocs handbook site for an L2 instance.

Six operations:

  apply       — build the site to ``site/`` (wraps ``mkdocs build``).
  serve       — live-reload preview (wraps ``mkdocs serve``).
  clean       — ``rm -rf site/``.
  test        — pytest the docs gates (link sweep + persona neutrality).
  export      — extract mkdocs source for hand-build (legacy ``export docs``).
  screenshot  — capture deployed dashboards to PNG (legacy ``export screenshots``).

No ``--execute`` here — building a static site to a directory isn't
a destructive side effect. The "emit" and the "do it" are the same
operation.

The ``--l2`` flag is honored via the ``QS_DOCS_L2_INSTANCE`` env var
that ``main.py`` reads at mkdocs-macros define-env time.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from quicksight_gen.cli._helpers import l2_instance_option


_REPO_ROOT = Path(__file__).resolve().parents[3]


@click.group()
def docs() -> None:
    """mkdocs handbook site (build, serve, test, export, screenshot)."""


@docs.command("apply")
@l2_instance_option()
@click.option(
    "-o", "--output", "output",
    type=click.Path(), default="site",
    help="Output directory for the built site (default: site/).",
)
@click.option(
    "--strict/--no-strict", default=True,
    help="Pass --strict to mkdocs (default on; treats warnings as errors).",
)
def docs_apply(
    l2_instance_path: str | None, output: str, strict: bool,
) -> None:
    """Build the docs site to ``site/`` (or ``-o DIR``).

    Wraps ``mkdocs build``. The L2 instance bound via ``--l2`` (or
    falling back to the bundled spec_example) drives every
    ``{{ vocab.* }}`` substitution in the rendered prose.

    No ``--execute``: building a static site IS the operation.
    """
    env = os.environ.copy()
    if l2_instance_path is not None:
        env["QS_DOCS_L2_INSTANCE"] = str(Path(l2_instance_path).resolve())

    cmd = [
        sys.executable, "-m", "mkdocs", "build",
        "-d", str(Path(output).resolve()),
    ]
    if strict:
        cmd.append("--strict")

    click.echo(f"$ {' '.join(cmd)}")
    exit_code = subprocess.call(cmd, cwd=_REPO_ROOT, env=env)
    if exit_code != 0:
        raise click.ClickException(f"mkdocs build failed (exit {exit_code}).")


@docs.command("serve")
@l2_instance_option()
@click.option(
    "--port", "-p", default=8000, show_default=True, type=int,
    help="Port to bind for live-reload preview.",
)
def docs_serve(l2_instance_path: str | None, port: int) -> None:
    """Live-reload preview at http://localhost:PORT (default 8000).

    Wraps ``mkdocs serve``. Edit any docs source file and the browser
    refreshes automatically. Useful for iterating on persona-block
    YAML edits or new walkthrough drafts.
    """
    env = os.environ.copy()
    if l2_instance_path is not None:
        env["QS_DOCS_L2_INSTANCE"] = str(Path(l2_instance_path).resolve())

    cmd = [
        sys.executable, "-m", "mkdocs", "serve",
        "-a", f"127.0.0.1:{port}",
    ]
    click.echo(f"$ {' '.join(cmd)}")
    subprocess.call(cmd, cwd=_REPO_ROOT, env=env)


@docs.command("clean")
@click.option(
    "-o", "--output", "output",
    type=click.Path(), default="site",
    help="Directory to remove (default: site/).",
)
def docs_clean(output: str) -> None:
    """Remove the built site directory."""
    target = Path(output)
    if not target.exists():
        click.echo(f"{target}/ doesn't exist; nothing to clean.")
        return
    shutil.rmtree(target)
    click.echo(f"Removed {target}/")


@docs.command("test")
@click.option(
    "--pytest-args", default="",
    help="Extra args passed verbatim to pytest (e.g. '-k links -v').",
)
def docs_test(pytest_args: str) -> None:
    """Run the docs gates (link sweep + persona-neutral check)."""
    pytest_argv = (
        [sys.executable, "-m", "pytest", "tests/docs/", "-q"]
        + (pytest_args.split() if pytest_args else [])
    )
    pyright_argv = [
        sys.executable, "-m", "pyright",
        "src/quicksight_gen/common/handbook/",
        "main.py",
    ]
    failed = []
    click.echo(f"$ {' '.join(pytest_argv)}")
    if subprocess.call(pytest_argv, cwd=_REPO_ROOT) != 0:
        failed.append("pytest")
    click.echo(f"$ {' '.join(pyright_argv)}")
    if subprocess.call(pyright_argv, cwd=_REPO_ROOT) != 0:
        failed.append("pyright")
    if failed:
        raise click.ClickException(f"docs test failed: {', '.join(failed)}")
    click.echo("docs test: OK")


@docs.command("export")
@click.option(
    "-o", "--output", "output",
    type=click.Path(), required=True,
    help="Target directory; created if missing, merged into if existing.",
)
@click.option(
    "--l2", "l2_instance_path",
    type=click.Path(exists=True),
    help=(
        "Optional path to an L2 institution YAML to bind the rendered "
        "docs against. Validated here; binding happens at mkdocs build "
        "time via QS_DOCS_L2_INSTANCE env var."
    ),
)
def docs_export(output: str, l2_instance_path: str | None) -> None:
    """Copy the bundled mkdocs source to a folder for hand-build.

    Different from ``docs apply``: ``apply`` builds the site INTO a
    directory; ``export`` copies the SOURCE FILES so an integrator
    can use their own mkdocs config / theme / build pipeline.
    """
    from quicksight_gen.cli_legacy import export_docs_cmd
    # Delegate to the existing implementation — same shape as legacy.
    ctx = click.Context(export_docs_cmd)
    ctx.invoke(
        export_docs_cmd, output=output, l2_instance=l2_instance_path,
    )


@docs.command("screenshot")
@click.option(
    "--app",
    type=click.Choice(
        ["l1-dashboard", "l2-flow-tracing", "investigation", "executives", "all"]
    ),
    default="all", show_default=True,
    help="App to capture (or 'all' for every deployed dashboard).",
)
@click.option(
    "--config", "-c",
    type=click.Path(exists=True), default="config.yaml",
    help="Path to configuration file (provides aws_account_id + aws_region).",
)
@click.option(
    "-o", "--output", "output",
    type=click.Path(), required=True,
    help="Output directory; PNG per sheet lands in <output>/<app-slug>/.",
)
@click.option(
    "--viewport", default="1280x900", show_default=True,
    help="Browser viewport WIDTHxHEIGHT (e.g. 1280x900).",
)
def docs_screenshot(
    app: str, config: str, output: str, viewport: str,
) -> None:
    """Capture per-sheet PNG screenshots from deployed dashboards.

    Walks each app's tree via WebKit and writes one full-page PNG
    per sheet to ``<output>/<app-slug>/<sheet_id>.png``.

    Requires the dashboards already deployed (``json apply --execute``).
    The handbook + walkthrough pages embed these screenshots by
    relative path under ``docs/walkthroughs/screenshots/<app>/``.
    """
    from quicksight_gen.cli_legacy import export_screenshots_cmd
    ctx = click.Context(export_screenshots_cmd)
    ctx.invoke(
        export_screenshots_cmd,
        app=app, config=config, output=output, viewport=viewport,
        date_from=None, date_to=None, skip_warmup=False,
        l2_instance=None,
    )
