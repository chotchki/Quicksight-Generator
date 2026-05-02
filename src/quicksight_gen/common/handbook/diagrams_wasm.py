"""Phase S spike — graphviz WASM emitter for L2 topology diagrams.

Parallel to ``diagrams.py``'s graphviz/dot pipeline; emits the raw
DOT source string instead of pre-rendered SVG. The mkdocs-macros
``diagram(...)`` entry checks the ``QS_USE_WASM`` env var and
dispatches here when set, then wraps the output in
``<script type="text/x-graphviz">…</script>``. A small JS bootstrap
(``stylesheets/qs-graphviz-wasm.js``) finds those blocks at page-load
time, loads ``@hpcc-js/wasm-graphviz`` from a CDN, and renders them
into SVG client-side.

Crucial design choice: we **reuse the existing ``_build_*_graph``
builders** from ``diagrams.py`` and just call ``.source`` on the
returned ``Digraph`` to extract the DOT string — no `dot` binary
shellout. The Python ``graphviz`` lib's ``Digraph`` class is
pure-Python construction; the system ``dot`` binary only gets invoked
when you call ``.pipe()`` or ``.render()``. Net: we keep all the
existing diagram logic + lose only the build-time SVG render step.

Spike target (per Phase S): the ``kind="accounts"`` diagram on
``/scenario/`` — the same surface where Mermaid+ELK failed the
eyeball test. If WASM-graphviz renders this byte-identically to the
v8.0.x graphviz output, the spike's a pass.
"""

from __future__ import annotations

from quicksight_gen.common.l2.primitives import L2Instance


def render_l2_topology_dot(l2_instance: L2Instance, kind: str) -> str:
    """Build the DOT source for an L2 topology diagram.

    Returns the raw graphviz DOT string. Caller wraps in a
    ``<script type="text/x-graphviz">`` block so the JS shim picks it
    up and renders via WASM.

    Reuses the existing ``_build_*_graph`` builders from
    ``diagrams.py`` — the only difference vs the v8.0.x path is we
    never call ``.pipe()`` (which would shell out to ``dot``).
    """
    from quicksight_gen.common.handbook.diagrams import (
        _build_account_templates_graph,
        _build_accounts_graph,
        _build_chains_graph,
        _build_hierarchy_graph,
        _build_layered_graph,
    )

    builders = {
        "accounts": _build_accounts_graph,
        "account_templates": _build_account_templates_graph,
        "chains": _build_chains_graph,
        "hierarchy": _build_hierarchy_graph,
        "layered": _build_layered_graph,
    }
    if kind not in builders:
        raise ValueError(
            f"WASM emitter not yet implemented for kind={kind!r}. "
            f"Spike target is 'accounts' first."
        )
    g = builders[kind](l2_instance)
    # Digraph.source is the pure-Python DOT construction — no `dot`
    # binary required. The browser-side WASM graphviz takes it from here.
    return g.source
