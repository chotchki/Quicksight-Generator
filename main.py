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
import shutil
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).parent
_TESTS_L2_DIR = _PROJECT_ROOT / "tests" / "l2"


def _apply_brand_asset_override(
    *,
    docs_dir: Path,
    theme_conf: dict[str, Any],
    kind: str,
    value: str | None,
) -> None:
    """Mutate ``theme_conf[kind]`` from a vetted L2 ``theme.<kind>`` value.

    URLs pass through unchanged. Absolute file paths get copied into
    ``<docs_dir>/img/_l2_<kind><ext>`` and ``theme_conf[kind]`` is set
    to the docs-relative path so mkdocs-material can serve it. The
    underscore prefix on the filename keeps the copied asset out of
    git (``.gitignore`` excludes ``img/_l2_*``).
    """
    if value is None:
        return
    if value.startswith(("http://", "https://", "//")):
        theme_conf[kind] = value
        return
    src = Path(value)
    if not src.is_absolute() or not src.exists():
        # Loader already validated this; the file may have moved/deleted
        # between yaml load and build. Surface clearly.
        raise FileNotFoundError(
            f"L2 theme.{kind} not found at {value!r}; either the path "
            f"moved or the YAML carries a stale reference."
        )
    img_dir = docs_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    dst = img_dir / f"_l2_{kind}{src.suffix}"
    shutil.copy2(src, dst)
    theme_conf[kind] = f"img/{dst.name}"


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
    # Expose the full ``L2Instance`` so generated pages
    # (e.g. ``Training_Story.md``) can iterate accounts / rails /
    # chains / templates / limit_schedules and render their
    # descriptions. The Jinja template walks attributes directly:
    # ``{% for a in l2.accounts %}{{ a.id }}: {{ a.description }}…``.
    env.variables["l2"] = default_l2

    # If the L2 carries inline brand assets, override mkdocs theme.logo
    # / theme.favicon. URLs pass through; absolute paths get copied into
    # docs_dir/img/_l2_<kind><ext> and the theme key is rewritten to
    # the docs-relative path. Without an L2 override no logo/favicon is
    # set — mkdocs.yml carries no defaults so the site renders text-only
    # nav rather than falling back to a persona-specific mark.
    if default_l2.theme is not None:
        docs_dir = Path(env.conf["docs_dir"])
        theme_conf = env.conf["theme"]
        _apply_brand_asset_override(
            docs_dir=docs_dir,
            theme_conf=theme_conf,
            kind="logo",
            value=default_l2.theme.logo,
        )
        _apply_brand_asset_override(
            docs_dir=docs_dir,
            theme_conf=theme_conf,
            kind="favicon",
            value=default_l2.theme.favicon,
        )

    @env.macro
    def diagram(family: str, **kwargs: Any) -> str:  # noqa: ARG001
        """Emit a diagram block for in-browser graphviz WASM rendering.

        Phase T (v8.1.0): every render_* helper now returns the DOT
        source string instead of pre-rendered SVG. We wrap it in a
        ``<script type="text/x-graphviz">`` inside a ``<figure>`` so:
        (1) ``stylesheets/qs-graphviz-wasm.js`` finds the script and
        renders it client-side via ``@hpcc-js/wasm-graphviz``, and
        (2) the existing ``qs-lightbox.js`` click-to-zoom keeps
        working against the figure wrapper unchanged.
        """
        from quicksight_gen.common.handbook.diagrams import (
            render_conceptual,
            render_dataflow,
            render_l2_topology,
        )

        if family == "conceptual":
            name = kwargs["name"]
            dot = render_conceptual(name)
            return _wrap_dot(dot, alt=f"conceptual diagram: {name}")
        if family == "l2_topology":
            kind = kwargs.get("kind", "accounts")
            name = kwargs.get("name")
            l2_path = Path(
                kwargs.get("l2_instance_path", str(default_l2_path))
            )
            l2 = (
                default_l2 if l2_path == default_l2_path else load_instance(l2_path)
            )
            dot = render_l2_topology(l2, kind, name=name)
            return _wrap_dot(
                dot,
                alt=f"L2 topology: {kind}" + (f" / {name}" if name else ""),
            )
        if family == "dataflow":
            app = kwargs["app"]
            dot = render_dataflow(app)
            return _wrap_dot(dot, alt=f"dataflow: {app}")
        raise ValueError(
            f"unknown diagram family {family!r}. "
            f"Expected one of: conceptual, l2_topology, dataflow."
        )

    # -- L2 concept "isolated" diagrams (concepts/l2/*.md) ---------------
    #
    # Each L2 concept page calls one of these macros to render a focused
    # example of that primitive. Auto-pick: try the active L2 first;
    # fall back to bundled spec_example, then sasquatch_pr (covers
    # primitives spec_example doesn't use, e.g. chains). When a fallback
    # fires, the wrapper prepends a callout so the reader knows the
    # example isn't from their institution.
    _spec_example_l2 = load_instance(_TESTS_L2_DIR / "spec_example.yaml")
    _sasquatch_pr_l2 = load_instance(_TESTS_L2_DIR / "sasquatch_pr.yaml")

    def _l2_focus(render_fn, *, primitive: str, alt: str) -> str:
        """Try active → spec_example → sasquatch_pr; wrap with fallback note."""
        active_name = str(default_l2.instance)
        for candidate, label in (
            (default_l2, active_name),
            (_spec_example_l2, "spec_example"),
            (_sasquatch_pr_l2, "sasquatch_pr"),
        ):
            dot = render_fn(candidate)
            if dot is None:
                continue
            wrapped = _wrap_dot(dot, alt=alt)
            if label != active_name:
                callout = (
                    f'<div class="admonition note">'
                    f'<p class="admonition-title">Fallback example</p>'
                    f'<p>The active L2 instance (<code>{active_name}</code>) '
                    f"declares no <code>{primitive}</code> entries; the "
                    f"diagram below is pulled from <code>{label}</code> for "
                    f"illustration.</p></div>"
                )
                return callout + wrapped
            return wrapped
        return (
            f'<div class="admonition warning">'
            f'<p class="admonition-title">No example available</p>'
            f"<p>Neither the active L2 instance nor the shipped fallback "
            f"fixtures declare any <code>{primitive}</code> entries.</p>"
            f"</div>"
        )

    @env.macro
    def l2_account_focus() -> str:
        from quicksight_gen.common.handbook.diagrams import (
            render_l2_account_focus,
        )
        return _l2_focus(
            render_l2_account_focus,
            primitive="accounts", alt="L2 concept: account",
        )

    @env.macro
    def l2_account_template_focus() -> str:
        from quicksight_gen.common.handbook.diagrams import (
            render_l2_account_template_focus,
        )
        return _l2_focus(
            render_l2_account_template_focus,
            primitive="account_templates",
            alt="L2 concept: account template",
        )

    @env.macro
    def l2_rail_focus() -> str:
        from quicksight_gen.common.handbook.diagrams import (
            render_l2_rail_focus,
        )
        return _l2_focus(
            render_l2_rail_focus,
            primitive="rails", alt="L2 concept: rail",
        )

    @env.macro
    def l2_transfer_template_focus() -> str:
        from quicksight_gen.common.handbook.diagrams import (
            render_l2_transfer_template_focus,
        )
        return _l2_focus(
            render_l2_transfer_template_focus,
            primitive="transfer_templates",
            alt="L2 concept: transfer template",
        )

    @env.macro
    def l2_chain_focus() -> str:
        from quicksight_gen.common.handbook.diagrams import (
            render_l2_chain_focus,
        )
        return _l2_focus(
            render_l2_chain_focus,
            primitive="chains", alt="L2 concept: chain",
        )

    @env.macro
    def l2_limit_schedule_focus() -> str:
        from quicksight_gen.common.handbook.diagrams import (
            render_l2_limit_schedule_focus,
        )
        return _l2_focus(
            render_l2_limit_schedule_focus,
            primitive="limit_schedules",
            alt="L2 concept: limit schedule",
        )


def _wrap_dot(dot: str, *, alt: str) -> str:
    """Wrap a graphviz DOT source string in a figure with a render block.

    ``stylesheets/qs-graphviz-wasm.js`` finds every
    ``<script type="text/x-graphviz">`` on the page at load time, runs
    the DOT through ``@hpcc-js/wasm-graphviz``, and inserts the rendered
    SVG into the parent figure. The figure stays as the lightbox /
    accessibility hook (``data-zoomable`` + ``tabindex`` opt it in to
    ``stylesheets/qs-lightbox.js``), so click-to-zoom works against the
    rendered SVG once it lands in the DOM.

    Browser HTML-parser caveat: the DOT source goes inside a
    ``<script type=...>`` (not a ``<pre>``) so any ``<`` / ``>`` /
    ``<br/>`` characters inside reach the WASM renderer verbatim. A
    ``<pre>`` would let the browser interpret them as HTML and mangle
    the source.
    """
    return (
        f'<figure class="qs-diagram" role="img" aria-label="{alt}" '
        f'data-zoomable="true" tabindex="0">\n'
        f'<script type="text/x-graphviz">\n{dot}\n</script>\n'
        f"</figure>"
    )
