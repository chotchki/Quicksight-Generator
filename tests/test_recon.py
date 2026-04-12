"""Tests for Payment Reconciliation visuals and filters."""

from __future__ import annotations

from dataclasses import asdict

from quicksight_gen.constants import (
    DS_EXTERNAL_TRANSACTIONS,
    DS_PAYMENT_RECON,
    DS_PAYMENTS,
    SHEET_PAYMENT_RECON,
)
from quicksight_gen.models import _strip_nones
from quicksight_gen.recon_filters import (
    build_recon_controls,
    build_recon_filter_groups,
)
from quicksight_gen.recon_visuals import build_payment_recon_visuals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_visual_ids(visuals: list) -> list[str]:
    """Extract VisualId from each Visual union."""
    ids = []
    for v in visuals:
        raw = _strip_nones(asdict(v))
        for vtype in raw.values():
            if isinstance(vtype, dict) and "VisualId" in vtype:
                ids.append(vtype["VisualId"])
    return ids


def _collect_dataset_refs(visuals: list) -> set[str]:
    """Collect all DataSetIdentifier values referenced by visuals."""
    refs: set[str] = set()

    def _walk(obj: object) -> None:
        if isinstance(obj, dict):
            if "DataSetIdentifier" in obj:
                refs.add(obj["DataSetIdentifier"])
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    for v in visuals:
        _walk(_strip_nones(asdict(v)))
    return refs


# ---------------------------------------------------------------------------
# Visual tests
# ---------------------------------------------------------------------------

class TestPaymentReconVisuals:
    def test_count(self):
        visuals = build_payment_recon_visuals()
        assert len(visuals) == 6

    def test_ids_unique(self):
        ids = _collect_visual_ids(build_payment_recon_visuals())
        assert len(ids) == len(set(ids))

    def test_dataset_refs(self):
        refs = _collect_dataset_refs(build_payment_recon_visuals())
        assert refs == {DS_PAYMENT_RECON, DS_PAYMENTS}

    def test_has_kpi_visuals(self):
        visuals = build_payment_recon_visuals()
        kpis = [v for v in visuals if v.KPIVisual is not None]
        assert len(kpis) == 3

    def test_has_bar_chart(self):
        visuals = build_payment_recon_visuals()
        bars = [v for v in visuals if v.BarChartVisual is not None]
        assert len(bars) == 1

    def test_has_tables(self):
        visuals = build_payment_recon_visuals()
        tables = [v for v in visuals if v.TableVisual is not None]
        assert len(tables) == 2

    def test_bar_chart_has_filter_action(self):
        visuals = build_payment_recon_visuals()
        bar = next(v for v in visuals if v.BarChartVisual is not None)
        assert bar.BarChartVisual.Actions is not None
        assert len(bar.BarChartVisual.Actions) == 1
        action = bar.BarChartVisual.Actions[0]
        assert action.Trigger == "DATA_POINT_CLICK"

    def test_tables_have_param_actions(self):
        visuals = build_payment_recon_visuals()
        tables = [v for v in visuals if v.TableVisual is not None]
        for t in tables:
            assert t.TableVisual.Actions is not None
            assert len(t.TableVisual.Actions) == 1
            ops = t.TableVisual.Actions[0].ActionOperations
            op_keys = set()
            for op in ops:
                op_keys.update(_strip_nones(asdict(op)).keys())
            assert "NavigationOperation" in op_keys
            assert "SetParametersOperation" in op_keys


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------

class TestReconFilterGroups:
    def test_count(self):
        groups = build_recon_filter_groups()
        assert len(groups) == 4

    def test_filter_ids_unique(self):
        groups = build_recon_filter_groups()
        filter_ids = []
        for fg in groups:
            for f in fg.Filters:
                raw = _strip_nones(asdict(f))
                for filter_obj in raw.values():
                    if isinstance(filter_obj, dict) and "FilterId" in filter_obj:
                        filter_ids.append(filter_obj["FilterId"])
        assert len(filter_ids) == len(set(filter_ids))

    def test_filter_group_ids_unique(self):
        groups = build_recon_filter_groups()
        fg_ids = [fg.FilterGroupId for fg in groups]
        assert len(fg_ids) == len(set(fg_ids))

    def test_all_scoped_to_payment_recon_sheet(self):
        groups = build_recon_filter_groups()
        for fg in groups:
            raw = _strip_nones(asdict(fg))
            scope = raw["ScopeConfiguration"]
            if "SelectedSheets" in scope:
                for svc in scope["SelectedSheets"][
                    "SheetVisualScopingConfigurations"
                ]:
                    assert svc["SheetId"] == SHEET_PAYMENT_RECON, (
                        f"Filter group '{fg.FilterGroupId}' scoped to "
                        f"'{svc['SheetId']}', expected '{SHEET_PAYMENT_RECON}'"
                    )

    def test_has_numeric_range_filter(self):
        groups = build_recon_filter_groups()
        days_fgs = [g for g in groups if "days-outstanding" in g.FilterGroupId]
        assert len(days_fgs) == 1
        raw = _strip_nones(asdict(days_fgs[0]))
        assert "NumericRangeFilter" in raw["Filters"][0]

    def test_has_time_range_filter(self):
        groups = build_recon_filter_groups()
        date_fgs = [g for g in groups if "date-range" in g.FilterGroupId]
        assert len(date_fgs) == 1

    def test_has_category_filters(self):
        groups = build_recon_filter_groups()
        cat_fgs = [
            g for g in groups
            if "match-status" in g.FilterGroupId
            or "external-system" in g.FilterGroupId
        ]
        assert len(cat_fgs) == 2


class TestReconFilterControls:
    def test_count(self):
        controls = build_recon_controls()
        assert len(controls) == 4

    def test_has_slider_control(self):
        controls = build_recon_controls()
        raw_all = [_strip_nones(asdict(c)) for c in controls]
        sliders = [r for r in raw_all if "Slider" in r]
        assert len(sliders) == 1

    def test_controls_reference_valid_filters(self):
        """Every SourceFilterId in controls must match a filter group filter."""
        groups = build_recon_filter_groups()
        all_filter_ids = set()
        for fg in groups:
            for f in fg.Filters:
                raw = _strip_nones(asdict(f))
                for filter_obj in raw.values():
                    if isinstance(filter_obj, dict) and "FilterId" in filter_obj:
                        all_filter_ids.add(filter_obj["FilterId"])

        for ctrl in build_recon_controls():
            raw = _strip_nones(asdict(ctrl))
            for ctrl_obj in raw.values():
                if isinstance(ctrl_obj, dict) and "SourceFilterId" in ctrl_obj:
                    src = ctrl_obj["SourceFilterId"]
                    assert src in all_filter_ids, (
                        f"Control references filter '{src}' but it's not in "
                        f"filter groups. Known: {all_filter_ids}"
                    )
