"""Diagram render pipeline for the unified mkdocs site.

Three diagram families:

1. **L2-driven topology** (``render_l2_topology``) — accounts + rails +
   chains laid out from the loaded ``L2Instance``. Cuts: ``accounts``
   (account-rail-account edges), ``chains`` (parent → child DAG over
   rails / transfer templates), ``layered`` (both, layered).

2. **Per-app dataflow** (``render_dataflow``) — which datasets feed
   which sheets, walked off the typed ``App`` tree. One per app's
   reference page.

3. **Hand-authored conceptual** (``render_conceptual``) — reads a
   ``.dot`` file from ``docs/_diagrams/conceptual/`` and renders it.
   Used for the narrative concept pages where the diagram is a
   teaching aid that doesn't derive from any L2 data (double-entry,
   escrow-with-reversal, sweep-net-settle, etc.).

All three return inline SVG (XML declaration stripped) so an
mkdocs-macros call like ``{{ diagram("conceptual", name="double-entry") }}``
embeds directly into the markdown via the ``md_in_html`` extension.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import graphviz

from quicksight_gen.common.l2.primitives import (
    Account,
    AccountTemplate,
    ChainEntry,
    L2Instance,
    Rail,
    SingleLegRail,
    TwoLegRail,
)


# -- Public API --------------------------------------------------------------


TopologyKind = Literal[
    "accounts", "account_templates", "chains", "layered", "hierarchy",
]


def render_l2_topology(l2_instance: L2Instance, kind: TopologyKind) -> str:
    """Render an L2 instance's structure as an inline SVG.

    ``kind="accounts"`` shows every Account as a node and every Rail as
    an edge between source-role-account and destination-role-account.
    Single-leg rails draw a self-loop on the leg-role account so they
    show up at all.

    ``kind="account_templates"`` mirrors the accounts diagram but with
    ``AccountTemplate`` nodes (keyed by role) instead of singleton
    Accounts. Rails whose ``source_role`` / ``destination_role`` /
    ``leg_role`` reference a template's role get edges to those template
    nodes; rails whose roles touch no template are excluded — this
    diagram is the "what does the template-shape graph look like?" view,
    not the full topology.

    ``kind="chains"`` shows every Rail / TransferTemplate the chains
    table references, with ``parent → child`` edges (XOR groups
    rendered as a shared cluster). Required edges drawn solid; optional
    edges dashed.

    ``kind="layered"`` lays the accounts diagram on top of the chains
    diagram in two ranks — the accounts row at the top, the chains row
    below.

    ``kind="hierarchy"`` shows the parent → child rollup of singleton
    accounts and account templates. Each node is an Account or
    AccountTemplate; an edge points from a child to its parent
    (resolved by ``child.parent_role == parent.role``). Singleton
    accounts have solid borders; account templates carry dashed
    borders since they're a SHAPE, not an instance.
    """
    if kind == "accounts":
        return _to_svg(_build_accounts_graph(l2_instance))
    if kind == "account_templates":
        return _to_svg(_build_account_templates_graph(l2_instance))
    if kind == "chains":
        return _to_svg(_build_chains_graph(l2_instance))
    if kind == "layered":
        return _to_svg(_build_layered_graph(l2_instance))
    if kind == "hierarchy":
        return _to_svg(_build_hierarchy_graph(l2_instance))
    raise ValueError(f"unknown topology kind: {kind!r}")


def render_l2_account_focus(l2_instance: L2Instance) -> str | None:
    """Render the first singleton Account with its parent edge (if any).

    Returns None if the instance has no singleton accounts. Caller (the
    mkdocs-macros entry) handles the fallback to ``spec_example``.
    """
    if not l2_instance.accounts:
        return None
    acc = l2_instance.accounts[0]
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="BT", nodesep="0.4", ranksep="0.7")
    g.attr("node", fontsize="11", style="filled")
    _add_account_node(g, acc)
    if acc.parent_role is not None:
        parent = _role_to_account(l2_instance).get(str(acc.parent_role))
        if parent is not None:
            _add_account_node(g, parent)
            g.edge(str(acc.id), str(parent.id), color="#666666")
    return _to_svg(g)


def render_l2_account_template_focus(l2_instance: L2Instance) -> str | None:
    """Render the first AccountTemplate with its parent singleton."""
    if not l2_instance.account_templates:
        return None
    template = l2_instance.account_templates[0]
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="BT", nodesep="0.4", ranksep="0.7")
    g.attr("node", fontsize="11", style="filled")
    _add_account_template_node(g, template)
    if template.parent_role is not None:
        parent = _role_to_account(l2_instance).get(str(template.parent_role))
        if parent is not None:
            _add_account_node(g, parent)
            g.edge(_template_node_id(template), str(parent.id), color="#666666")
    return _to_svg(g)


def render_l2_rail_focus(l2_instance: L2Instance) -> str | None:
    """Render the first Rail with its endpoint accounts.

    For TwoLeg, source + destination side-by-side with the rail edge
    between them. For SingleLeg, the leg-role account with a self-loop
    edge.
    """
    if not l2_instance.rails:
        return None
    rail = l2_instance.rails[0]
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="LR", nodesep="0.5", ranksep="1.0")
    g.attr("node", fontsize="11", style="filled")
    role_to_account = _role_to_account(l2_instance)
    if isinstance(rail, TwoLegRail):
        sources = _expand_role_expression(rail.source_role)
        destinations = _expand_role_expression(rail.destination_role)
        for r in (*sources, *destinations):
            acc = role_to_account.get(r)
            if acc is not None:
                _add_account_node(g, acc)
    elif isinstance(rail, SingleLegRail):
        for r in _expand_role_expression(rail.leg_role):
            acc = role_to_account.get(r)
            if acc is not None:
                _add_account_node(g, acc)
    _add_rail_edges(g, rail, role_to_account)
    return _to_svg(g)


def render_l2_transfer_template_focus(l2_instance: L2Instance) -> str | None:
    """Render the first TransferTemplate as a chain of leg rails.

    Each leg becomes a node labeled with its rail_name; edges connect
    them in declaration order. The template name + ``expected_net``
    sit in the graph label.
    """
    if not l2_instance.transfer_templates:
        return None
    template = l2_instance.transfer_templates[0]
    g = graphviz.Digraph(format="svg")
    g.attr(
        rankdir="LR", nodesep="0.4", ranksep="0.9",
        label=f"{template.name}  (expected_net={template.expected_net})",
        labelloc="t", fontsize="12",
    )
    g.attr(
        "node", fontsize="11", shape="box",
        style="filled,rounded", fillcolor="#e0f7fa",
    )
    rails_by_name = {str(r.name): r for r in l2_instance.rails}
    prev: str | None = None
    for idx, leg in enumerate(template.leg_rails):
        rail_name = str(leg)
        node_id = f"leg_{idx}_{rail_name}"
        rail = rails_by_name.get(rail_name)
        if isinstance(rail, TwoLegRail):
            kind = "TwoLeg"
        elif isinstance(rail, SingleLegRail):
            kind = "SingleLeg"
        else:
            kind = ""
        label = f"{rail_name}\n({kind})" if kind else rail_name
        g.node(node_id, label)
        if prev is not None:
            g.edge(prev, node_id, color="#666666")
        prev = node_id
    return _to_svg(g)


def render_l2_chain_focus(l2_instance: L2Instance) -> str | None:
    """Render the first ChainEntry with both endpoints labeled.

    Endpoint nodes are coloured by kind (rail vs template vs unresolved).
    Edge style + label match the same conventions as the full chains
    diagram (solid=required, dashed=optional, xor group label).
    """
    if not l2_instance.chains:
        return None
    chain = l2_instance.chains[0]
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="LR", nodesep="0.4", ranksep="0.9")
    g.attr("node", fontsize="11", shape="box", style="filled,rounded")

    rails_by_name = {str(r.name) for r in l2_instance.rails}
    templates_by_name = {str(t.name) for t in l2_instance.transfer_templates}

    def _add_endpoint(ref: object) -> None:
        ref_id = str(ref)
        if ref_id in rails_by_name:
            g.node(ref_id, ref_id, fillcolor="#e0f7fa")
        elif ref_id in templates_by_name:
            g.node(ref_id, f"{ref_id}\n(template)", fillcolor="#fff9c4")
        else:
            g.node(ref_id, ref_id, fillcolor="#f5f5f5")

    _add_endpoint(chain.parent)
    _add_endpoint(chain.child)
    _add_chain_edge(g, chain)
    return _to_svg(g)


def render_l2_limit_schedule_focus(l2_instance: L2Instance) -> str | None:
    """Render the first LimitSchedule as a (parent_role, transfer_type) → cap.

    Visual: a parent-role node on the left with a labeled edge to a
    "cap" node showing the daily flow ceiling. Conceptual rather than
    topological since LimitSchedules are configuration, not topology.
    """
    if not l2_instance.limit_schedules:
        return None
    sched = l2_instance.limit_schedules[0]
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="LR", nodesep="0.4", ranksep="1.0")
    g.attr("node", fontsize="11", style="filled")

    role_node = f"role_{sched.parent_role}"
    cap_node = f"cap_{sched.parent_role}_{sched.transfer_type}"
    g.node(
        role_node, f"role: {sched.parent_role}",
        shape="box", fillcolor="#bbdefb",
    )
    g.node(
        cap_node, f"daily cap\n{sched.cap}",
        shape="cylinder", fillcolor="#ffe0b2",
    )
    g.edge(
        role_node, cap_node,
        label=f"transfer_type:\n{sched.transfer_type}",
        fontsize="9", color="#666666",
    )
    return _to_svg(g)


def render_dataflow(app_name: str) -> str:
    """Render which datasets feed which sheets for ``app_name``.

    Reads the typed ``App`` tree's emitted analysis structure — every
    Visual carries its dataset reference, so the dataflow is a fan-in
    graph: datasets on the left, sheets on the right, edges from a
    dataset to every sheet it feeds.
    """
    from quicksight_gen.common.tree.structure import App

    app = _build_app(app_name)
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="LR", nodesep="0.4", ranksep="1.2")
    g.attr("node", fontsize="11")

    datasets_seen: set[str] = set()
    edges: set[tuple[str, str]] = set()
    for sheet in app.analysis.sheets:
        sheet_id = f"sheet::{sheet.name}"
        g.node(
            sheet_id,
            sheet.name,
            shape="box",
            style="filled,rounded",
            fillcolor="#e3f2fd",
        )
        for visual in sheet.visuals:
            ds = getattr(visual, "dataset", None)
            if ds is None:
                continue
            ds_id = f"ds::{ds.identifier}"
            if ds_id not in datasets_seen:
                g.node(
                    ds_id,
                    ds.identifier,
                    shape="cylinder",
                    style="filled",
                    fillcolor="#fff3e0",
                )
                datasets_seen.add(ds_id)
            edges.add((ds_id, sheet_id))

    for ds_id, sheet_id in sorted(edges):
        g.edge(ds_id, sheet_id, color="#666666")

    return _to_svg(g)


def render_conceptual(name: str) -> str:
    """Render a hand-authored ``.dot`` file from the conceptual catalog.

    Reads ``docs/_diagrams/conceptual/<name>.dot`` and pipes it through
    Graphviz. ``KeyError`` if the named diagram doesn't exist — surfaces
    in the mkdocs build with a clear "no such conceptual diagram" line.
    """
    dot_path = _CONCEPTUAL_DIR / f"{name}.dot"
    if not dot_path.exists():
        available = sorted(p.stem for p in _CONCEPTUAL_DIR.glob("*.dot"))
        raise KeyError(
            f"No conceptual diagram named {name!r}. "
            f"Available: {', '.join(available) or '(none)'}."
        )
    source = dot_path.read_text(encoding="utf-8")
    g = graphviz.Source(source, format="svg")
    return _to_svg(g)


# -- L2 graph builders -------------------------------------------------------


def _build_accounts_graph(l2_instance: L2Instance) -> graphviz.Digraph:
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="LR", nodesep="0.5", ranksep="1.0")
    g.attr("node", fontsize="11", style="filled")

    role_to_account = _role_to_account(l2_instance)
    for acc in l2_instance.accounts:
        _add_account_node(g, acc)

    for rail in l2_instance.rails:
        _add_rail_edges(g, rail, role_to_account)
    return g


def _build_account_templates_graph(l2_instance: L2Instance) -> graphviz.Digraph:
    """Mirror of the accounts graph using AccountTemplate nodes by role.

    Renders each ``AccountTemplate`` as a dashed-border node (the same
    shape used by the hierarchy diagram for templates) keyed by role,
    then draws rail edges between template-role nodes. Rails whose
    source / destination / leg roles touch no template are excluded —
    this diagram is intentionally narrower than the singleton accounts
    view, surfacing only the template-shape topology.
    """
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="LR", nodesep="0.5", ranksep="1.0")
    g.attr("node", fontsize="11", style="filled")

    template_roles = {str(t.role) for t in l2_instance.account_templates}
    role_to_template = _role_to_template(l2_instance)
    for template in l2_instance.account_templates:
        _add_account_template_node(g, template)

    for rail in l2_instance.rails:
        _add_template_rail_edges(g, rail, template_roles, role_to_template)
    return g


def _build_chains_graph(l2_instance: L2Instance) -> graphviz.Digraph:
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="LR", nodesep="0.4", ranksep="0.9")
    g.attr("node", fontsize="11", shape="box", style="filled,rounded")

    referenced_ids: set[str] = set()
    for chain in l2_instance.chains:
        referenced_ids.add(str(chain.parent))
        referenced_ids.add(str(chain.child))

    rails_by_name = {str(r.name): r for r in l2_instance.rails}
    templates_by_name = {str(t.name): t for t in l2_instance.transfer_templates}

    for ref_id in sorted(referenced_ids):
        if ref_id in rails_by_name:
            g.node(ref_id, ref_id, fillcolor="#e0f7fa")
        elif ref_id in templates_by_name:
            g.node(ref_id, f"{ref_id} (template)", fillcolor="#fff9c4")
        else:
            g.node(ref_id, ref_id, fillcolor="#f5f5f5")

    for chain in l2_instance.chains:
        _add_chain_edge(g, chain)
    return g


def _build_layered_graph(l2_instance: L2Instance) -> graphviz.Digraph:
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="TB", nodesep="0.4", ranksep="1.4")

    with g.subgraph(name="cluster_accounts") as c:
        c.attr(label="Accounts + Rails", style="rounded", color="#90caf9")
        c.attr("node", fontsize="11", style="filled")
        role_to_account = _role_to_account(l2_instance)
        for acc in l2_instance.accounts:
            _add_account_node(c, acc)
        for rail in l2_instance.rails:
            _add_rail_edges(c, rail, role_to_account)

    with g.subgraph(name="cluster_chains") as c:
        c.attr(label="Chains", style="rounded", color="#a5d6a7")
        c.attr(
            "node", fontsize="11", shape="box", style="filled,rounded"
        )
        rails_by_name = {str(r.name) for r in l2_instance.rails}
        templates_by_name = {str(t.name) for t in l2_instance.transfer_templates}
        seen: set[str] = set()
        for chain in l2_instance.chains:
            for ref in (chain.parent, chain.child):
                ref_id = str(ref)
                if ref_id in seen:
                    continue
                seen.add(ref_id)
                if ref_id in rails_by_name:
                    c.node(f"chain::{ref_id}", ref_id, fillcolor="#e0f7fa")
                elif ref_id in templates_by_name:
                    c.node(
                        f"chain::{ref_id}",
                        f"{ref_id} (template)",
                        fillcolor="#fff9c4",
                    )
                else:
                    c.node(f"chain::{ref_id}", ref_id, fillcolor="#f5f5f5")
        for chain in l2_instance.chains:
            style = "solid" if chain.required else "dashed"
            label = chain.xor_group and f"xor: {chain.xor_group}" or ""
            c.edge(
                f"chain::{chain.parent}",
                f"chain::{chain.child}",
                label=label,
                style=style,
                color="#666666",
            )
    return g


def _build_hierarchy_graph(l2_instance: L2Instance) -> graphviz.Digraph:
    """Render the parent → child rollup of accounts and account templates.

    Singleton ``Account`` nodes use the same scope-colored fill as the
    other diagrams (blue=internal, orange=external). ``AccountTemplate``
    nodes use a dashed border so a reader can distinguish "this is one
    account" from "this is a SHAPE that exists in many instances at
    runtime" at a glance.

    Edges run from child to parent (singleton or template child →
    singleton-account parent), resolved by
    ``child.parent_role == parent.role``. The edge arrow points at the
    parent so the rollup direction reads naturally with ``rankdir=BT``
    (children at the top, control accounts at the bottom).

    Roots (singletons with ``parent_role=None``) appear ungrouped at
    the bottom rank.
    """
    g = graphviz.Digraph(format="svg")
    g.attr(rankdir="BT", nodesep="0.4", ranksep="0.9")
    g.attr("node", fontsize="11", style="filled")

    role_to_account = _role_to_account(l2_instance)

    for acc in l2_instance.accounts:
        _add_account_node(g, acc)

    for template in l2_instance.account_templates:
        _add_account_template_node(g, template)

    # Child → parent edges (children: singletons + templates with
    # parent_role set; parents: singletons whose role matches).
    for acc in l2_instance.accounts:
        if acc.parent_role is None:
            continue
        parent = role_to_account.get(str(acc.parent_role))
        if parent is None:
            continue
        g.edge(str(acc.id), str(parent.id), color="#666666")

    for template in l2_instance.account_templates:
        if template.parent_role is None:
            continue
        parent = role_to_account.get(str(template.parent_role))
        if parent is None:
            continue
        g.edge(_template_node_id(template), str(parent.id), color="#666666")

    return g


# -- Graph helpers -----------------------------------------------------------


def _role_to_account(l2_instance: L2Instance) -> dict[str, Account]:
    return {
        str(acc.role): acc for acc in l2_instance.accounts if acc.role is not None
    }


def _role_to_template(l2_instance: L2Instance) -> dict[str, AccountTemplate]:
    return {str(t.role): t for t in l2_instance.account_templates}


def _add_account_node(g: graphviz.Digraph, acc: Account) -> None:
    color = "#bbdefb" if acc.scope == "internal" else "#ffe0b2"
    label = acc.name or acc.id
    g.node(str(acc.id), str(label), fillcolor=color, shape="box")


def _template_node_id(template: AccountTemplate) -> str:
    """Stable graph node id for an AccountTemplate.

    Templates have no ``id`` field (they're a SHAPE, not an instance) so
    we synthesize one from the role with a ``tmpl__`` prefix to avoid
    collisions with singleton account ids.

    Underscore — NOT colon. The ``graphviz`` Python lib quotes node
    IDs in node-definition statements but emits unquoted endpoints in
    edge statements, where Graphviz dot syntax then parses ``a:b`` as
    "node ``a``, port ``b``". A previous ``tmpl::`` prefix made every
    template edge collapse onto a phantom ``tmpl`` node — see commit
    history for the fix.
    """
    return f"tmpl__{template.role}"


def _add_account_template_node(
    g: graphviz.Digraph, template: AccountTemplate,
) -> None:
    """Render an AccountTemplate node with a dashed border.

    Uses the same scope-coloured fill as singletons but a dashed
    border to mark it as "this is a SHAPE, populated at runtime"
    rather than a single physical account. Label includes ``role × N``
    to nudge readers toward the multi-instance reading.
    """
    color = "#bbdefb" if template.scope == "internal" else "#ffe0b2"
    g.node(
        _template_node_id(template),
        f"{template.role} × N",
        fillcolor=color,
        shape="box",
        style="filled,dashed",
    )


def _add_rail_edges(
    g: graphviz.Digraph,
    rail: Rail,
    role_to_account: dict[str, Account],
) -> None:
    if isinstance(rail, TwoLegRail):
        sources = _expand_role_expression(rail.source_role)
        destinations = _expand_role_expression(rail.destination_role)
        for src_role in sources:
            src_acc = role_to_account.get(src_role)
            for dst_role in destinations:
                dst_acc = role_to_account.get(dst_role)
                if src_acc is None or dst_acc is None:
                    continue
                g.edge(
                    str(src_acc.id),
                    str(dst_acc.id),
                    label=f"{rail.name}\n({rail.transfer_type})",
                    fontsize="9",
                    color="#1976d2",
                )
    elif isinstance(rail, SingleLegRail):
        for leg_role in _expand_role_expression(rail.leg_role):
            acc = role_to_account.get(leg_role)
            if acc is None:
                continue
            g.edge(
                str(acc.id),
                str(acc.id),
                label=f"{rail.name}\n({rail.transfer_type})",
                fontsize="9",
                style="dashed",
                color="#7b1fa2",
            )


def _add_template_rail_edges(
    g: graphviz.Digraph,
    rail: Rail,
    template_roles: set[str],
    role_to_template: dict[str, AccountTemplate],
) -> None:
    """Mirror of ``_add_rail_edges`` keyed off AccountTemplate nodes.

    Only emits an edge when the role on each end resolves to an
    AccountTemplate; singleton-only rails (no template touched) drop
    out of the diagram by design.
    """
    if isinstance(rail, TwoLegRail):
        sources = _expand_role_expression(rail.source_role)
        destinations = _expand_role_expression(rail.destination_role)
        for src_role in sources:
            if src_role not in template_roles:
                continue
            src_template = role_to_template[src_role]
            for dst_role in destinations:
                if dst_role not in template_roles:
                    continue
                dst_template = role_to_template[dst_role]
                g.edge(
                    _template_node_id(src_template),
                    _template_node_id(dst_template),
                    label=f"{rail.name}\n({rail.transfer_type})",
                    fontsize="9",
                    color="#1976d2",
                )
    elif isinstance(rail, SingleLegRail):
        for leg_role in _expand_role_expression(rail.leg_role):
            if leg_role not in template_roles:
                continue
            template = role_to_template[leg_role]
            node_id = _template_node_id(template)
            g.edge(
                node_id,
                node_id,
                label=f"{rail.name}\n({rail.transfer_type})",
                fontsize="9",
                style="dashed",
                color="#7b1fa2",
            )


def _expand_role_expression(expr: object) -> tuple[str, ...]:
    """RoleExpression is either a single Identifier or a tuple of them."""
    if isinstance(expr, tuple):
        return tuple(str(e) for e in expr)
    return (str(expr),)


def _add_chain_edge(g: graphviz.Digraph, chain: ChainEntry) -> None:
    style = "solid" if chain.required else "dashed"
    parts: list[str] = []
    if chain.required:
        parts.append("required")
    if chain.xor_group is not None:
        parts.append(f"xor:{chain.xor_group}")
    label = " · ".join(parts)
    g.edge(
        str(chain.parent),
        str(chain.child),
        label=label,
        fontsize="9",
        style=style,
        color="#666666",
    )


# -- App tree builder dispatch -----------------------------------------------


def _build_app(app_name: str):
    """Build the named app's tree against a default L2 + minimal Config.

    Used for ``render_dataflow`` — only needs the analysis structure
    (sheets + visuals + dataset refs), not a real datasource.
    """
    from quicksight_gen.common.config import Config
    from quicksight_gen.common.l2.loader import load_instance

    spec_example = load_instance(_TESTS_L2_DIR / "spec_example.yaml")
    cfg = Config(
        aws_account_id="000000000000",
        aws_region="us-east-2",
        datasource_arn=(
            "arn:aws:quicksight:us-east-2:000000000000:"
            "datasource/qs-gen-demo-datasource"
        ),
        principal_arns=[
            "arn:aws:quicksight:us-east-2:000000000000:user/default/dummy"
        ],
    )
    return _APP_BUILDERS[app_name](cfg, l2_instance=spec_example)


def _build_l1_app(cfg, *, l2_instance):
    from quicksight_gen.apps.l1_dashboard.app import build_l1_dashboard_app
    return build_l1_dashboard_app(cfg, l2_instance=l2_instance)


def _build_l2ft_app(cfg, *, l2_instance):
    from quicksight_gen.apps.l2_flow_tracing.app import build_l2_flow_tracing_app
    return build_l2_flow_tracing_app(cfg, l2_instance=l2_instance)


def _build_inv_app(cfg, *, l2_instance):
    from quicksight_gen.apps.investigation.app import build_investigation_app
    return build_investigation_app(cfg, l2_instance=l2_instance)


def _build_exec_app(cfg, *, l2_instance):
    from quicksight_gen.apps.executives.app import build_executives_app
    return build_executives_app(cfg, l2_instance=l2_instance)


_APP_BUILDERS = {
    "l1_dashboard": _build_l1_app,
    "l2_flow_tracing": _build_l2ft_app,
    "investigation": _build_inv_app,
    "executives": _build_exec_app,
}


# -- SVG plumbing ------------------------------------------------------------


def _to_svg(g: graphviz.Digraph | graphviz.Source) -> str:
    """Render to SVG bytes, decode, strip XML declaration + DOCTYPE."""
    svg_bytes = g.pipe(format="svg")
    svg = svg_bytes.decode("utf-8")
    if svg.startswith("<?xml"):
        _, _, svg = svg.partition("?>")
        svg = svg.lstrip()
    if svg.startswith("<!DOCTYPE"):
        _, _, svg = svg.partition(">")
        svg = svg.lstrip()
    return svg


# -- Paths -------------------------------------------------------------------


_DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
_CONCEPTUAL_DIR = _DOCS_DIR / "_diagrams" / "conceptual"
_TESTS_L2_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "tests" / "l2"
)
