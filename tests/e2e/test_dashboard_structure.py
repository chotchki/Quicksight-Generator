"""API tests: validate the deployed dashboard definition matches expectations."""

from __future__ import annotations

import pytest


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
    def test_has_five_sheets(self, dashboard_definition):
        sheets = dashboard_definition["Sheets"]
        assert len(sheets) == 5

    def test_sheet_names(self, dashboard_definition):
        names = {s["Name"] for s in dashboard_definition["Sheets"]}
        expected = {
            "Sales Overview",
            "Settlements",
            "Payments",
            "Exceptions & Alerts",
            "Payment Reconciliation",
        }
        assert names == expected, f"Sheet names mismatch: {names}"

    def test_every_sheet_has_visuals(self, dashboard_definition):
        for sheet in dashboard_definition["Sheets"]:
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
        "Exceptions & Alerts": 4,
        "Payment Reconciliation": 6,
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
        # Financial (5 shared) + 2 settlement drill-down + 4 recon + 2 recon drill-down
        assert len(groups) >= 10

    def test_filter_group_ids_unique(self, dashboard_definition):
        groups = dashboard_definition.get("FilterGroups", [])
        ids = [g["FilterGroupId"] for g in groups]
        assert len(ids) == len(set(ids))


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
