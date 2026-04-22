"""API tests: validate the deployed AR dashboard definition matches expectations.

Phase K.1 reshaped Exceptions: the legacy single-sheet check inventory
(47 visuals across 14 per-check blocks) was replaced by Today's
Exceptions (3 visuals: total KPI + breakdown + unified table) and
Exceptions Trends (7 visuals: drift timelines + KPI/table rollup pairs +
aging matrix + per-check trend). The four sheet-pinned drift-only
filter groups went away with the per-check KPIs.
"""

from __future__ import annotations

import pytest

from quicksight_gen.apps.account_recon.constants import (
    ALL_FG_AR_IDS,
    ALL_P_AR,
    FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER,
    V_AR_BALANCES_SUBLEDGER_TABLE,
    V_AR_DS_KPI_CLOSING,
    V_AR_DS_KPI_CREDITS,
    V_AR_DS_KPI_DEBITS,
    V_AR_DS_KPI_DRIFT,
    V_AR_DS_KPI_OPENING,
    V_AR_DS_TRANSACTIONS_TABLE,
    V_AR_TXN_BAR_BY_DAY,
    V_AR_TXN_BAR_BY_STATUS,
)


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
        "Today's Exceptions",
        "Exceptions Trends",
        "Daily Statement",
    ]

    def test_has_seven_sheets(self, ar_dashboard_definition):
        assert len(ar_dashboard_definition["Sheets"]) == 7

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
        # Phase K.1.2 — total KPI + breakdown bar + unified table
        "Today's Exceptions": 3,
        # Phase K.1.3 — drift timelines (1) + 2 KPI/table rollup pairs (4)
        # + aging matrix + per-check trend = 7
        "Exceptions Trends": 7,
        # Phase I.2 — 5 KPIs (opening / debits / credits / closing / drift)
        # + 1 transaction-detail table
        "Daily Statement": 6,
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

    def test_transactions_has_bar_by_day(self, ar_dashboard_definition):
        """Phase 4 added the Transactions-by-day chart alongside by-status."""
        txn_sheet = next(
            s for s in ar_dashboard_definition["Sheets"]
            if s["Name"] == "Transactions"
        )
        ids = set(_visual_ids(txn_sheet))
        assert V_AR_TXN_BAR_BY_STATUS in ids
        assert V_AR_TXN_BAR_BY_DAY in ids

    def test_daily_statement_has_kpi_strip_and_table(
        self, ar_dashboard_definition,
    ):
        """Phase I.2 — Daily Statement sheet must surface all 5 KPIs and
        the transaction-detail table, in stable IDs the handbook walkthrough
        will reference. A regression that drops any one of these would break
        the walkthrough's screenshot anchors."""
        ds_sheet = next(
            s for s in ar_dashboard_definition["Sheets"]
            if s["Name"] == "Daily Statement"
        )
        ids = set(_visual_ids(ds_sheet))
        for expected in (
            V_AR_DS_KPI_OPENING,
            V_AR_DS_KPI_DEBITS,
            V_AR_DS_KPI_CREDITS,
            V_AR_DS_KPI_CLOSING,
            V_AR_DS_KPI_DRIFT,
            V_AR_DS_TRANSACTIONS_TABLE,
        ):
            assert expected in ids, (
                f"Daily Statement missing visual '{expected}'"
            )


class TestParameters:
    def _names(self, definition: dict) -> set[str]:
        names: set[str] = set()
        for p in definition.get("ParameterDeclarations", []):
            for decl in p.values():
                if isinstance(decl, dict) and "Name" in decl:
                    names.add(decl["Name"])
        return names

    def test_drill_down_parameters(self, ar_dashboard_definition):
        # 6 drill-down parameters (Phase D + K.2 pArAccountId) + 2 Daily
        # Statement parameters (Phase I.2). pArDsBalanceDate is a DateTime
        # parameter; the rest are String parameters.
        assert self._names(ar_dashboard_definition) == {p.name for p in ALL_P_AR}


class TestFilterGroups:
    def test_filter_group_ids(self, ar_dashboard_definition):
        groups = ar_dashboard_definition.get("FilterGroups", [])
        ids = {g["FilterGroupId"] for g in groups}
        assert ids == ALL_FG_AR_IDS

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
            if g["FilterGroupId"] == FG_AR_DRILL_LEDGER_ON_BALANCES_SUBLEDGER
        )
        scope = fg["ScopeConfiguration"]["SelectedSheets"][
            "SheetVisualScopingConfigurations"
        ][0]
        assert scope["Scope"] == "SELECTED_VISUALS"
        assert scope["VisualIds"] == [V_AR_BALANCES_SUBLEDGER_TABLE]


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
