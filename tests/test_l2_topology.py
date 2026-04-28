"""Topology diagram render tests.

Three layers of coverage:

1. **Pure construction** — ``build_topology_graph`` returns a Graphviz
   Digraph whose ``.source`` (the DOT script) contains the expected
   roles, rails, templates, and chain edges. No filesystem I/O, no
   ``dot`` binary required. Runs in plain pytest.
2. **Bundling unit tests** — the `_bundle_two_leg_rails` helper
   collapses parallel rails into one labeled edge. Asserted against
   handwritten primitive instances.
3. **End-to-end render** — ``render_topology`` writes an SVG file from
   each shipped fixture. Skipped automatically when the system ``dot``
   binary or the ``graphviz`` Python package isn't available, so the
   suite passes everywhere even when Graphviz isn't installed.
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from quicksight_gen.common.l2 import (
    Account,
    AccountTemplate,
    ChainEntry,
    Identifier,
    L2Instance,
    SingleLegRail,
    TransferTemplate,
    TwoLegRail,
    load_instance,
)
from quicksight_gen.common.l2.topology import (
    build_topology_graph,
    render_topology,
)
from quicksight_gen.common.l2 import topology as topology_mod


FIXTURES = Path(__file__).parent / "l2"


def _has_dot_binary() -> bool:
    """True if the system 'dot' binary is on PATH."""
    return shutil.which("dot") is not None


def _has_graphviz_pkg() -> bool:
    """True if the Python 'graphviz' package is importable."""
    try:
        import graphviz  # noqa: F401
    except ImportError:
        return False
    return True


_render_skip = pytest.mark.skipif(
    not (_has_dot_binary() and _has_graphviz_pkg()),
    reason=(
        "Skipping render test — the system 'dot' binary and Python "
        "'graphviz' package must both be installed."
    ),
)
_pkg_skip = pytest.mark.skipif(
    not _has_graphviz_pkg(),
    reason="Python 'graphviz' package not installed.",
)


# -- Bundling unit tests -----------------------------------------------------


def _make_two_leg(
    name: str,
    src: str,
    dst: str,
    *,
    transfer_type: str = "ach",
) -> TwoLegRail:
    """Tiny helper — construct a TwoLegRail with the bare-minimum fields."""
    return TwoLegRail(
        name=Identifier(name),
        transfer_type=transfer_type,
        metadata_keys=(),
        source_role=(Identifier(src),),
        destination_role=(Identifier(dst),),
        origin="InternalInitiated",
        expected_net=Decimal("0"),
    )


def test_bundle_collapses_parallel_rails() -> None:
    """Two rails between the same (src, dst) collapse to one edge."""
    rails = [
        _make_two_leg("RailOne", "A", "B"),
        _make_two_leg("RailTwo", "A", "B", transfer_type="wire"),
    ]
    bundles = topology_mod._bundle_two_leg_rails(rails)
    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.source == "A"
    assert bundle.destination == "B"
    assert bundle.rail_names == (Identifier("RailOne"), Identifier("RailTwo"))
    assert set(bundle.transfer_types) == {"ach", "wire"}


def test_bundle_keeps_distinct_pairs_separate() -> None:
    """Rails to different destinations stay as separate bundles."""
    rails = [
        _make_two_leg("Rail1", "A", "B"),
        _make_two_leg("Rail2", "A", "C"),
        _make_two_leg("Rail3", "A", "B"),
    ]
    bundles = topology_mod._bundle_two_leg_rails(rails)
    assert len(bundles) == 2
    by_dest = {b.destination: b for b in bundles}
    assert by_dest[Identifier("B")].rail_names == (
        Identifier("Rail1"), Identifier("Rail3"),
    )
    assert by_dest[Identifier("C")].rail_names == (Identifier("Rail2"),)


def test_bundle_label_single_rail_skips_count_prefix() -> None:
    """A 1-rail bundle should not get a 'N rails:' prefix in the label."""
    rails = [_make_two_leg("OnlyRail", "A", "B", transfer_type="ach")]
    (bundle,) = topology_mod._bundle_two_leg_rails(rails)
    label = topology_mod._bundle_label(bundle)
    assert label.startswith("OnlyRail")
    assert "rails:" not in label


def test_bundle_label_multi_rail_uses_count_prefix() -> None:
    """A 3-rail bundle's label should lead with '3 rails:'."""
    rails = [
        _make_two_leg("RailA", "A", "B"),
        _make_two_leg("RailB", "A", "B", transfer_type="wire"),
        _make_two_leg("RailC", "A", "B", transfer_type="cash"),
    ]
    (bundle,) = topology_mod._bundle_two_leg_rails(rails)
    label = topology_mod._bundle_label(bundle)
    assert label.startswith("3 rails:")
    assert "RailA" in label
    assert "RailB" in label
    assert "RailC" in label


def test_bundle_fans_out_role_expression_cross_product() -> None:
    """A rail with multi-role source + destination produces N x M edges."""
    rail = TwoLegRail(
        name=Identifier("FanRail"),
        transfer_type="ach",
        metadata_keys=(),
        source_role=(Identifier("A"), Identifier("B")),
        destination_role=(Identifier("C"), Identifier("D")),
        origin="InternalInitiated",
        expected_net=Decimal("0"),
    )
    bundles = topology_mod._bundle_two_leg_rails([rail])
    pairs = {(b.source, b.destination) for b in bundles}
    assert pairs == {
        (Identifier("A"), Identifier("C")),
        (Identifier("A"), Identifier("D")),
        (Identifier("B"), Identifier("C")),
        (Identifier("B"), Identifier("D")),
    }


# -- Pure-construction tests against a handwritten instance -----------------


def _kitchen_instance() -> L2Instance:
    """A small but topologically rich L2Instance covering every primitive."""
    return L2Instance(
        instance=Identifier("kitchen"),
        accounts=(
            Account(
                id=Identifier("acc-internal"),
                name="Internal Account",
                role=Identifier("InternalRole"),
                scope="internal",
            ),
            Account(
                id=Identifier("acc-external"),
                name="External Account",
                role=Identifier("ExternalRole"),
                scope="external",
            ),
        ),
        account_templates=(
            AccountTemplate(
                role=Identifier("CustomerSubledger"),
                scope="internal",
                parent_role=Identifier("InternalRole"),
            ),
        ),
        rails=(
            _make_two_leg("InboundRail", "ExternalRole", "CustomerSubledger"),
            _make_two_leg(
                "OutboundRail", "CustomerSubledger", "ExternalRole",
                transfer_type="wire",
            ),
            SingleLegRail(
                name=Identifier("FeeCharge"),
                transfer_type="fee",
                metadata_keys=(),
                leg_role=(Identifier("CustomerSubledger"),),
                leg_direction="Debit",
                origin="InternalInitiated",
            ),
        ),
        transfer_templates=(
            TransferTemplate(
                name=Identifier("SettlementCycle"),
                transfer_type="settlement",
                expected_net=Decimal("0"),
                transfer_key=(Identifier("merchant_id"),),
                completion="business_day_end",
                leg_rails=(Identifier("FeeCharge"),),
            ),
        ),
        chains=(
            ChainEntry(
                parent=Identifier("InboundRail"),
                child=Identifier("SettlementCycle"),
                required=True,
            ),
        ),
        limit_schedules=(),
    )


@_pkg_skip
def test_build_graph_includes_every_role_node() -> None:
    """Every declared + rail-referenced role appears as a node."""
    inst = _kitchen_instance()
    g = build_topology_graph(inst)
    src: str = g.source
    for role in ("InternalRole", "ExternalRole", "CustomerSubledger"):
        assert role in src, f"role {role!r} missing from DOT output"


@_pkg_skip
def test_build_graph_renders_two_leg_rail_edge() -> None:
    """Every two-leg rail produces a labeled directed edge."""
    inst = _kitchen_instance()
    g = build_topology_graph(inst)
    src: str = g.source
    assert "InboundRail" in src
    assert "OutboundRail" in src


@_pkg_skip
def test_build_graph_renders_single_leg_self_loop() -> None:
    """Single-leg rails appear as self-loops on their leg_role."""
    inst = _kitchen_instance()
    g = build_topology_graph(inst)
    src: str = g.source
    assert "FeeCharge" in src
    assert "Debit" in src


@_pkg_skip
def test_build_graph_renders_transfer_template_cluster() -> None:
    """TransferTemplates appear as named clusters with their leg rails."""
    inst = _kitchen_instance()
    g = build_topology_graph(inst)
    src: str = g.source
    assert "SettlementCycle" in src
    assert "cluster_tmpl_SettlementCycle" in src
    assert "merchant_id" in src


@_pkg_skip
def test_build_graph_renders_chain_edge() -> None:
    """Chain entries become dashed parent -> child edges with labels."""
    inst = _kitchen_instance()
    g = build_topology_graph(inst)
    src: str = g.source
    assert "chain" in src
    assert "required" in src


@_pkg_skip
def test_build_graph_internal_external_styling_distinguishes_scope() -> None:
    """Internal + external roles get different fill colors."""
    inst = _kitchen_instance()
    g = build_topology_graph(inst)
    src: str = g.source
    # Internal node fill (#dbe9f6) and external node fill (#fff2cc)
    # both appear in the output. Templated roles use _TEMPLATE_STYLE
    # (#e8f0ff). All three should be present given the kitchen instance.
    assert "#dbe9f6" in src or "#e8f0ff" in src
    assert "#fff2cc" in src


# -- Smoke against shipped fixtures ------------------------------------------


@_pkg_skip
def test_build_graph_smoke_spec_example() -> None:
    """Walks the persona-neutral fixture without error + emits real content."""
    inst = load_instance(FIXTURES / "spec_example.yaml")
    g = build_topology_graph(inst)
    src: str = g.source
    # The fixture's role names should all surface in the DOT output.
    for role in (
        "ClearingSuspense", "NorthPool", "SouthPool", "CustomerLedger",
        "ExternalCounterparty", "CustomerSubledger",
    ):
        assert role in src, f"role {role!r} missing from spec_example DOT"
    # Every rail name should also be present.
    for rail_name in (
        "ExternalRailInbound", "ExternalRailOutbound",
        "SubledgerCharge", "PoolBalancing",
    ):
        assert rail_name in src, f"rail {rail_name!r} missing from spec_example DOT"
    # The template + its key surface.
    assert "MerchantSettlementCycle" in src
    assert "settlement_period" in src


@_pkg_skip
def test_build_graph_smoke_sasquatch_pr() -> None:
    """Walks the rich Sasquatch fixture end-to-end without error."""
    inst = load_instance(FIXTURES / "sasquatch_pr.yaml")
    g = build_topology_graph(inst)
    src: str = g.source
    # Spot-check a handful of identifiers we know exist in the fixture.
    assert "CashDueFRB" in src
    assert "ConcentrationMaster" in src
    assert "DDAControl" in src
    # Sasquatch declares transfer templates, chains, and many rails —
    # all should land in the graph.
    assert "cluster_tmpl_" in src


# -- End-to-end render (writes SVG) ------------------------------------------


@_render_skip
def test_render_topology_writes_svg_spec_example(tmp_path: Path) -> None:
    """End-to-end render of spec_example.yaml produces a non-empty SVG."""
    inst = load_instance(FIXTURES / "spec_example.yaml")
    out = tmp_path / "spec_example.svg"
    rendered = render_topology(inst, out)
    assert rendered.exists(), f"expected output at {rendered}"
    text = rendered.read_text(encoding="utf-8")
    assert text.startswith("<?xml") or text.startswith("<svg"), (
        "Output does not look like an SVG document"
    )
    # Spot-check a couple of role names made it into the SVG label text.
    assert "CustomerLedger" in text
    assert "ExternalCounterparty" in text


@_render_skip
def test_render_topology_writes_svg_sasquatch_pr(tmp_path: Path) -> None:
    """End-to-end render of sasquatch_pr.yaml produces a non-empty SVG."""
    inst = load_instance(FIXTURES / "sasquatch_pr.yaml")
    out = tmp_path / "sasquatch_pr.svg"
    rendered = render_topology(inst, out)
    assert rendered.exists()
    text = rendered.read_text(encoding="utf-8")
    assert "CashDueFRB" in text or "Cash" in text


@_render_skip
def test_render_topology_accepts_engine_choices(tmp_path: Path) -> None:
    """Each accepted engine produces a renderable SVG."""
    inst = load_instance(FIXTURES / "spec_example.yaml")
    for engine in ("dot", "neato", "sfdp"):
        out = tmp_path / f"spec_example_{engine}.svg"
        rendered = render_topology(inst, out, engine=engine)
        assert rendered.exists(), f"engine {engine!r} produced no file"


@_pkg_skip
def test_render_topology_rejects_unknown_engine(tmp_path: Path) -> None:
    """Unknown engine names raise a ValueError before any I/O happens."""
    inst = load_instance(FIXTURES / "spec_example.yaml")
    with pytest.raises(ValueError, match="not supported"):
        render_topology(inst, tmp_path / "x.svg", engine="bogus")
