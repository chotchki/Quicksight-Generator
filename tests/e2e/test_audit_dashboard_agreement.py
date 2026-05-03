"""U.8.b.3 — Drift-only three-way agreement (wiring lap).

Single-invariant smoke for U.8.b's release-gate contract:
    expected (from scenario) == PDF (extractor) == dashboard (Playwright)

Locks the wiring before the U.8.b.4 fanout to the remaining
invariants. Drift gets the wiring lap because the dashboard's
"Leaf Account Drift" table is the closest 1:1 with the PDF's
single drift table — overdraft / limit_breach / stuck_* split into
parent + child sub-tables that need per-invariant translation
between the dashboard's and PDF's row-grouping shapes (handled in
U.8.b.4's fanout).

Prerequisites (test skips if missing):
  - ``QS_GEN_E2E=1`` (matches existing browser-test gate)
  - The L1 dashboard for the default L2 instance (``spec_example``)
    is already deployed; ``run_e2e.sh`` or ``json apply --execute``
    against ``spec_example`` is the canonical pre-step
  - ``cfg.demo_database_url`` is configured (the test seeds the DB
    with a known scenario before asserting)

The scenario seed runs against the real ``demo_database_url`` —
DESTRUCTIVE for the ``spec_example_*`` prefix. Other prefixes (the
operator's actual data) are untouched because the schema apply only
drops + recreates the prefixed objects.

Anchors on ``date.today()`` (not the M.2a.8 hash-lock 2030 date):
the stuck_pending / stuck_unbundled matviews compute age via
``CURRENT_TIMESTAMP - posting``, so plants pinned to a far-future
date land in the SQL future and never satisfy the age threshold.
Anchoring on real today keeps plants visible across all 6
invariants — though this test only checks drift, the conftest
fixture is shared with the U.8.b.4 fanout that does check stuck_*.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.cli import main
from quicksight_gen.common.browser.helpers import (
    generate_dashboard_embed_url,
    wait_for_dashboard_loaded,
    webkit_page,
)
from quicksight_gen.common.db import connect_demo_db
from quicksight_gen.common.l2 import load_instance
from quicksight_gen.common.sql import Dialect

from tests.audit._dashboard_extract import count_l1_invariant_rows
from tests.audit._pdf_extract import count_invariant_table_rows
from tests.audit._scenario_expectations import expected_audit_counts


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


_FIXTURES = Path(__file__).parent.parent / "l2"
_SPEC_EXAMPLE = _FIXTURES / "spec_example.yaml"

# Anchor on real today so the stuck_* matviews' CURRENT_TIMESTAMP
# filter sees plants in the past. days_ago offsets stay deterministic;
# only the absolute calendar date varies. The audit period [_TODAY - 7,
# _TODAY - 1] then contains the plant effective dates by construction.
_TODAY = date.today()
_PERIOD: tuple[date, date] = (
    _TODAY - timedelta(days=7),
    _TODAY - timedelta(days=1),
)


def _resolve_cfg_path() -> Path | None:
    """Find the cfg path the e2e fixtures already loaded.

    Mirrors the conftest's candidate-list resolution so we can pass
    `-c PATH` to ``audit apply`` against the same config the embed
    URL was built from. Returns None if no candidate exists; the
    test will skip cleanly.
    """
    import os

    explicit = os.environ.get("QS_GEN_CONFIG")
    if explicit:
        return Path(explicit)
    for candidate in (
        Path("config.yaml"),
        Path("run/config.yaml"),
        Path("run/config.postgres.yaml"),
        Path("run/config.oracle.yaml"),
    ):
        if candidate.exists():
            return candidate
    return None


@pytest.fixture(scope="module")
def cfg_path():
    p = _resolve_cfg_path()
    if p is None:
        pytest.skip(
            "No config.yaml found on candidate paths; set "
            "QS_GEN_CONFIG to point at the file used for the deploy."
        )
    return p


@pytest.fixture(scope="module")
def seeded_audit(cfg, cfg_path, tmp_path_factory):
    """Seed DB with the spec_example scenario, render audit PDF.

    Module-scoped — the seed + render is the expensive setup; both
    the dashboard walk and the PDF extraction reuse the same
    artifacts. Returns ``(pdf_path, scenario)``.
    """
    from tests.e2e._harness_seed import apply_db_seed

    if cfg.demo_database_url is None:
        pytest.skip(
            "demo_database_url not configured — three-way agreement "
            "test requires a seedable DB."
        )

    instance = load_instance(_SPEC_EXAMPLE)
    dialect = (
        Dialect.ORACLE
        if (cfg.dialect or "").lower() == "oracle"
        else Dialect.POSTGRES
    )
    conn = connect_demo_db(cfg)
    try:
        scenario = apply_db_seed(
            conn, instance,
            mode="l1_invariants",
            today=_TODAY,
            dialect=dialect,
            include_baseline=False,
        )
    finally:
        conn.close()

    out = tmp_path_factory.mktemp("audit-pdf") / "report.pdf"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "audit", "apply",
            "-c", str(cfg_path),
            "--l2", str(_SPEC_EXAMPLE),
            "--from", _PERIOD[0].isoformat(),
            "--to", _PERIOD[1].isoformat(),
            "-o", str(out),
            "--execute",
        ],
    )
    assert result.exit_code == 0, result.output
    return (out, scenario)


@pytest.fixture
def embed_url(region, account_id, l1_dashboard_id, qs_client) -> str:
    """Function-scoped — embed URLs are single-use, fresh per test.

    Pre-flight: confirm the dashboard actually exists before
    generating the embed URL. ``generate_dashboard_embed_url``
    happily returns a URL pointing at a non-existent dashboard,
    which then loads as an empty QS error page that times out the
    "wait for sheet tabs" gate with a confusing 30s timeout. A
    proactive ``describe_dashboard`` check turns that into an
    immediate skip with the actual deploy command to fix it.
    """
    try:
        qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=l1_dashboard_id,
        )
    except qs_client.exceptions.ResourceNotFoundException:
        pytest.skip(
            f"L1 dashboard {l1_dashboard_id!r} not deployed in "
            f"account {account_id} region {region}. Deploy it "
            f"first: `quicksight-gen json apply -c <cfg> "
            f"--execute` against the default L2 instance "
            f"(spec_example), then re-run this test."
        )
    return generate_dashboard_embed_url(
        aws_account_id=account_id,
        aws_region=region,
        dashboard_id=l1_dashboard_id,
    )


# All 6 L1 invariants. The current-state invariants
# (stuck_pending / stuck_unbundled / supersession) used to xfail with
# "No data found for visual" — root-caused to the L1 dashboard
# applying its `[today-7, today]` default date scope to matviews that
# have no date column on the audit-PDF side, dropping rows whose
# `posting` was outside the window even though the matview held them.
# Fixed by removing the date-scope FilterGroups from the current-state
# sheets (stucks are stuck until cleared regardless of analyst's
# period of interest); the audit PDF and dashboard now agree by
# construction.
_ALL_INVARIANTS: tuple[str, ...] = (
    "drift",
    "overdraft",
    "limit_breach",
    "stuck_pending",
    "stuck_unbundled",
    "supersession",
)


@pytest.mark.parametrize("invariant", _ALL_INVARIANTS)
def test_invariant_three_way_agreement(
    seeded_audit, embed_url, page_timeout, visual_timeout,
    invariant,
):
    """Per-invariant: PDF count and dashboard count both >= expected
    count, AND PDF count == dashboard count.

    Three asserts so a failure points at WHICH side broke:
      - expected > PDF: producer-side regression (SQL / matview /
        PDF rendering pipeline drifted from what the plant emitted)
      - expected > dashboard: same producer side, different output
        target (the dashboard reads the same matview, so unless QS
        is doing something exotic the numbers should match)
      - PDF != dashboard: the credibility contract broke directly —
        regulator and operator are seeing different numbers for the
        same matview + period

    NOTE on the strict ``PDF == dashboard`` assert: this works for
    drift because the PDF section and the dashboard's "Leaf Account
    Drift" table both show every drift matview row in one flat
    table. For other invariants the shapes diverge — the PDF
    aggregates parent + child accounts into a parent-per-row table
    + a "Child Accounts Grouped by Parent Role" table while the
    dashboard typically shows raw matview rows on its detail
    table. Where these counts diverge, it's a data-shape contract
    mismatch worth investigating, not necessarily a bug. U.8.b.4
    runs all 6 to surface every shape mismatch as concrete data;
    U.8.b's future work then either aligns the shapes or shifts
    the assert to row-identity matching (account_id + day) instead
    of count.
    """
    pdf_path, scenario = seeded_audit
    expected = getattr(
        expected_audit_counts(scenario, _PERIOD), f"{invariant}_count",
    )
    pdf_count = count_invariant_table_rows(pdf_path, invariant)

    # 1600×4000 — tall viewport so stacked KPI + chart + table layouts
    # (Pending Aging / Unbundled Aging / Supersession Audit) keep the
    # detail table inside the initial render area. QS lazy-renders
    # below-the-fold visuals; without the tall viewport,
    # count_table_total_rows times out waiting for cells that never
    # mount. Same pattern as the M.4.1.k harness.
    with webkit_page(headless=True, viewport=(1600, 4000)) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        dashboard_count = count_l1_invariant_rows(
            page, invariant, _PERIOD, timeout_ms=visual_timeout,
        )

    assert pdf_count >= expected, (
        f"Producer-side regression ({invariant}): scenario planted "
        f"{expected} rows but PDF shows only {pdf_count}. Plant "
        f"didn't reach the matview, or audit query / PDF render "
        f"dropped the row."
    )
    assert dashboard_count >= expected, (
        f"Producer-side regression ({invariant}): scenario planted "
        f"{expected} rows but dashboard shows only {dashboard_count}. "
        f"Plant didn't reach the matview."
    )
    assert dashboard_count == pdf_count, (
        f"Credibility contract broken ({invariant}): dashboard "
        f"shows {dashboard_count} rows, PDF shows {pdf_count}. "
        f"Same period ({_PERIOD[0]}–{_PERIOD[1]}), same matview, "
        f"different counts."
    )
