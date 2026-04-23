"""API tests: validate the deployed Investigation dashboard definition.

Five sheets: Getting Started + four investigation surfaces (Recipient
Fanout / Volume Anomalies / Money Trail / Account Network). The
Account Network sheet's two side-by-side directional Sankeys are the
load-bearing K.4.8 invariant — both must declare distinct visual IDs
so the layout encodes direction in geometry rather than in node
position inside one big Sankey.
"""

from __future__ import annotations

import pytest

from quicksight_gen.apps.investigation.app import build_investigation_app
from quicksight_gen.apps.investigation.constants import (
    V_INV_ANETWORK_SANKEY_INBOUND,
    V_INV_ANETWORK_SANKEY_OUTBOUND,
    V_INV_ANETWORK_TABLE,
    V_INV_MONEY_TRAIL_SANKEY,
    V_INV_MONEY_TRAIL_TABLE,
)


pytestmark = [pytest.mark.e2e, pytest.mark.api]


@pytest.fixture(scope="module")
def inv_dashboard_definition(qs_client, account_id, inv_dashboard_id) -> dict:
    resp = qs_client.describe_dashboard_definition(
        AwsAccountId=account_id,
        DashboardId=inv_dashboard_id,
    )
    return resp["Definition"]


@pytest.fixture(scope="module")
def inv_app(cfg):
    """Build the Investigation tree and resolve auto-IDs.

    The tree is the source of truth — the deployed dashboard's filter
    group / parameter sets must equal the tree's emitted set. emit_analysis()
    runs _resolve_auto_ids() in place, so reading off
    ``app.analysis.parameters`` / ``app.analysis.filter_groups`` after the
    call gives the resolved IDs that should match the deployed definition.
    """
    app = build_investigation_app(cfg)
    app.emit_analysis()
    return app


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
        "Recipient Fanout",
        "Volume Anomalies",
        "Money Trail",
        "Account Network",
    ]

    def test_has_five_sheets(self, inv_dashboard_definition):
        assert len(inv_dashboard_definition["Sheets"]) == 5

    def test_sheet_order(self, inv_dashboard_definition):
        names = [s["Name"] for s in inv_dashboard_definition["Sheets"]]
        assert names == self.EXPECTED_NAMES

    def test_every_sheet_has_description(self, inv_dashboard_definition):
        for sheet in inv_dashboard_definition["Sheets"]:
            desc = sheet.get("Description", "")
            assert len(desc) > 20, (
                f"Sheet '{sheet['Name']}' missing description"
            )


class TestVisuals:
    EXPECTED_VISUAL_COUNTS = {
        # Getting Started is text-only (welcome + roadmap text boxes).
        "Recipient Fanout": 4,       # 3 KPIs + table
        "Volume Anomalies": 3,       # KPI + distribution chart + table
        "Money Trail": 2,            # Sankey + hop-by-hop table
        "Account Network": 3,        # inbound Sankey + outbound Sankey + table
    }

    def test_visual_counts_per_sheet(self, inv_dashboard_definition):
        for sheet in inv_dashboard_definition["Sheets"]:
            name = sheet["Name"]
            expected = self.EXPECTED_VISUAL_COUNTS.get(name)
            if expected is None:
                continue
            actual = len(sheet.get("Visuals", []))
            assert actual == expected, (
                f"Sheet '{name}' has {actual} visuals, expected {expected}"
            )

    def test_all_visual_ids_unique(self, inv_dashboard_definition):
        all_ids: list[str] = []
        for sheet in inv_dashboard_definition["Sheets"]:
            all_ids.extend(_visual_ids(sheet))
        assert len(all_ids) == len(set(all_ids)), (
            f"Duplicate visual IDs: "
            f"{[vid for vid in all_ids if all_ids.count(vid) > 1]}"
        )

    def test_every_visual_has_subtitle(self, inv_dashboard_definition):
        for sheet in inv_dashboard_definition["Sheets"]:
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

    def test_money_trail_has_sankey_and_table(self, inv_dashboard_definition):
        sheet = next(
            s for s in inv_dashboard_definition["Sheets"]
            if s["Name"] == "Money Trail"
        )
        ids = set(_visual_ids(sheet))
        assert V_INV_MONEY_TRAIL_SANKEY in ids
        assert V_INV_MONEY_TRAIL_TABLE in ids

    def test_account_network_has_two_directional_sankeys_and_table(
        self, inv_dashboard_definition,
    ):
        """K.4.8i invariant — direction must be encoded in geometry. A
        regression that drops one Sankey or merges them back into one
        omnidirectional view would silently put the analyst back into the
        anchor-disambiguation problem the redesign solved."""
        sheet = next(
            s for s in inv_dashboard_definition["Sheets"]
            if s["Name"] == "Account Network"
        )
        ids = set(_visual_ids(sheet))
        for expected in (
            V_INV_ANETWORK_SANKEY_INBOUND,
            V_INV_ANETWORK_SANKEY_OUTBOUND,
            V_INV_ANETWORK_TABLE,
        ):
            assert expected in ids, (
                f"Account Network missing visual '{expected}'"
            )


class TestParameters:
    def _names(self, definition: dict) -> set[str]:
        names: set[str] = set()
        for p in definition.get("ParameterDeclarations", []):
            for decl in p.values():
                if isinstance(decl, dict) and "Name" in decl:
                    names.add(decl["Name"])
        return names

    def test_all_parameters_declared(self, inv_dashboard_definition, inv_app):
        # The tree's parameter set is the source of truth — deployed must
        # match exactly. K.4.3 fanout-threshold + K.4.4 anomalies-sigma +
        # K.4.5 money-trail-root + max-hops + min-amount + K.4.8 anchor +
        # min-amount = 7 today; the assert tracks adds/removes automatically.
        expected = {str(p.name) for p in inv_app.analysis.parameters}
        assert self._names(inv_dashboard_definition) == expected


class TestFilterGroups:
    def test_filter_group_ids(self, inv_dashboard_definition, inv_app):
        groups = inv_dashboard_definition.get("FilterGroups", [])
        deployed = {g["FilterGroupId"] for g in groups}
        expected = {str(fg.filter_group_id) for fg in inv_app.analysis.filter_groups}
        assert deployed == expected

    def test_filter_group_ids_unique(self, inv_dashboard_definition):
        groups = inv_dashboard_definition.get("FilterGroups", [])
        ids = [g["FilterGroupId"] for g in groups]
        assert len(ids) == len(set(ids))


class TestDatasetDeclarations:
    def test_all_datasets_declared(
        self, inv_dashboard_definition, inv_dataset_ids,
    ):
        decls = inv_dashboard_definition["DataSetIdentifierDeclarations"]
        declared_ds_ids = {d["DataSetArn"].split("/")[-1] for d in decls}
        for ds_id in inv_dataset_ids:
            assert ds_id in declared_ds_ids, (
                f"Investigation dataset {ds_id} not declared in dashboard"
            )
