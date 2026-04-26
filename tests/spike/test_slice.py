"""M.0 spike — smoke test for the vertical-slice pipeline.

One test file, two tests:
- ``test_pipeline_artifacts`` walks the load → schema → seed → dashboard →
  handbook chain on the actual ``slice.yaml`` and asserts the load-bearing
  shape of each artifact.
- ``test_handbook_screenshot_reference`` checks the persona-substitution +
  screenshot-embed wiring without requiring real Playwright deployment.

Spike's testing budget per PLAN M.0.5: shape-learning, not coverage. The
proper M.1 test suite gets per-primitive coverage + rejection tests +
hash-locks (per the M.1.6/.7/.8 substeps).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from quicksight_gen.common.config import Config
from quicksight_gen.l2_spike.emit import (
    build_dashboard,
    emit_schema_sql,
    emit_seed_sql,
    render_handbook,
)
from quicksight_gen.l2_spike.loader import load


SLICE_YAML = Path(__file__).parent / "slice.yaml"


def _spike_cfg() -> Config:
    return Config(
        aws_account_id="111122223333",
        aws_region="us-west-2",
        datasource_arn=(
            "arn:aws:quicksight:us-west-2:111122223333:datasource/spk-ds"
        ),
        theme_preset="default",
        resource_prefix="spk",
    )


def test_pipeline_artifacts() -> None:
    """Walk load → schema → seed → dashboard, asserting each artifact's shape."""
    inst = load(SLICE_YAML)
    assert inst.instance == "spk"
    assert len(inst.accounts) == 2
    assert {a.id for a in inst.accounts} == {"int-001", "ext-001"}
    assert {a.role for a in inst.accounts} == {"InternalDDA", "ExternalCounterparty"}
    assert len(inst.rails) == 1
    rail = inst.rails[0]
    assert rail.name == "ExtInbound"
    assert rail.source_role == "ExternalCounterparty"
    assert rail.destination_role == "InternalDDA"
    assert rail.expected_net == Decimal("0")

    schema_sql = emit_schema_sql(inst)
    assert "CREATE TABLE spk_transactions" in schema_sql
    assert "CREATE TABLE spk_daily_balances" in schema_sql
    assert "CREATE VIEW spk_current_transactions" in schema_sql
    assert "CREATE VIEW spk_current_daily_balances" in schema_sql

    seed_sql = emit_seed_sql(inst)
    # 5 transfers × 2 legs = 10 transactions, all values inline.
    assert seed_sql.count("INSERT INTO spk_transactions") == 1
    assert seed_sql.count("'tx-001-debit'") == 1
    assert seed_sql.count("'tx-005-credit'") == 1
    # 1 stored-balance row planted at $450 (drift = -$50 from $500 sum).
    assert "INSERT INTO spk_daily_balances" in seed_sql
    assert "450.00" in seed_sql

    cfg = _spike_cfg()
    app = build_dashboard(inst, cfg)
    analysis = app.emit_analysis()
    assert analysis.Name == "Drift Exceptions"
    assert len(analysis.Definition.Sheets) == 1
    drift_sheet = analysis.Definition.Sheets[0]
    assert drift_sheet.Name == "Drift"
    # 1 KPI + 1 detail table.
    assert len(drift_sheet.Visuals) == 2
    decls = analysis.Definition.DataSetIdentifierDeclarations
    assert [d.Identifier for d in decls] == ["drift-view"]


def test_handbook_screenshot_reference() -> None:
    """Persona substitution + screenshot-embed wiring without Playwright."""
    inst = load(SLICE_YAML)
    handbook = render_handbook(inst, screenshot_path="drift-sheet.png")

    # Persona substitution: account display name (not ID) appears in prose.
    assert "Internal Operations Account" in handbook
    # ID still appears (in code-quoted form per the template).
    assert "`int-001`" in handbook
    # Screenshot embed wires the path through.
    assert "![Drift sheet](drift-sheet.png)" in handbook
    # Sasquatch leakage check — institution-blind handbook should never
    # mention demo personas the spike's L2 instance didn't declare.
    assert "Sasquatch" not in handbook
    assert "Bigfoot" not in handbook
