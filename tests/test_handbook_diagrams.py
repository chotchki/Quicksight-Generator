"""Smoke tests for ``common.handbook.diagrams``.

Exercises every render path against the spec_example fixture so a
broken graphviz install or a renamed L2 primitive surfaces here
rather than at mkdocs-build time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quicksight_gen.common.handbook.diagrams import (
    render_conceptual,
    render_dataflow,
    render_l2_topology,
)
from quicksight_gen.common.l2.loader import load_instance


_FIXTURES = Path(__file__).parent / "l2"
_SPEC_EXAMPLE = _FIXTURES / "spec_example.yaml"
_SASQUATCH_PR = _FIXTURES / "sasquatch_pr.yaml"


# -- L2-driven topology ------------------------------------------------------


class TestL2Topology:
    @pytest.mark.parametrize(
        "kind",
        ["accounts", "account_templates", "chains", "layered", "hierarchy"],
    )
    def test_renders_against_spec_example(self, kind: str):
        l2 = load_instance(_SPEC_EXAMPLE)
        svg = render_l2_topology(l2, kind)  # type: ignore[arg-type]
        assert "<svg" in svg
        assert "</svg>" in svg

    @pytest.mark.parametrize(
        "kind",
        ["accounts", "account_templates", "chains", "layered", "hierarchy"],
    )
    def test_renders_against_sasquatch_pr(self, kind: str):
        # Sasquatch is a richer fixture — exercises union role expressions
        # + XOR-grouped chain entries that spec_example doesn't have.
        l2 = load_instance(_SASQUATCH_PR)
        svg = render_l2_topology(l2, kind)  # type: ignore[arg-type]
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_unknown_kind_raises(self):
        l2 = load_instance(_SPEC_EXAMPLE)
        with pytest.raises(ValueError, match="unknown topology kind"):
            render_l2_topology(l2, "bogus")  # type: ignore[arg-type]

    def test_accounts_diagram_includes_account_names(self):
        l2 = load_instance(_SPEC_EXAMPLE)
        svg = render_l2_topology(l2, "accounts")
        # spec_example has Clearing Suspense, North Pool, South Pool —
        # each should appear in the rendered SVG as a node label.
        for expected in ("Clearing Suspense", "North Pool", "South Pool"):
            assert expected in svg, f"missing account label: {expected}"

    def test_account_templates_diagram_includes_template_marker(self):
        # spec_example declares CustomerSubledger as a template;
        # sasquatch_pr declares CustomerDDA / MerchantDDA / etc. The
        # template node label is rendered as ``role × N`` so the SVG
        # must contain that marker once at minimum.
        l2 = load_instance(_SASQUATCH_PR)
        svg = render_l2_topology(l2, "account_templates")
        assert "× N" in svg, (
            "account_templates diagram should mark templates with × N"
        )

    def test_transfer_template_diagram_renders_against_sasquatch_pr(self):
        # sasquatch_pr declares two TransferTemplates: InternalTransferCycle
        # (3 legs incl. one Variable closure) and MerchantSettlementCycle
        # (1 leg, TransferKey-grouped). Both should render without raising
        # and the SVG should mention the template name + at least one of
        # its leg rails.
        l2 = load_instance(_SASQUATCH_PR)
        for template in l2.transfer_templates:
            svg = render_l2_topology(
                l2, "transfer_template", name=str(template.name),
            )
            assert "<svg" in svg
            assert str(template.name) in svg, (
                f"transfer_template diagram missing the template name "
                f"{template.name!r} in the rendered SVG"
            )
            for leg in template.leg_rails:
                assert str(leg) in svg, (
                    f"transfer_template diagram for {template.name!r} "
                    f"missing leg-rail {leg!r}"
                )

    def test_transfer_template_diagram_requires_name(self):
        # Defensive: the dispatch arm should reject the missing-name
        # case with a clear error rather than silently rendering nothing.
        l2 = load_instance(_SASQUATCH_PR)
        import pytest
        with pytest.raises(ValueError, match="requires a name"):
            render_l2_topology(l2, "transfer_template")

    def test_transfer_template_diagram_unknown_name_raises(self):
        l2 = load_instance(_SASQUATCH_PR)
        import pytest
        with pytest.raises(ValueError, match="no TransferTemplate named"):
            render_l2_topology(
                l2, "transfer_template", name="DoesNotExist",
            )

    def test_diagrams_bundle_parallel_rails_per_direction(self):
        # Parallel rails sharing the same (src, dst) direction should
        # collapse into one labeled edge instead of N parallel lines.
        # Direction stays split (a Customer→External rail and an
        # External→Customer rail produce distinct edges).
        #
        # sasquatch_pr's ext-harvest-credit-exchange ↔ CustomerDDA pair
        # has multiple rails in each direction (CustomerInbound{ACH,Wire}
        # plus the cash-deposit family inbound; CustomerOutbound{ACH,Wire}
        # plus cash-withdrawal + return rails outbound). Pre-bundle the
        # template diagram emitted ~9 edges; post-bundle it emits ~5.
        # Guard against regression by asserting the count drops once
        # bundling is in place.
        l2 = load_instance(_SASQUATCH_PR)
        svg = render_l2_topology(l2, "account_templates")
        # Graphviz writes "src->dst" inside <title> for each edge. Count
        # how many distinct edge titles appear in the SVG.
        import re
        titles = re.findall(r"<title>([^<]+)</title>", svg)
        edges = [t for t in titles if "&#45;&gt;" in t or "->" in t]
        # 21 rails (sasquatch_pr) → without bundling we'd see closer to
        # 15+ edges on the templates diagram alone. With bundling on
        # template-touching rails we expect single-digit. Cap a regression
        # bar generously: ≤8 keeps the win obvious without coupling to
        # the exact rail topology.
        assert len(edges) <= 8, (
            f"Templates diagram emitted {len(edges)} edges; expected ≤8 "
            f"after parallel-rail bundling. Edge titles:\n  "
            + "\n  ".join(edges)
        )

    def test_account_templates_diagram_renders_singleton_cross_edges(self):
        # Regression guard: an earlier filter required BOTH ends of a
        # rail to be templates, which dropped every template ↔ singleton
        # rail (the common case) and left only SingleLegRail self-loops
        # on template nodes — a useless diagram.
        #
        # sasquatch_pr's ZBASweep rail (ZBASubAccount → ConcentrationMaster)
        # is the canonical template ↔ singleton case; ConcentrationMaster
        # is a singleton account whose label "Cash Concentration Master"
        # MUST appear in the rendered SVG so the rail edge is visible.
        l2 = load_instance(_SASQUATCH_PR)
        svg = render_l2_topology(l2, "account_templates")
        assert "Cash Concentration Master" in svg, (
            "account_templates diagram dropped a template→singleton rail "
            "(ZBASweep). The diagram should render singleton endpoints "
            "for any template-touching rail, not only template→template."
        )

    def test_chains_diagram_renders_when_chains_present(self):
        # sasquatch_pr declares chain entries; spec_example may or may
        # not. Either way the SVG should be well-formed.
        l2 = load_instance(_SASQUATCH_PR)
        svg = render_l2_topology(l2, "chains")
        assert "<svg" in svg

    def test_hierarchy_diagram_includes_template_marker(self):
        # sasquatch_pr has account templates (CustomerDDA, MerchantDDA,
        # ExternalCounterparty etc.). The hierarchy renderer suffixes
        # template labels with ``× N`` to mark them as "many instances
        # at runtime" — proves templates are surfaced separately from
        # singletons.
        l2 = load_instance(_SASQUATCH_PR)
        svg = render_l2_topology(l2, "hierarchy")
        assert "× N" in svg, "hierarchy diagram should mark templates with × N"

    def test_hierarchy_template_edges_reach_their_parent(self):
        # Regression: the original ``tmpl::`` node-id prefix collided
        # with Graphviz's ``node:port`` syntax in edge endpoints —
        # graphviz-python quoted the identifier in the node definition
        # but not in the edge, so every template edge collapsed onto a
        # phantom ``tmpl`` node. Walk the rendered SVG and assert each
        # template's parent_role chain produces a real edge whose tail
        # is the template node, not ``tmpl``.
        from quicksight_gen.common.handbook.diagrams import (
            _build_hierarchy_graph,
        )

        l2 = load_instance(_SASQUATCH_PR)
        dot = _build_hierarchy_graph(l2).source

        # Sasquatch has CustomerDDA → DDAControl among others. The
        # rendered DOT must contain that exact edge with the expected
        # template node id, NOT a port-syntax artifact like
        # ``tmpl:"":CustomerDDA``.
        assert "tmpl__CustomerDDA -> " in dot, (
            f"expected 'tmpl__CustomerDDA -> ...' edge in DOT; got:\n{dot}"
        )
        # And the broken form must NOT appear anywhere.
        assert ":CustomerDDA" not in dot, (
            f"DOT contains port-syntax artifact ':CustomerDDA' — node id "
            f"prefix is interacting with Graphviz port parsing again.\n{dot}"
        )


# -- Per-app dataflow --------------------------------------------------------


class TestDataflow:
    @pytest.mark.parametrize(
        "app",
        ["l1_dashboard", "l2_flow_tracing", "investigation", "executives"],
    )
    def test_renders_for_every_shipped_app(self, app: str):
        svg = render_dataflow(app)
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_l1_dashboard_includes_known_dataset_identifiers(self):
        svg = render_dataflow("l1_dashboard")
        # The L1 dashboard has 14 datasets (per CLAUDE.md). Spot-check one
        # that's stable across L2 instances: the drift dataset.
        # The dataset identifier shape is ``<prefix>-l1-...``, so just
        # check that *something* dataset-ish is rendered.
        assert "drift" in svg.lower() or "transactions" in svg.lower()

    def test_unknown_app_raises_keyerror(self):
        with pytest.raises(KeyError):
            render_dataflow("not_a_real_app")


# -- Hand-authored conceptual ------------------------------------------------


class TestConceptual:
    def test_double_entry_renders(self):
        svg = render_conceptual("double-entry")
        assert "<svg" in svg
        assert "</svg>" in svg
        # Sanity check — the rendered SVG should mention some node
        # text from the .dot source.
        assert "Money" in svg or "money" in svg

    def test_unknown_diagram_raises_keyerror_with_catalog(self):
        with pytest.raises(KeyError, match="No conceptual diagram"):
            render_conceptual("not-a-real-diagram")


# -- SVG plumbing ------------------------------------------------------------


class TestSvgOutput:
    def test_xml_declaration_stripped(self):
        # Inline SVG must NOT carry the <?xml ... ?> prologue —
        # browsers won't render it inline if it's there.
        l2 = load_instance(_SPEC_EXAMPLE)
        svg = render_l2_topology(l2, "accounts")
        assert "<?xml" not in svg

    def test_doctype_stripped(self):
        l2 = load_instance(_SPEC_EXAMPLE)
        svg = render_l2_topology(l2, "accounts")
        assert "<!DOCTYPE" not in svg
