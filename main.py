"""mkdocs-macros entry point.

mkdocs-macros looks for a top-level ``main.py`` with a
``define_env(env)`` function. We register a single ``diagram(...)``
macro that dispatches to the render functions in
``quicksight_gen.common.handbook.diagrams``.

Diagram families:

- ``{{ diagram("l2_topology", kind="accounts") }}`` — accounts +
  rails (kinds: "accounts" / "chains" / "layered").
- ``{{ diagram("dataflow", app="l1_dashboard") }}`` — per-app
  dataflow (which datasets feed which sheets).
- ``{{ diagram("conceptual", name="double-entry") }}`` — hand-authored
  ``.dot`` from ``src/quicksight_gen/docs/_diagrams/conceptual/``.

The L2 instance defaulted into ``l2_topology`` / ``dataflow`` is
``spec_example``; O.2.c (export-docs CLI) lets the integrator
override.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).parent
_TESTS_L2_DIR = _PROJECT_ROOT / "tests" / "l2"


def define_env(env: Any) -> None:
    """mkdocs-macros entry point.

    ``env`` is the MacroEnvironment; ``env.macro(fn)`` registers a
    callable accessible from any markdown page as ``{{ fn(...) }}``.
    """

    @env.macro
    def diagram(family: str, **kwargs: Any) -> str:  # noqa: ARG001
        from quicksight_gen.common.handbook.diagrams import (
            render_conceptual,
            render_dataflow,
            render_l2_topology,
        )
        from quicksight_gen.common.l2.loader import load_instance

        if family == "conceptual":
            name = kwargs["name"]
            svg = render_conceptual(name)
            return _wrap_svg(svg, alt=f"conceptual diagram: {name}")
        if family == "l2_topology":
            kind = kwargs.get("kind", "accounts")
            l2_path = kwargs.get(
                "l2_instance_path", _TESTS_L2_DIR / "spec_example.yaml"
            )
            l2 = load_instance(Path(l2_path))
            svg = render_l2_topology(l2, kind)
            return _wrap_svg(svg, alt=f"L2 topology: {kind}")
        if family == "dataflow":
            app = kwargs["app"]
            svg = render_dataflow(app)
            return _wrap_svg(svg, alt=f"dataflow: {app}")
        raise ValueError(
            f"unknown diagram family {family!r}. "
            f"Expected one of: conceptual, l2_topology, dataflow."
        )


def _wrap_svg(svg: str, *, alt: str) -> str:
    """Wrap inline SVG in a figure block so md_in_html lays it out cleanly."""
    return (
        f'<figure class="qs-diagram" role="img" aria-label="{alt}">\n'
        f"{svg}\n"
        f"</figure>"
    )
