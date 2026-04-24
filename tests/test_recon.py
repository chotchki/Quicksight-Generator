"""Tests for the Payment Reconciliation app.

L.4.13 — the imperative builders (`apps/payment_recon/{analysis,
filters,recon_filters,visuals,recon_visuals}.py`) were retired.
Tests now walk the tree's emitted analysis from
`build_payment_recon_app(cfg)`. The L.4.5 + L.4.6 structural
assertions for the orphan-bar-wired Exceptions + Payment
Reconciliation sheets live here (moved from the deleted
`test_l4_payment_recon_port.py` byte-identity gate).
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from quicksight_gen.apps.payment_recon.app import build_payment_recon_app
from quicksight_gen.apps.payment_recon.constants import (
    SHEET_EXCEPTIONS,
    SHEET_PAYMENT_RECON,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.models import _strip_nones


_TEST_CFG = Config(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    datasource_arn="arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds",
    theme_preset="default",
)


@pytest.fixture(scope="module")
def pr_analysis():
    """Tree-built PR Analysis (post-emit, auto-IDs resolved)."""
    return build_payment_recon_app(_TEST_CFG).emit_analysis()


def _visual_ids(sheet: dict) -> list[str]:
    out: list[str] = []
    for v in sheet.get("Visuals") or []:
        for body in v.values():
            if isinstance(body, dict) and "VisualId" in body:
                out.append(body["VisualId"])
    return out


def _layout_visual_ids(sheet: dict) -> list[str]:
    layouts = sheet.get("Layouts") or []
    if not layouts:
        return []
    return [
        e["ElementId"]
        for e in layouts[0]["Configuration"]["GridLayout"]["Elements"]
    ]


def _sheet_dict(pr_analysis, sheet_id: str) -> dict:
    sheet = next(
        s for s in pr_analysis.Definition.Sheets if s.SheetId == sheet_id
    )
    return _strip_nones(asdict(sheet))


# ---------------------------------------------------------------------------
# Exceptions & Alerts (L.4.5 + L.4.12a)
# ---------------------------------------------------------------------------

def test_exceptions_sheet_has_kpis_tables_and_aging_bars(pr_analysis) -> None:
    """Exceptions & Alerts: 2 KPIs + 5 detail tables + 5 aging bars
    (one per table) = 12 visuals, all placed in layout. L.4.12a wired
    the 5 aging bars the imperative had constructed but never placed."""
    sheet = _sheet_dict(pr_analysis, SHEET_EXCEPTIONS)
    expected = {
        "exceptions-kpi-unsettled",
        "exceptions-kpi-returns",
        "exceptions-unsettled-table",
        "exceptions-returns-table",
        "exceptions-sale-settlement-mismatch-table",
        "exceptions-settlement-payment-mismatch-table",
        "exceptions-unmatched-ext-txn-table",
        "exceptions-aging-unsettled",
        "exceptions-aging-returns",
        "exceptions-aging-sale-stl-mismatch",
        "exceptions-aging-stl-pay-mismatch",
        "exceptions-aging-unmatched-ext",
    }
    assert set(_visual_ids(sheet)) == expected
    # Every visual is placed — no orphans remain.
    assert set(_layout_visual_ids(sheet)) == expected


# ---------------------------------------------------------------------------
# Payment Reconciliation (L.4.6 + L.4.12a)
# ---------------------------------------------------------------------------

def test_payment_recon_sheet_has_kpis_bar_tables_and_aging(pr_analysis) -> None:
    """Payment Reconciliation: 3 KPIs + bar by system + side-by-side
    detail tables + 1 aging bar = 7 visuals all placed."""
    sheet = _sheet_dict(pr_analysis, SHEET_PAYMENT_RECON)
    expected = {
        "recon-kpi-matched-amount",
        "recon-kpi-unmatched-amount",
        "recon-kpi-late-count",
        "recon-bar-by-system",
        "recon-payments-table",
        "recon-ext-txn-table",
        "recon-aging-bar",
    }
    assert set(_visual_ids(sheet)) == expected
    assert set(_layout_visual_ids(sheet)) == expected


def test_payment_recon_tables_carry_mutual_filter_drills(pr_analysis) -> None:
    """Both detail tables on the recon sheet write `pExternalTransactionId`
    on left-click — that's what powers the mutual-filter behaviour
    (parameter-bound CategoryFilters re-render both tables when one
    fires). The drill `target_sheet` is the recon sheet itself
    (same-sheet parameter-set)."""
    sheet = _sheet_dict(pr_analysis, SHEET_PAYMENT_RECON)
    table_ids = {"recon-payments-table", "recon-ext-txn-table"}
    for v in sheet["Visuals"]:
        if "TableVisual" not in v:
            continue
        body = v["TableVisual"]
        if body["VisualId"] not in table_ids:
            continue
        actions = body.get("Actions") or []
        assert len(actions) == 1, (
            f"{body['VisualId']} should have exactly one drill action"
        )
        action = actions[0]
        assert action["Trigger"] == "DATA_POINT_CLICK"
        ops = action["ActionOperations"]
        # NavigationOperation + SetParametersOperation, both targeting
        # the recon sheet itself (same-sheet param-set).
        op_keys = {key for op in ops for key in op}
        assert op_keys == {"NavigationOperation", "SetParametersOperation"}
        nav = next(op for op in ops if "NavigationOperation" in op)
        assert nav["NavigationOperation"]["LocalNavigationConfiguration"][
            "TargetSheetId"
        ] == SHEET_PAYMENT_RECON
        set_params = next(op for op in ops if "SetParametersOperation" in op)
        targets = {
            cfg["DestinationParameterName"]
            for cfg in set_params["SetParametersOperation"][
                "ParameterValueConfigurations"
            ]
        }
        assert targets == {"pExternalTransactionId"}
