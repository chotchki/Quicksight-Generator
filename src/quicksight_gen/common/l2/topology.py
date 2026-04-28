# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
# The `graphviz` package ships no type stubs, so every `Digraph.node()`
# / `.edge()` / `.subgraph()` call type-checks as `Unknown`. The L2-side
# logic (role collection, bundling, label rendering) IS strictly typed;
# only the graphviz-wrapper surface is untyped, and the SVG output is
# the verifiable contract. Suppressing graphviz noise here keeps the
# rest of the L2 module under strict pyright without per-line ignores.
"""Topology diagram render for an ``L2Instance``.

Walks an L2 instance and produces a Graphviz diagram showing the
relationships between L2 primitives — a "what's in this L2?" overview
for an analyst inspecting an unfamiliar institution.

The diagram surfaces:

- **Roles** (nodes): every Role declared on an Account or
  AccountTemplate is one node. Internal vs external scope is styled
  visually (color + shape) so the analyst sees the institutional
  perimeter at a glance.
- **TwoLegRail** (directed edge): ``source_role -> destination_role``.
  Multiple rails between the same (source, destination) pair collapse
  into one bundled edge with a count + comma-joined rail-name label —
  keeps dense instances legible without losing per-rail names.
- **SingleLegRail** (self-loop): a single-leg rail attaches to its
  ``leg_role`` as a self-loop, with the leg direction in the label.
- **TransferTemplate** (cluster + node): each template renders as a
  subgraph cluster grouping the template's ``leg_rails`` (visually as
  template-name node + dotted membership edges to each leg-rail's
  endpoints), so the analyst sees "these N rails fire together as
  one shared Transfer".
- **Chain** (dashed edge): ``parent`` → ``child`` rendered as a dashed
  edge between rail/template nodes with ``required`` + ``xor_group``
  badged in the label.

Designed to stay generic — no persona-specific styling. Theme colors
come from neutral Graphviz defaults; integrators wanting branded output
can post-process the SVG.

Bundling rationale: real-world L2 instances easily declare 8+ rails
between the same (FRB, Customer DDA) pair. Drawing each as its own
edge clutters the graph; collapsing to one labeled edge with the rail
names + count keeps the institutional skeleton readable. The count is
included in the label so high-traffic edges visually pop.

Engines: ``dot`` (default; hierarchical layout — good for chain DAGs);
``neato`` / ``sfdp`` / ``fdp`` / ``twopi`` / ``circo`` available as
fallbacks for force-directed layouts when the graph has many cycles
(common for instances with bidirectional rails between counterparties).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .primitives import (
    Account,
    AccountTemplate,
    ChainEntry,
    Identifier,
    L2Instance,
    Rail,
    Scope,
    SingleLegRail,
    TwoLegRail,
)


# Engines accepted by --engine. Map directly onto Graphviz's bundled
# layout binaries; the dot driver picks the binary based on this name.
_VALID_ENGINES = ("dot", "neato", "sfdp", "fdp", "twopi", "circo")


@dataclass(frozen=True, slots=True)
class _RoleStyle:
    """Per-scope visual styling for a Role node."""

    fill: str
    border: str
    font: str
    shape: str


# Two scopes, two styles. Internal = soft blue (institution-side);
# external = soft yellow (counterparty / outside-the-perimeter). Both
# rounded rectangles for accounts; templates get a different shape so
# the analyst can tell "the role exists as a singleton" from "the role
# is templated and exists in many instances at runtime".
_INTERNAL_STYLE = _RoleStyle(
    fill="#dbe9f6", border="#1f4e79", font="#1f4e79", shape="box",
)
_EXTERNAL_STYLE = _RoleStyle(
    fill="#fff2cc", border="#7f6000", font="#7f6000", shape="box",
)
_TEMPLATE_STYLE = _RoleStyle(
    fill="#e8f0ff", border="#1f4e79", font="#1f4e79", shape="folder",
)
_RAIL_NODE_FILL = "#f5f5f5"
_RAIL_NODE_BORDER = "#666666"
_TRANSFER_TEMPLATE_FILL = "#fce4d6"
_TRANSFER_TEMPLATE_BORDER = "#a6622c"
_CHAIN_EDGE_COLOR = "#5a5a5a"
_BUNDLE_EDGE_COLOR = "#1f4e79"
_SELF_LOOP_COLOR = "#7f6000"


@dataclass(frozen=True, slots=True)
class _BundledEdge:
    """Aggregate of one or more two-leg rails sharing a (src, dst) pair."""

    source: Identifier
    destination: Identifier
    rail_names: tuple[Identifier, ...]
    transfer_types: tuple[str, ...]


def _role_id(role: Identifier) -> str:
    """Graphviz node id for a Role.

    Graphviz accepts most strings but quoting policy varies; the wrapper
    quotes when necessary. Prefixing with ``role__`` avoids collision
    with rail / template / chain node ids.
    """
    return f"role__{role}"


def _rail_id(rail_name: Identifier) -> str:
    """Graphviz node id for a Rail (used by chain edges + template clusters)."""
    return f"rail__{rail_name}"


def _template_id(template_name: Identifier) -> str:
    """Graphviz node id for a TransferTemplate."""
    return f"tmpl__{template_name}"


def _scope_for_role(
    role: Identifier,
    accounts: Iterable[Account],
    templates: Iterable[AccountTemplate],
) -> Scope | None:
    """Return the scope that declares ``role``, or None if undeclared.

    A role is "declared" by an Account or AccountTemplate that names
    it. The same role may appear on both a singleton Account and a
    template — when that happens, the singleton's scope wins (it's the
    more concrete declaration). When neither declares the role (rails
    can reference roles that aren't declared anywhere — invalid per the
    SPEC validator, but the renderer must still degrade gracefully so
    integrators get a useful diagnostic), returns None.
    """
    for account in accounts:
        if account.role == role:
            return account.scope
    for template in templates:
        if template.role == role:
            return template.scope
    return None


def _is_templated(
    role: Identifier,
    templates: Iterable[AccountTemplate],
) -> bool:
    """True if any AccountTemplate declares this role.

    Templated roles are visually distinct (folder shape) from singleton
    roles (box) so the diagram surfaces "this role exists in many
    instances at runtime" without needing the analyst to read a legend.
    """
    return any(t.role == role for t in templates)


def _collect_roles(instance: L2Instance) -> tuple[Identifier, ...]:
    """All roles referenced by accounts, templates, or rails — sorted, deduped.

    Includes roles referenced only by rails (not declared on any
    Account / AccountTemplate) so the diagram still draws them — they
    render with the "undeclared" style as a soft hint at the data
    quality issue. Sorting ensures a stable graph layout across runs
    (the ``dot`` engine is stable for stable input order).
    """
    seen: set[Identifier] = set()
    for account in instance.accounts:
        if account.role is not None:
            seen.add(account.role)
    for template in instance.account_templates:
        seen.add(template.role)
    for rail in instance.rails:
        if isinstance(rail, TwoLegRail):
            seen.update(rail.source_role)
            seen.update(rail.destination_role)
        else:
            seen.update(rail.leg_role)
    return tuple(sorted(seen))


def _bundle_two_leg_rails(
    rails: Iterable[Rail],
) -> tuple[_BundledEdge, ...]:
    """Collapse parallel two-leg rails between the same (src, dst) pair.

    Each TwoLegRail's ``source_role`` / ``destination_role`` is a
    ``RoleExpression`` (tuple of admissible roles) — for the diagram we
    fan out across the cross-product so a rail with
    ``source_role: [A, B]`` and ``destination_role: [C]`` produces
    A→C and B→C bundled edges. This keeps the diagram showing every
    admissible flow path; the integrator can simplify rail definitions
    to collapse if visual density gets too high.

    Bundling key is ``(source, destination)`` so a rail named
    ``ExtInbound`` going A→B and another named ``WireIn`` going A→B
    collapse into one labeled "2 rails: ExtInbound, WireIn" edge.
    Sorting rail names within the bundle keeps the label deterministic.
    """
    pairs: dict[
        tuple[Identifier, Identifier],
        list[tuple[Identifier, str]],
    ] = {}
    for rail in rails:
        if not isinstance(rail, TwoLegRail):
            continue
        for source in rail.source_role:
            for destination in rail.destination_role:
                pairs.setdefault(
                    (source, destination), [],
                ).append((rail.name, rail.transfer_type))
    bundled: list[_BundledEdge] = []
    for (source, destination), entries in sorted(pairs.items()):
        sorted_entries = sorted(entries)
        bundled.append(
            _BundledEdge(
                source=source,
                destination=destination,
                rail_names=tuple(name for name, _ in sorted_entries),
                transfer_types=tuple(tt for _, tt in sorted_entries),
            )
        )
    return tuple(bundled)


def _bundle_label(bundle: _BundledEdge) -> str:
    """Pretty label for a bundled edge — count + rail names + types.

    When only one rail backs the edge, drop the count prefix to avoid
    "1 rail: Foo (ach)" noise. Multi-rail bundles get the count up
    front so visual scan picks out the high-traffic edges.
    """
    rail_count = len(bundle.rail_names)
    type_set = sorted(set(bundle.transfer_types))
    types_str = ", ".join(type_set)
    if rail_count == 1:
        return f"{bundle.rail_names[0]}\n({types_str})"
    rail_str = ", ".join(bundle.rail_names)
    return f"{rail_count} rails: {rail_str}\n({types_str})"


def _self_loop_label(rail: SingleLegRail) -> str:
    """Pretty label for a single-leg rail self-loop."""
    return (
        f"{rail.name}\n"
        f"({rail.transfer_type}, {rail.leg_direction})"
    )


def _chain_label(entry: ChainEntry) -> str:
    """Pretty label for a chain edge — required / xor flagged."""
    parts: list[str] = []
    if entry.required:
        parts.append("required")
    if entry.xor_group is not None:
        parts.append(f"xor: {entry.xor_group}")
    if parts:
        return "chain\n(" + ", ".join(parts) + ")"
    return "chain"


def build_topology_graph(instance: L2Instance) -> Any:
    """Build a Graphviz directed graph capturing the L2 topology.

    Pure construction — no rendering, no I/O. Returns a
    ``graphviz.Digraph`` ready for the caller to ``.render()`` or
    ``.source`` inspect. Typed as ``Any`` because the ``graphviz``
    package ships without type stubs; callers should treat the return
    value as opaque and use ``.render()`` / ``.source`` only.

    Raises ``ImportError`` if the ``graphviz`` Python package isn't
    installed; ``render_topology`` surfaces this as a friendly CLI
    error.
    """
    import graphviz

    # graphviz's stubs are partial / inconsistent across versions; pin
    # graph to Any so strict pyright doesn't trip on Digraph method
    # signatures that move between releases. The CLI surface is the
    # only consumer; SVG output is the verifiable contract.
    graph: Any = graphviz.Digraph(
        name=f"l2_topology_{instance.instance}",
        comment=f"L2 topology for instance '{instance.instance}'",
    )
    graph.attr(rankdir="LR", splines="true", overlap="false")
    graph.attr("node", style="filled,rounded", fontname="Helvetica")
    graph.attr("edge", fontname="Helvetica", fontsize="10")

    # Role nodes — one per role, scope + template-status styled.
    for role in _collect_roles(instance):
        scope = _scope_for_role(
            role, instance.accounts, instance.account_templates,
        )
        templated = _is_templated(role, instance.account_templates)
        style = _style_for(scope, templated)
        graph.node(
            _role_id(role),
            label=role,
            shape=style.shape,
            fillcolor=style.fill,
            color=style.border,
            fontcolor=style.font,
        )

    # Two-leg rails — bundle parallel rails by (source, destination).
    for bundle in _bundle_two_leg_rails(instance.rails):
        graph.edge(
            _role_id(bundle.source),
            _role_id(bundle.destination),
            label=_bundle_label(bundle),
            color=_BUNDLE_EDGE_COLOR,
            penwidth=str(min(1.0 + 0.5 * len(bundle.rail_names), 4.0)),
        )

    # Single-leg rails — self-loop on leg_role. Render across each role
    # in the leg_role expression (matching the two-leg fan-out logic).
    for rail in instance.rails:
        if not isinstance(rail, SingleLegRail):
            continue
        for role in rail.leg_role:
            graph.edge(
                _role_id(role),
                _role_id(role),
                label=_self_loop_label(rail),
                color=_SELF_LOOP_COLOR,
                style="solid",
            )

    # Transfer templates — one cluster per template, with rail-name
    # nodes inside and a dotted edge from each leg-rail node to its
    # corresponding (source, destination) endpoints, surfacing
    # "these rails belong to one shared Transfer".
    for template in instance.transfer_templates:
        cluster_name = f"cluster_tmpl_{template.name}"
        with graph.subgraph(name=cluster_name) as sub:
            assert sub is not None  # graphviz returns subgraph in `with` form
            sub.attr(
                label=f"TransferTemplate: {template.name}\n"
                f"({template.transfer_type})",
                style="dashed,rounded",
                color=_TRANSFER_TEMPLATE_BORDER,
                fontcolor=_TRANSFER_TEMPLATE_BORDER,
                fontname="Helvetica",
                fontsize="11",
            )
            sub.node(
                _template_id(template.name),
                label=f"{template.name}\nkeys: "
                + ", ".join(template.transfer_key),
                shape="component",
                fillcolor=_TRANSFER_TEMPLATE_FILL,
                color=_TRANSFER_TEMPLATE_BORDER,
                fontcolor=_TRANSFER_TEMPLATE_BORDER,
                style="filled",
            )
            for rail_name in template.leg_rails:
                sub.node(
                    _rail_id(rail_name),
                    label=rail_name,
                    shape="ellipse",
                    fillcolor=_RAIL_NODE_FILL,
                    color=_RAIL_NODE_BORDER,
                    fontcolor=_RAIL_NODE_BORDER,
                    style="filled",
                )
                sub.edge(
                    _template_id(template.name),
                    _rail_id(rail_name),
                    style="dotted",
                    color=_TRANSFER_TEMPLATE_BORDER,
                    arrowhead="none",
                )

    # Chains — dashed edges between rail / template nodes.
    # Add stand-alone rail nodes (not already in any template) so the
    # chain edge has somewhere to terminate.
    rails_in_templates: set[Identifier] = set()
    for template in instance.transfer_templates:
        rails_in_templates.update(template.leg_rails)
    chain_referenced: set[Identifier] = set()
    for chain in instance.chains:
        chain_referenced.add(chain.parent)
        chain_referenced.add(chain.child)
    template_names: set[Identifier] = {
        t.name for t in instance.transfer_templates
    }
    for ref in sorted(chain_referenced):
        if ref in template_names or ref in rails_in_templates:
            continue
        graph.node(
            _rail_id(ref),
            label=ref,
            shape="ellipse",
            fillcolor=_RAIL_NODE_FILL,
            color=_RAIL_NODE_BORDER,
            fontcolor=_RAIL_NODE_BORDER,
            style="filled",
        )
    for chain in instance.chains:
        parent_id = (
            _template_id(chain.parent)
            if chain.parent in template_names
            else _rail_id(chain.parent)
        )
        child_id = (
            _template_id(chain.child)
            if chain.child in template_names
            else _rail_id(chain.child)
        )
        graph.edge(
            parent_id,
            child_id,
            label=_chain_label(chain),
            color=_CHAIN_EDGE_COLOR,
            style="dashed",
            fontcolor=_CHAIN_EDGE_COLOR,
        )

    return graph


def _style_for(scope: Scope | None, templated: bool) -> _RoleStyle:
    """Select node style by (scope, is-templated)."""
    if templated:
        return _TEMPLATE_STYLE
    if scope == "external":
        return _EXTERNAL_STYLE
    if scope == "internal":
        return _INTERNAL_STYLE
    # Undeclared role — fall through with the internal style as the
    # least-surprising default. The validator will reject the L2
    # instance separately; the renderer's job is just to not crash.
    return _INTERNAL_STYLE


def render_topology(
    instance: L2Instance,
    output_path: Path,
    *,
    engine: str = "dot",
) -> Path:
    """Render an L2 topology diagram to an SVG file.

    Returns the actual on-disk path of the rendered SVG (Graphviz
    appends the format suffix when missing). Surfaces a friendly
    ``RuntimeError`` when the system ``dot`` binary isn't installed —
    the Python ``graphviz`` package is a wrapper, not a renderer, so
    the binary is the actual dependency that makes/breaks rendering.

    ``engine`` defaults to ``dot`` (hierarchical layout — good for
    chains). Force-directed alternatives ``neato`` / ``sfdp`` / ``fdp``
    / ``twopi`` / ``circo`` are accepted for instances where the
    hierarchical layout reads poorly (lots of bidirectional edges
    between counterparties).

    Raises:
        ImportError: the ``graphviz`` Python package isn't installed.
        ValueError: ``engine`` isn't one of the supported names.
        RuntimeError: the system ``dot`` binary is missing or fails.
    """
    if engine not in _VALID_ENGINES:
        raise ValueError(
            f"engine={engine!r} not supported; pick one of "
            f"{_VALID_ENGINES}"
        )
    try:
        import graphviz
    except ImportError as exc:
        raise ImportError(
            "The 'graphviz' Python package is required for L2 topology "
            "rendering. Install it with: pip install graphviz"
        ) from exc

    graph: Any = build_topology_graph(instance)
    graph.engine = engine

    # graphviz.render() appends the format suffix when the path doesn't
    # already carry it. Strip the suffix from the user-supplied path
    # before passing in, then put it back when reporting the actual
    # output path. This dance avoids the wrapper writing
    # "topology.svg.svg" when the caller passes a path already ending
    # in .svg.
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stem_path = output_path.with_suffix("")

    try:
        rendered: Any = graph.render(
            filename=str(stem_path),
            format="svg",
            cleanup=True,
            quiet=True,
        )
    except graphviz.ExecutableNotFound as exc:
        raise RuntimeError(
            "Graphviz 'dot' binary not found on PATH. Install it with "
            "your system package manager (Homebrew: 'brew install "
            "graphviz'; Debian/Ubuntu: 'apt install graphviz'; "
            "Fedora: 'dnf install graphviz')."
        ) from exc
    except graphviz.CalledProcessError as exc:
        raise RuntimeError(
            f"Graphviz '{engine}' failed to render the L2 topology: {exc}"
        ) from exc

    return Path(rendered)


__all__ = [
    "build_topology_graph",
    "render_topology",
]
