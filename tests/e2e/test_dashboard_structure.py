"""API tests: validate the deployed dashboard definition matches expectations."""

from __future__ import annotations

import pytest

from quicksight_gen.payment_recon.constants import (
    FG_PR_PAYMENT_METHOD,
    FG_PR_PAYMENTS_UNMATCHED,
    FG_PR_SALES_UNSETTLED,
    FG_PR_SETTLEMENTS_UNPAID,
    SalesMeta,
)


pytestmark = [pytest.mark.e2e, pytest.mark.api]


@pytest.fixture(scope="module")
def dashboard_definition(qs_client, account_id, dashboard_id) -> dict:
    """Fetch the full dashboard definition from AWS."""
    resp = qs_client.describe_dashboard_definition(
        AwsAccountId=account_id,
        DashboardId=dashboard_id,
    )
    return resp["Definition"]


class TestSheets:
    def test_has_six_sheets(self, dashboard_definition):
        sheets = dashboard_definition["Sheets"]
        assert len(sheets) == 6

    def test_sheet_names(self, dashboard_definition):
        names = {s["Name"] for s in dashboard_definition["Sheets"]}
        expected = {
            "Getting Started",
            "Sales Overview",
            "Settlements",
            "Payments",
            "Exceptions & Alerts",
            "Payment Reconciliation",
        }
        assert names == expected, f"Sheet names mismatch: {names}"

    def test_getting_started_is_first(self, dashboard_definition):
        sheets = dashboard_definition["Sheets"]
        assert sheets[0]["Name"] == "Getting Started"

    def test_every_data_sheet_has_visuals(self, dashboard_definition):
        """Every sheet except Getting Started must carry visuals."""
        for sheet in dashboard_definition["Sheets"]:
            if sheet["Name"] == "Getting Started":
                continue
            visuals = sheet.get("Visuals", [])
            assert len(visuals) > 0, (
                f"Sheet '{sheet['Name']}' has no visuals"
            )

    def test_every_sheet_has_description(self, dashboard_definition):
        for sheet in dashboard_definition["Sheets"]:
            desc = sheet.get("Description", "")
            assert len(desc) > 20, (
                f"Sheet '{sheet['Name']}' has no meaningful description"
            )


class TestVisuals:
    EXPECTED_VISUAL_COUNTS = {
        "Sales Overview": 5,
        "Settlements": 4,
        "Payments": 4,
        "Exceptions & Alerts": 12,
        "Payment Reconciliation": 7,
    }

    def test_visual_counts_per_sheet(self, dashboard_definition):
        for sheet in dashboard_definition["Sheets"]:
            name = sheet["Name"]
            visuals = sheet.get("Visuals", [])
            expected = self.EXPECTED_VISUAL_COUNTS.get(name)
            if expected is not None:
                assert len(visuals) == expected, (
                    f"Sheet '{name}' has {len(visuals)} visuals, expected {expected}"
                )

    def test_all_visual_ids_unique(self, dashboard_definition):
        all_ids = []
        for sheet in dashboard_definition["Sheets"]:
            for v in sheet.get("Visuals", []):
                for vtype in v.values():
                    if isinstance(vtype, dict) and "VisualId" in vtype:
                        all_ids.append(vtype["VisualId"])
        assert len(all_ids) == len(set(all_ids)), (
            f"Duplicate visual IDs: "
            f"{[vid for vid in all_ids if all_ids.count(vid) > 1]}"
        )

    def test_every_visual_has_subtitle(self, dashboard_definition):
        for sheet in dashboard_definition["Sheets"]:
            for v in sheet.get("Visuals", []):
                for vtype in v.values():
                    if isinstance(vtype, dict) and "VisualId" in vtype:
                        subtitle = vtype.get("Subtitle", {})
                        fmt = subtitle.get("FormatText", {})
                        text = fmt.get("PlainText", "")
                        assert len(text) > 10, (
                            f"Visual '{vtype['VisualId']}' has no subtitle"
                        )

    def test_exceptions_has_new_mismatch_tables(self, dashboard_definition):
        exc_sheet = next(
            s for s in dashboard_definition["Sheets"]
            if s["Name"] == "Exceptions & Alerts"
        )
        ids = []
        for v in exc_sheet.get("Visuals", []):
            for vtype in v.values():
                if isinstance(vtype, dict) and "VisualId" in vtype:
                    ids.append(vtype["VisualId"])
        for expected in (
            "exceptions-sale-settlement-mismatch-table",
            "exceptions-settlement-payment-mismatch-table",
            "exceptions-unmatched-ext-txn-table",
        ):
            assert expected in ids, f"Missing exception table '{expected}'"


class TestParameters:
    def test_has_settlement_id_parameter(self, dashboard_definition):
        params = dashboard_definition.get("ParameterDeclarations", [])
        names = set()
        for p in params:
            for decl in p.values():
                if isinstance(decl, dict) and "Name" in decl:
                    names.add(decl["Name"])
        assert "pSettlementId" in names

    def test_has_external_txn_id_parameter(self, dashboard_definition):
        params = dashboard_definition.get("ParameterDeclarations", [])
        names = set()
        for p in params:
            for decl in p.values():
                if isinstance(decl, dict) and "Name" in decl:
                    names.add(decl["Name"])
        assert "pExternalTransactionId" in names


class TestFilterGroups:
    def test_has_filter_groups(self, dashboard_definition):
        groups = dashboard_definition.get("FilterGroups", [])
        # core pipeline + 3 state toggles + 4 optional metadata
        # + settlement/payment drill-downs + 3 recon + 2 recon drill-downs
        assert len(groups) >= 18

    def test_filter_group_ids_unique(self, dashboard_definition):
        groups = dashboard_definition.get("FilterGroups", [])
        ids = [g["FilterGroupId"] for g in groups]
        assert len(ids) == len(set(ids))

    def test_payment_method_filter_present(self, dashboard_definition):
        groups = dashboard_definition.get("FilterGroups", [])
        ids = {g["FilterGroupId"] for g in groups}
        assert FG_PR_PAYMENT_METHOD in ids

    def test_optional_metadata_filters_present(self, dashboard_definition):
        groups = dashboard_definition.get("FilterGroups", [])
        ids = {g["FilterGroupId"] for g in groups}
        for col in ("taxes", "tips", "discount_percentage", "cashier"):
            fg_id = SalesMeta(col).fg_id
            assert fg_id in ids, (
                f"Missing optional metadata filter for '{col}'"
            )

    def test_state_toggles_and_no_days_outstanding(self, dashboard_definition):
        """Sales/Settlements/Payments expose a Show-Only-X toggle; no tab
        should still carry the retired days-outstanding slider."""
        ids = {g["FilterGroupId"] for g in dashboard_definition.get("FilterGroups", [])}
        for fg_id in (
            FG_PR_SALES_UNSETTLED,
            FG_PR_SETTLEMENTS_UNPAID,
            FG_PR_PAYMENTS_UNMATCHED,
        ):
            assert fg_id in ids, f"Missing state toggle filter group '{fg_id}'"
        stale = [fg_id for fg_id in ids if "days-outstanding" in fg_id]
        assert not stale, f"Found stale days-outstanding filter groups: {stale}"


class TestDatasetDeclarations:
    def test_all_datasets_declared(self, dashboard_definition, dataset_ids):
        decls = dashboard_definition["DataSetIdentifierDeclarations"]
        declared_ds_ids = set()
        for d in decls:
            ds_id = d["DataSetArn"].split("/")[-1]
            declared_ds_ids.add(ds_id)
        for ds_id in dataset_ids:
            assert ds_id in declared_ds_ids, (
                f"Dataset {ds_id} not declared in dashboard definition"
            )
