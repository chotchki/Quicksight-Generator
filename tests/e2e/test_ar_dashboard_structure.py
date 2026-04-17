"""API tests: validate the deployed AR dashboard definition matches expectations.

Phase 5 shape — 5 sheets, per-sheet visual counts (Exceptions grows to
12 with the breach + overdraft additions), 5 drill-down parameters, and
16 filter groups (shared date-range + 5 multi-selects + 5 Show-Only
toggles + 5 parameter-bound drill-down filters).
"""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.api]


@pytest.fixture(scope="module")
def ar_dashboard_definition(qs_client, account_id, ar_dashboard_id) -> dict:
    resp = qs_client.describe_dashboard_definition(
        AwsAccountId=account_id,
        DashboardId=ar_dashboard_id,
    )
    return resp["Definition"]


def _visual_ids(sheet: dict) -> list[str]:
    out: list[str] = []
    for v in sheet.get("Visuals", []):
        for vtype in v.values():
            if isinstance(vtype, dict) and "VisualId" in vtype:
                out.append(vtype["VisualId"])
    return out


class TestSheets:
    EXPECTED_NAMES = [
        "Getting Started",
        "Balances",
        "Transfers",
        "Transactions",
        "Exceptions",
    ]

    def test_has_five_sheets(self, ar_dashboard_definition):
        assert len(ar_dashboard_definition["Sheets"]) == 5

    def test_sheet_order(self, ar_dashboard_definition):
        names = [s["Name"] for s in ar_dashboard_definition["Sheets"]]
        assert names == self.EXPECTED_NAMES

    def test_every_sheet_has_description(self, ar_dashboard_definition):
        for sheet in ar_dashboard_definition["Sheets"]:
            desc = sheet.get("Description", "")
            assert len(desc) > 20, (
                f"Sheet '{sheet['Name']}' missing description"
            )


class TestVisuals:
    EXPECTED_VISUAL_COUNTS = {
        "Balances": 4,
        "Transfers": 4,
        "Transactions": 5,
        # Phase 5: 5 KPIs + 5 tables + 2 timelines
        "Exceptions": 12,
    }

    def test_visual_counts_per_sheet(self, ar_dashboard_definition):
        for sheet in ar_dashboard_definition["Sheets"]:
            name = sheet["Name"]
            expected = self.EXPECTED_VISUAL_COUNTS.get(name)
            if expected is None:
                continue
            actual = len(sheet.get("Visuals", []))
            assert actual == expected, (
                f"Sheet '{name}' has {actual} visuals, expected {expected}"
            )

    def test_all_visual_ids_unique(self, ar_dashboard_definition):
        all_ids: list[str] = []
        for sheet in ar_dashboard_definition["Sheets"]:
            all_ids.extend(_visual_ids(sheet))
        assert len(all_ids) == len(set(all_ids)), (
            f"Duplicate visual IDs: "
            f"{[vid for vid in all_ids if all_ids.count(vid) > 1]}"
        )

    def test_every_visual_has_subtitle(self, ar_dashboard_definition):
        for sheet in ar_dashboard_definition["Sheets"]:
            for v in sheet.get("Visuals", []):
                for vtype in v.values():
                    if not (isinstance(vtype, dict) and "VisualId" in vtype):
                        continue
                    text = (
                        vtype.get("Subtitle", {})
                             .get("FormatText", {})
                             .get("PlainText", "")
                    )
                    assert len(text) > 10, (
                        f"Visual '{vtype['VisualId']}' missing subtitle"
                    )

    def test_exceptions_has_both_drift_tables_and_timelines(
        self, ar_dashboard_definition,
    ):
        """Phase 4 split the single drift table/timeline into ledger +
        sub-ledger pairs; Phase 5 adds breach and overdraft tables/KPIs.
        Catch it if any of the five reconciliation checks regresses away."""
        exc_sheet = next(
            s for s in ar_dashboard_definition["Sheets"]
            if s["Name"] == "Exceptions"
        )
        ids = set(_visual_ids(exc_sheet))
        for expected in (
            "ar-exc-ledger-drift-table",
            "ar-exc-subledger-drift-table",
            "ar-exc-ledger-drift-timeline",
            "ar-exc-subledger-drift-timeline",
            "ar-exc-nonzero-table",
            "ar-exc-breach-table",
            "ar-exc-overdraft-table",
            "ar-exc-kpi-breach",
            "ar-exc-kpi-overdraft",
        ):
            assert expected in ids, (
                f"Exceptions missing visual '{expected}'"
            )

    def test_transactions_has_bar_by_day(self, ar_dashboard_definition):
        """Phase 4 added the Transactions-by-day chart alongside by-status."""
        txn_sheet = next(
            s for s in ar_dashboard_definition["Sheets"]
            if s["Name"] == "Transactions"
        )
        ids = set(_visual_ids(txn_sheet))
        assert "ar-txn-bar-by-status" in ids
        assert "ar-txn-bar-by-day" in ids


class TestParameters:
    def _names(self, definition: dict) -> set[str]:
        names: set[str] = set()
        for p in definition.get("ParameterDeclarations", []):
            for decl in p.values():
                if isinstance(decl, dict) and "Name" in decl:
                    names.add(decl["Name"])
        return names

    def test_five_drill_down_parameters(self, ar_dashboard_definition):
        assert self._names(ar_dashboard_definition) == {
            "pArSubledgerAccountId",
            "pArLedgerAccountId",
            "pArTransferId",
            "pArActivityDate",
            "pArTransferType",
        }


class TestFilterGroups:
    EXPECTED_IDS = {
        "fg-ar-date-range",
        "fg-ar-ledger-account",
        "fg-ar-subledger-account",
        "fg-ar-transfer-status",
        "fg-ar-transaction-status",
        "fg-ar-transfer-type",
        "fg-ar-balances-ledger-drift",
        "fg-ar-balances-subledger-drift",
        "fg-ar-balances-overdraft",
        "fg-ar-transactions-failed",
        "fg-ar-posting-level",
        "fg-ar-drill-subledger-on-txn",
        "fg-ar-drill-transfer-on-txn",
        "fg-ar-drill-ledger-on-balances-subledger",
        "fg-ar-drill-activity-date-on-txn",
        "fg-ar-drill-transfer-type-on-txn",
    }

    def test_filter_group_ids(self, ar_dashboard_definition):
        groups = ar_dashboard_definition.get("FilterGroups", [])
        ids = {g["FilterGroupId"] for g in groups}
        assert ids == self.EXPECTED_IDS

    def test_filter_group_ids_unique(self, ar_dashboard_definition):
        groups = ar_dashboard_definition.get("FilterGroups", [])
        ids = [g["FilterGroupId"] for g in groups]
        assert len(ids) == len(set(ids))

    def test_ledger_drill_scoped_to_subledger_table_only(
        self, ar_dashboard_definition,
    ):
        """Guard against a regression where the ledger drill-down filter
        applies to the ledger table itself — which would empty the ledger
        table when a user right-clicks a ledger row."""
        groups = ar_dashboard_definition.get("FilterGroups", [])
        fg = next(
            g for g in groups
            if g["FilterGroupId"] == "fg-ar-drill-ledger-on-balances-subledger"
        )
        scope = fg["ScopeConfiguration"]["SelectedSheets"][
            "SheetVisualScopingConfigurations"
        ][0]
        assert scope["Scope"] == "SELECTED_VISUALS"
        assert scope["VisualIds"] == ["ar-balances-subledger-table"]


class TestDatasetDeclarations:
    def test_all_datasets_declared(
        self, ar_dashboard_definition, ar_dataset_ids,
    ):
        decls = ar_dashboard_definition["DataSetIdentifierDeclarations"]
        declared_ds_ids = {d["DataSetArn"].split("/")[-1] for d in decls}
        for ds_id in ar_dataset_ids:
            assert ds_id in declared_ds_ids, (
                f"AR dataset {ds_id} not declared in dashboard definition"
            )
