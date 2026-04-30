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
    @pytest.mark.parametrize("kind", ["accounts", "chains", "layered", "hierarchy"])
    def test_renders_against_spec_example(self, kind: str):
        l2 = load_instance(_SPEC_EXAMPLE)
        svg = render_l2_topology(l2, kind)  # type: ignore[arg-type]
        assert "<svg" in svg
        assert "</svg>" in svg

    @pytest.mark.parametrize("kind", ["accounts", "chains", "layered", "hierarchy"])
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
