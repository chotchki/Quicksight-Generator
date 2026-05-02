"""``quicksight-gen audit`` — PDF reconciliation report.

Three operations:

  apply  — emit Markdown source for the report (default), or
           ``--execute`` to write a PDF via reportlab.
  clean  — list the report file that would be removed (default), or
           ``--execute`` to delete it.
  test   — pytest the audit module + pyright.

The report is a regulator-ready PDF generated **directly from the
database**, querying the per-prefix L1 invariant matviews + base
tables. Same emit-vs-execute pattern as the other artifact groups —
no ``--execute`` means the integrator can review the rendered
Markdown / page outline before committing to a real PDF write.

Phase U.0 ships the **skeleton only**: a one-page reportlab PDF that
says "Phase U skeleton — institution: {name}, period: {from}–{to}".
Real per-invariant tables, the per-account-day Daily Statement walk,
and the provenance hash land in U.1–U.7.

Period default: ``yesterday + last 7 days`` (a 7-day window ending
yesterday). Override with ``--from YYYY-MM-DD`` / ``--to YYYY-MM-DD``.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import click

from quicksight_gen.cli._helpers import (
    config_option,
    execute_option,
    l2_instance_option,
    resolve_l2_for_demo,
)


@click.group()
def audit() -> None:
    """Per-instance PDF reconciliation report (cover, summary, exceptions)."""


def _period_option_from():  # type: ignore[no-untyped-def]
    return click.option(
        "--from", "period_from",
        type=click.DateTime(formats=["%Y-%m-%d"]), default=None,
        help=(
            "Period start (YYYY-MM-DD, inclusive). Default: today − 7 days "
            "(start of the 7-day window ending yesterday)."
        ),
    )


def _period_option_to():  # type: ignore[no-untyped-def]
    return click.option(
        "--to", "period_to",
        type=click.DateTime(formats=["%Y-%m-%d"]), default=None,
        help=(
            "Period end (YYYY-MM-DD, inclusive). Default: yesterday "
            "(today − 1)."
        ),
    )


def _resolve_period(
    period_from: datetime | None, period_to: datetime | None,
    *, today: date | None = None,
) -> tuple[date, date]:
    """Resolve the report period.

    Default: a 7-day window ending yesterday — i.e. ``[today − 7,
    today − 1]`` inclusive. Both endpoints are inclusive dates.
    Override either endpoint via ``--from`` / ``--to``.
    """
    anchor = today or date.today()
    end = period_to.date() if period_to is not None else anchor - timedelta(days=1)
    start = period_from.date() if period_from is not None else anchor - timedelta(days=7)
    if start > end:
        raise click.UsageError(
            f"--from ({start.isoformat()}) must not be after --to "
            f"({end.isoformat()})."
        )
    return start, end


def _institution_name(instance) -> str:  # type: ignore[no-untyped-def]
    """Pull the institution display name from the L2 persona block.

    Falls back to the L2 instance identifier when no persona block is
    declared — the report still renders cleanly against any L2 YAML.
    """
    persona = getattr(instance, "persona", None)
    if persona is not None and persona.institution:
        return str(persona.institution[0])
    return str(instance.instance)


@audit.command("apply")
@l2_instance_option()
@config_option(required_for_dialect_only=True)
@_period_option_from()
@_period_option_to()
@click.option(
    "-o", "--output", "output",
    type=click.Path(), default=None,
    help=(
        "Output path. Without --execute: Markdown source destination "
        "(default: stdout). With --execute: PDF destination "
        "(default: report.pdf)."
    ),
)
@execute_option()
def audit_apply(
    l2_instance_path: str | None,
    config: str,
    period_from: datetime | None,
    period_to: datetime | None,
    output: str | None,
    execute: bool,
) -> None:
    """Emit the audit report's Markdown source (or ``--execute`` to write a PDF).

    Default: print the Markdown rendering of the report (cover +
    section outline) to stdout. Pass ``-o FILE`` to write to a file.
    Useful for review before committing to a PDF.

    Pass ``--execute`` to render the report as a PDF via reportlab.
    Default destination is ``report.pdf`` in the current working
    directory; override with ``-o FILE``.

    Phase U.0 ships the skeleton: cover-page placeholder + a stub
    body. Real content (executive summary, per-invariant tables,
    Daily Statement walk) lands in U.1+ as the page-by-page review
    gates close.
    """
    _cfg, instance = resolve_l2_for_demo(config, l2_instance_path)
    start, end = _resolve_period(period_from, period_to)
    institution = _institution_name(instance)
    generated_at = datetime.now()

    if execute:
        out_path = Path(output) if output is not None else Path("report.pdf")
        _write_skeleton_pdf(
            out_path,
            institution=institution,
            period=(start, end),
            generated_at=generated_at,
        )
        click.echo(
            f"Wrote audit report skeleton to {out_path} "
            f"(institution={institution}, period={start}–{end})."
        )
        return

    markdown = _render_skeleton_markdown(
        institution=institution,
        period=(start, end),
        generated_at=generated_at,
    )
    if output is None:
        click.echo(markdown, nl=False)
        return
    Path(output).write_text(markdown, encoding="utf-8")
    click.echo(
        f"Wrote audit Markdown source to {output} "
        f"({len(markdown)} bytes).",
        err=True,
    )


@audit.command("clean")
@click.option(
    "-o", "--output", "output",
    type=click.Path(), default="report.pdf",
    help="PDF path to remove (default: report.pdf).",
)
@execute_option()
def audit_clean(output: str, execute: bool) -> None:
    """Print or remove the generated report file.

    Default: print the path that would be deleted (no side effect).
    Pass ``--execute`` to actually unlink it.
    """
    target = Path(output)
    if not target.exists():
        click.echo(f"{target} doesn't exist; nothing to clean.")
        return
    if not execute:
        click.echo(f"Would delete: {target}")
        return
    target.unlink()
    click.echo(f"Removed {target}")


@audit.command("test")
@click.option(
    "--pytest-args", default="",
    help="Extra args passed verbatim to pytest (e.g. '-k smoke').",
)
def audit_test(pytest_args: str) -> None:
    """Run the audit test suite (pytest + pyright on cli/audit.py)."""
    pytest_argv = (
        [sys.executable, "-m", "pytest", "tests/audit/", "-q"]
        + (pytest_args.split() if pytest_args else [])
    )
    pyright_argv = [
        sys.executable, "-m", "pyright",
        "src/quicksight_gen/cli/audit.py",
    ]
    failed = []
    click.echo(f"$ {' '.join(pytest_argv)}")
    if subprocess.call(pytest_argv) != 0:
        failed.append("pytest")
    click.echo(f"$ {' '.join(pyright_argv)}")
    if subprocess.call(pyright_argv) != 0:
        failed.append("pyright")
    if failed:
        raise click.ClickException(f"audit test failed: {', '.join(failed)}")
    click.echo("audit test: OK")


# -- Renderers (skeleton — replaced page-by-page in U.1+) ---------------------


def _render_skeleton_markdown(
    *,
    institution: str,
    period: tuple[date, date],
    generated_at: datetime,
) -> str:
    """Skeleton-mode Markdown rendering.

    U.1 will replace this with the real cover-page Markdown; U.2+ add
    the body sections. For U.0 the Markdown emit is a single section
    that confirms the CLI loaded the L2 instance, resolved the period,
    and captured the generation timestamp.
    """
    start, end = period
    return (
        "# QuickSight Generator audit report (Phase U.0 skeleton)\n"
        "\n"
        f"- **Institution:** {institution}\n"
        f"- **Period:** {start.isoformat()} – {end.isoformat()} (inclusive)\n"
        f"- **Generated:** {generated_at.isoformat(timespec='seconds')}\n"
        "\n"
        "_Real content (executive summary, per-invariant tables, "
        "Daily Statement walk, provenance hash) lands in Phase U.1+. "
        "This skeleton confirms the CLI shape + L2 instance binding._\n"
    )


def _write_skeleton_pdf(
    path: Path,
    *,
    institution: str,
    period: tuple[date, date],
    generated_at: datetime,
) -> None:
    """Skeleton-mode reportlab PDF.

    Minimal one-page output that proves reportlab is wired up + the
    L2 metadata + period + generation timestamp threaded through. U.1
    replaces this with the real cover page; U.2+ append the body
    sections.
    """
    # Imported lazily so the audit CLI loads even when the [audit]
    # extra isn't installed — only --execute paths need reportlab.
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="QuickSight Generator audit report (Phase U.0 skeleton)",
    )
    styles = getSampleStyleSheet()
    start, end = period
    story = [
        Paragraph(
            "QuickSight Generator audit report",
            styles["Title"],
        ),
        Paragraph(
            "<i>Phase U.0 skeleton</i>",
            styles["Italic"],
        ),
        Spacer(1, 0.4 * inch),
        Paragraph(f"<b>Institution:</b> {institution}", styles["BodyText"]),
        Paragraph(
            f"<b>Period:</b> {start.isoformat()} &ndash; {end.isoformat()} "
            "(inclusive)",
            styles["BodyText"],
        ),
        Paragraph(
            f"<b>Generated:</b> {generated_at.isoformat(timespec='seconds')}",
            styles["BodyText"],
        ),
        Spacer(1, 0.5 * inch),
        Paragraph(
            "<i>Real content (executive summary, per-invariant tables, "
            "per-account-day Daily Statement walk, provenance hash) lands "
            "in Phase U.1+. This skeleton confirms the CLI shape + L2 "
            "instance binding + reportlab pipeline.</i>",
            styles["BodyText"],
        ),
    ]
    doc.build(story)
