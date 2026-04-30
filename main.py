"""mkdocs-macros entry point.

mkdocs-macros looks for a top-level ``main.py`` with a
``define_env(env)`` function. We register:

- A ``diagram(family, **kwargs)`` macro that dispatches to the render
  functions in ``quicksight_gen.common.handbook.diagrams``.
- A ``vocab`` Jinja variable populated from
  ``vocabulary_for(l2_instance)`` so any markdown page can substitute
  ``{{ vocab.institution.name }}`` etc.

Both default to the L2 instance at ``QS_DOCS_L2_INSTANCE`` (env var) or
``tests/l2/spec_example.yaml`` if unset. O.2.c (export-docs CLI) lets
the integrator pass an arbitrary L2 path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).parent
_TESTS_L2_DIR = _PROJECT_ROOT / "tests" / "l2"


def define_env(env: Any) -> None:
    """mkdocs-macros entry point.

    ``env`` is the MacroEnvironment; ``env.macro(fn)`` registers a
    callable accessible from any markdown page as ``{{ fn(...) }}``;
    ``env.variables[k] = v`` exposes ``v`` as ``{{ k }}``.
    """
    from quicksight_gen.common.handbook import vocabulary_for
    from quicksight_gen.common.l2.loader import load_instance

    default_l2_path = Path(
        os.environ.get(
            "QS_DOCS_L2_INSTANCE",
            str(_TESTS_L2_DIR / "spec_example.yaml"),
        )
    )
    default_l2 = load_instance(default_l2_path)
    env.variables["vocab"] = vocabulary_for(default_l2)
    env.variables["l2_instance_name"] = str(default_l2.instance)

    @env.macro
    def diagram(family: str, **kwargs: Any) -> str:  # noqa: ARG001
        from quicksight_gen.common.handbook.diagrams import (
            render_conceptual,
            render_dataflow,
            render_l2_topology,
        )

        if family == "conceptual":
            name = kwargs["name"]
            svg = render_conceptual(name)
            return _wrap_svg(svg, alt=f"conceptual diagram: {name}")
        if family == "l2_topology":
            kind = kwargs.get("kind", "accounts")
            l2_path = Path(
                kwargs.get("l2_instance_path", str(default_l2_path))
            )
            l2 = (
                default_l2 if l2_path == default_l2_path else load_instance(l2_path)
            )
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
