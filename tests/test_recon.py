"""Tests for reconciliation visuals and filters (Steps 3 & 4)."""

from __future__ import annotations

from dataclasses import asdict

from quicksight_gen.constants import (
    DS_EXTERNAL_TRANSACTIONS,
    DS_PAYMENT_RECON,
    DS_RECON_EXCEPTIONS,
    DS_SALES_RECON,
    DS_SETTLEMENT_RECON,
    SHEET_PAYMENT_RECON,
    SHEET_RECON_OVERVIEW,
    SHEET_SALES_RECON,
    SHEET_SETTLEMENT_RECON,
)
from quicksight_gen.models import _strip_nones
from quicksight_gen.recon_filters import (
    build_payment_recon_controls,
    build_recon_filter_groups,
    build_recon_overview_controls,
    build_sales_recon_controls,
    build_settlement_recon_controls,
)
from quicksight_gen.recon_visuals import (
    build_payment_recon_visuals,
    build_recon_overview_visuals,
    build_sales_recon_visuals,
    build_settlement_recon_visuals,
)


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

class TestReconOverviewVisuals:
    def test_count(self):
        visuals = build_recon_overview_visuals()
        assert len(visuals) == 6

    def test_ids_unique(self):
        ids = _collect_visual_ids(build_recon_overview_visuals())
        assert len(ids) == len(set(ids))

    def test_dataset_refs(self):
        refs = _collect_dataset_refs(build_recon_overview_visuals())
        assert refs == {DS_RECON_EXCEPTIONS}


class TestSalesReconVisuals:
    def test_count(self):
        assert len(build_sales_recon_visuals()) == 4

    def test_ids_unique(self):
        ids = _collect_visual_ids(build_sales_recon_visuals())
        assert len(ids) == len(set(ids))

    def test_dataset_refs(self):
        refs = _collect_dataset_refs(build_sales_recon_visuals())
        assert refs == {DS_SALES_RECON}


class TestSettlementReconVisuals:
    def test_count(self):
        assert len(build_settlement_recon_visuals()) == 4

    def test_ids_unique(self):
        ids = _collect_visual_ids(build_settlement_recon_visuals())
        assert len(ids) == len(set(ids))

    def test_dataset_refs(self):
        refs = _collect_dataset_refs(build_settlement_recon_visuals())
        assert refs == {DS_SETTLEMENT_RECON}


class TestPaymentReconVisuals:
    def test_count(self):
        assert len(build_payment_recon_visuals()) == 4

    def test_ids_unique(self):
        ids = _collect_visual_ids(build_payment_recon_visuals())
        assert len(ids) == len(set(ids))

    def test_dataset_refs(self):
        refs = _collect_dataset_refs(build_payment_recon_visuals())
        assert refs == {DS_PAYMENT_RECON}


class TestAllReconVisualIdsUnique:
    def test_no_duplicates_across_sheets(self):
        all_ids = (
            _collect_visual_ids(build_recon_overview_visuals())
            + _collect_visual_ids(build_sales_recon_visuals())
            + _collect_visual_ids(build_settlement_recon_visuals())
            + _collect_visual_ids(build_payment_recon_visuals())
        )
        assert len(all_ids) == len(set(all_ids)), (
            f"Duplicate visual IDs: "
            f"{[vid for vid in all_ids if all_ids.count(vid) > 1]}"
        )


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------

class TestReconFilterGroups:
    def test_count(self):
        groups = build_recon_filter_groups()
        # 5 shared filters + 4 per-sheet days-outstanding filters
        assert len(groups) == 9

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

    def test_all_scope_sheet_ids_valid(self):
        valid_sheets = {
            SHEET_RECON_OVERVIEW,
            SHEET_SALES_RECON,
            SHEET_SETTLEMENT_RECON,
            SHEET_PAYMENT_RECON,
        }
        groups = build_recon_filter_groups()
        for fg in groups:
            raw = _strip_nones(asdict(fg))
            scope = raw["ScopeConfiguration"]
            if "SelectedSheets" in scope:
                for svc in scope["SelectedSheets"][
                    "SheetVisualScopingConfigurations"
                ]:
                    assert svc["SheetId"] in valid_sheets, (
                        f"Filter group '{fg.FilterGroupId}' references "
                        f"unknown sheet '{svc['SheetId']}'"
                    )

    def test_has_numeric_range_filters(self):
        """Each sheet gets its own days-outstanding NumericRangeFilter."""
        groups = build_recon_filter_groups()
        days_fgs = [g for g in groups if "days-outstanding" in g.FilterGroupId]
        assert len(days_fgs) == 4
        for fg in days_fgs:
            raw = _strip_nones(asdict(fg))
            assert "NumericRangeFilter" in raw["Filters"][0]


class TestReconFilterControls:
    def test_overview_controls_count(self):
        assert len(build_recon_overview_controls()) == 6

    def test_sales_recon_controls_count(self):
        assert len(build_sales_recon_controls()) == 5

    def test_settlement_recon_controls_count(self):
        assert len(build_settlement_recon_controls()) == 5

    def test_payment_recon_controls_count(self):
        assert len(build_payment_recon_controls()) == 5

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

        all_controls = (
            build_recon_overview_controls()
            + build_sales_recon_controls()
            + build_settlement_recon_controls()
            + build_payment_recon_controls()
        )
        for ctrl in all_controls:
            raw = _strip_nones(asdict(ctrl))
            for ctrl_obj in raw.values():
                if isinstance(ctrl_obj, dict) and "SourceFilterId" in ctrl_obj:
                    src = ctrl_obj["SourceFilterId"]
                    assert src in all_filter_ids, (
                        f"Control references filter '{src}' but it's not in "
                        f"filter groups. Known: {all_filter_ids}"
                    )

    def test_has_days_outstanding_control(self):
        """The days-outstanding control should use a Slider
        (per-sheet filter, not cross-sheet)."""
        controls = build_recon_overview_controls()
        raw_all = [_strip_nones(asdict(c)) for c in controls]
        days_ctrls = [
            r for r in raw_all
            if "Slider" in r
            and "days-outstanding" in r["Slider"]["SourceFilterId"]
        ]
        assert len(days_ctrls) == 1
