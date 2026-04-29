"""End-to-end harness — `tests/test_harness_end_to_end.py` (M.4.1).

One harness parameterized over every `L2_INSTANCES` matrix entry. Each
per-instance test executes the full chain — load YAML → emit_schema to
a fresh per-test DB prefix → auto-scenario + emit_seed → DB apply →
matview refresh → generate l1-dashboard + generate l2-flow-tracing →
deploy both to QS → Playwright asserts planted scenarios surface as
visible rows on the right sheets — and dumps a triage manifest on
failure.

This file lives under ``tests/e2e/`` so it inherits the
``QS_GEN_E2E=1`` skip gate from ``tests/e2e/conftest.py`` (no need to
re-implement). Per-test fixtures are scoped here (independent of the
shared session-scoped ``cfg`` fixture, which loads production
``config.yaml`` and is the wrong shape for a per-test ephemeral
deploy).

**M.4.1.a — Shared fixtures + cleanup scaffolding (this commit).**
Lands the fixture skeleton + per-test isolation + tag-filter cleanup
for every QS resource the harness deploys + DB schema drop. One smoke
test exercises the wiring without yet doing the deploy / Playwright
half. M.4.1.b–h fill in the actual harness body.

Per-test isolation strategy:
- Each test gets a unique short UID (``harness_uid`` fixture).
- The L2 instance is cloned with a derived prefix
  ``e2e_<original_instance>_<uid>`` so concurrent tests can't collide
  on shared schema names OR shared QS resource IDs.
- ``Config.extra_tags`` carries ``TestUid: <uid>`` + ``Harness: e2e``;
  ``Config.tags()`` already propagates these onto every QS resource.
- Teardown sweeps QS resources by ``TestUid`` tag (via
  ``_harness_cleanup.sweep_qs_resources_by_tag``) + drops the DB
  schema by ``e2e_*_<uid>`` prefix discovery (via
  ``_harness_cleanup.drop_prefixed_schema``).

Required env vars beyond the existing e2e set (see
``tests/e2e/conftest.py`` for the base set):
- ``QS_GEN_DEMO_DATABASE_URL`` — psycopg2 DSN for the harness's DB
  apply step. The existing conftest already reads this for
  ``cfg.demo_database_url`` derivation, so any environment running
  the production e2e suite already has it set.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

# Pull in the cleanup helpers from the sibling module (test-only path,
# not pip-installable from this layout, so import via sys.path).
sys.path.insert(0, str(Path(__file__).parent))
from _harness_cleanup import (  # noqa: E402
    drop_prefixed_schema,
    sweep_qs_resources_by_tag,
)
from _harness_seed import (  # noqa: E402
    apply_db_seed,
    build_planted_manifest,
)
from _harness_deploy import (  # noqa: E402
    HARNESS_APPS,
    build_embed_urls,
    extract_dashboard_ids,
    generate_apps,
)
from _harness_l1_assertions import (  # noqa: E402
    assert_l1_plants_visible,
    assert_todays_exceptions_kpi_matches,
)
from _harness_l2ft_assertions import (  # noqa: E402
    assert_l2_exceptions_check_types_present,
    assert_l2ft_plants_visible,
)

# L2_INSTANCES matrix: re-use the exact list `test_l2_seed_contract.py`
# uses so adding a new YAML there parameterizes the harness too.
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_l2_seed_contract import L2_INSTANCES  # noqa: E402

from quicksight_gen.common.config import Config
from quicksight_gen.common.l2 import L2Instance, load_instance
from quicksight_gen.common.l2.primitives import Identifier


# ---------------------------------------------------------------------------
# Per-test isolation fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def harness_uid() -> str:
    """Short unique string per test (suitable for DB prefix + QS tags).

    Constraints:
    - Stays under the L2 ``InstancePrefix`` 30-char cap (F5) — the prefix
      becomes ``e2e_<instance>_<uid>``, so the uid plus instance plus
      ``e2e_`` overhead must fit. 8 chars of UUID hex leaves room for
      L2 instance names up to ~17 chars (``sasquatch_pr`` = 12, fits).
    - Starts with a hex char (always [0-9a-f]) so the resulting prefix
      passes the loader's ``^[a-z][a-z0-9_]*$`` regex.
    """
    return uuid.uuid4().hex[:8]


@pytest.fixture(params=L2_INSTANCES)
def harness_l2(request, harness_uid: str) -> L2Instance:
    """Load the L2 YAML, then clone with an ephemeral per-test prefix.

    ``emit_schema`` reads the prefix from ``instance.instance`` directly
    (no separate ``prefix=`` arg), so the only way to give a test its
    own prefix is to clone the L2 instance with a different ``instance``
    field. The original on-disk YAML stays unmodified.

    The cloned instance also gets ``validate=False`` skipped — the
    original was already validated at load. Re-running the validator
    on the clone would be a wasted cycle.
    """
    yaml_path: Path = request.param
    original = load_instance(yaml_path)
    ephemeral_prefix = Identifier(f"e2e_{original.instance}_{harness_uid}")
    return dataclasses.replace(original, instance=ephemeral_prefix)


@pytest.fixture
def harness_cfg(harness_l2: L2Instance, harness_uid: str) -> Config:
    """Per-test ``Config`` with TestUid-tagged extra_tags.

    Env-var driven (NOT loading production config.yaml — the harness
    deploys to ephemeral resource IDs that have no relationship with
    the production deploy's ``out/`` directory).

    ``extra_tags`` is the M.4.1.a tag-injection point: ``TestUid``
    enables the per-test tag-filter sweep at teardown; ``Harness``
    is a coarse marker for "this came from the e2e harness, not the
    production deploy" (cheap to query at scale, useful for debugging
    if a leak ever shows up in the QS console).
    """
    aws_account_id = os.environ["QS_GEN_AWS_ACCOUNT_ID"]
    aws_region = os.environ["QS_GEN_AWS_REGION"]
    datasource_arn = os.environ.get("QS_GEN_DATASOURCE_ARN")
    demo_db_url = os.environ.get("QS_GEN_DEMO_DATABASE_URL")
    if datasource_arn is None and demo_db_url is None:
        raise RuntimeError(
            "harness needs QS_GEN_DATASOURCE_ARN or QS_GEN_DEMO_DATABASE_URL "
            "set; neither found in env"
        )
    return Config(
        aws_account_id=aws_account_id,
        aws_region=aws_region,
        datasource_arn=datasource_arn,
        demo_database_url=demo_db_url,
        extra_tags={"TestUid": harness_uid, "Harness": "e2e"},
        l2_instance_prefix=str(harness_l2.instance),
    )


@pytest.fixture
def harness_db_conn(harness_cfg: Config):
    """psycopg2 connection to the demo DB, with Aurora cold-start warmup.

    Connection is fixture-scoped (per-test) so each test gets its own
    connection — concurrent tests don't share a connection that one
    test's teardown might close out from under another. Yields the
    connection; teardown drops every prefixed object the test created.

    Aurora cold-start: the existing operational footgun (CLAUDE.md) is
    that Aurora Serverless V1's idle pause causes the first query to
    fail. Issue ``SELECT 1`` immediately after connecting so the
    cold-start hit lands on the warmup, not the first real
    ``emit_schema`` apply.
    """
    psycopg2 = pytest.importorskip(
        "psycopg2",
        reason="harness needs psycopg2 (install via `pip install -e '.[demo]'`)",
    )
    if harness_cfg.demo_database_url is None:
        pytest.skip("QS_GEN_DEMO_DATABASE_URL not set")
    conn = psycopg2.connect(harness_cfg.demo_database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        yield conn
    finally:
        # Always attempt schema cleanup — even if the test failed mid-way
        # the prefixed objects (if any made it in) need to come out so
        # the next test doesn't see leftover state.
        try:
            drop_prefixed_schema(conn, str(harness_cfg.l2_instance_prefix))
        except Exception as exc:  # noqa: BLE001 — best-effort teardown
            print(
                f"[harness] DB schema teardown failed for prefix "
                f"{harness_cfg.l2_instance_prefix!r}: {exc}",
                file=sys.stderr,
            )
        conn.close()


@pytest.fixture
def harness_seeded(harness_db_conn: Any, harness_l2: L2Instance):
    """Apply schema + seed + matview refresh; return the per-test
    handle the M.4.1.b–e harness body consumes (M.4.1.b).

    Three DB-side steps run via ``_harness_seed.apply_db_seed``:
    emit_schema → emit_seed (mode='l1_plus_broad' so both L1 SHOULD
    plants and broad-mode rail firings land) → refresh_matviews_sql.
    Each commits independently so a mid-flow failure leaves the DB in
    a known state for ``harness_db_conn``'s teardown to drop cleanly.

    Returns a dict with three keys downstream Playwright assertions
    (M.4.1.d/e) consume:
      - ``instance``: the per-test L2Instance (already cloned with the
        ephemeral prefix)
      - ``prefix``: the same prefix as a string, for SQL-emit /
        boto3 ID derivation convenience
      - ``planted_manifest``: dict of plant-kind → list-of-row-finder
        dicts (see ``_harness_seed.build_planted_manifest`` for the
        shape; M.4.1.f's failure dump consumes the same dict)
    """
    scenario = apply_db_seed(harness_db_conn, harness_l2)
    return {
        "instance": harness_l2,
        "prefix": str(harness_l2.instance),
        "planted_manifest": build_planted_manifest(scenario),
    }


@pytest.fixture
def harness_deployed(
    tmp_path: Path,
    harness_seeded: dict[str, Any],
    harness_cfg: Config,
    harness_qs_cleanup: None,
) -> dict[str, Any]:
    """Generate + deploy both apps + build embed URLs (M.4.1.c).

    Pulls together the M.4.1.b harness_seeded handle and the
    M.4.1.a harness_qs_cleanup teardown, then runs the deploy chain:

    1. ``generate_apps`` writes theme + per-app analysis/dashboard +
       per-dataset JSON to ``tmp_path``. Datasource skipped (uses
       cfg.datasource_arn from env).
    2. ``common.deploy.deploy()`` does the delete-then-create dance
       on QS for both apps' resources, waits for
       ``CREATION_SUCCESSFUL``. The harness's ``cfg.tags()`` carry
       the M.4.1.a TestUid + Harness tags so every created resource
       is reapable by the cleanup fixture's tag-filter sweep.
    3. ``extract_dashboard_ids`` reads the dashboard JSONs back to
       recover the QS DashboardId per app.
    4. ``build_embed_urls`` generates one signed embed URL per
       dashboard via the identity-region QS client.

    Depends on ``harness_qs_cleanup`` (the underscore-prefixed
    pytest declaration is fine — pytest evaluates fixture dependencies
    by name, so requesting ``harness_qs_cleanup`` ensures the
    teardown runs after this test exits) so even a mid-deploy
    failure gets reaped.

    Returns ``{instance, prefix, planted_manifest, dashboard_ids,
    embed_urls}`` for the M.4.1.d/.e Playwright assertions.
    """
    from quicksight_gen.common.deploy import deploy as deploy_apps

    out_dir = tmp_path / "harness_out"
    instance = harness_seeded["instance"]

    # 1. Generate JSON for both apps.
    generate_apps(harness_cfg, instance, out_dir)

    # 2. Deploy via the existing CLI deploy (delete-then-create +
    # CREATION_SUCCESSFUL wait). Returns 0 on success.
    rc = deploy_apps(harness_cfg, out_dir, list(HARNESS_APPS))
    if rc != 0:
        raise RuntimeError(
            f"harness deploy failed for prefix "
            f"{harness_cfg.l2_instance_prefix!r}; see deploy stdout"
        )

    # 3. Recover dashboard IDs from the JSON the deploy step sent.
    dashboard_ids = extract_dashboard_ids(out_dir)

    # 4. Build per-test embed URLs. Identity-region client (us-east-1)
    # — the dashboard region is irrelevant for embed-URL signing.
    import boto3
    from tests.e2e.conftest import IDENTITY_REGION
    qs_identity = boto3.client("quicksight", region_name=IDENTITY_REGION)
    embed_urls = build_embed_urls(
        qs_identity,
        harness_cfg.aws_account_id,
        dashboard_ids,
    )

    return {
        "instance": instance,
        "prefix": harness_seeded["prefix"],
        "planted_manifest": harness_seeded["planted_manifest"],
        "dashboard_ids": dashboard_ids,
        "embed_urls": embed_urls,
    }


@pytest.fixture
def harness_qs_cleanup(harness_cfg: Config, harness_uid: str):
    """Yield, then sweep every QS resource carrying ``TestUid: <uid>``.

    Pure-teardown fixture — the actual deploy + Playwright assertions
    happen inside the test body. This fixture's only job is to
    guarantee that whatever the test deployed (or partially deployed
    before failing) gets reaped.

    Lazy boto3 import keeps the harness file loadable in environments
    without boto3 installed (e.g. the CI lint pass).
    """
    yield  # test runs
    try:
        import boto3
    except ImportError:
        # Test environment doesn't have boto3 — nothing to sweep.
        return
    qs = boto3.client("quicksight", region_name=harness_cfg.aws_region)
    counts = sweep_qs_resources_by_tag(
        qs,
        harness_cfg.aws_account_id,
        tag_key="TestUid",
        tag_value=harness_uid,
    )
    print(
        f"[harness] swept QS resources for TestUid={harness_uid}: {counts}",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Smoke test — fixtures wire up + tag injection lands
# ---------------------------------------------------------------------------


def test_harness_fixtures_wire_up(
    harness_uid: str,
    harness_l2: L2Instance,
    harness_cfg: Config,
) -> None:
    """The fixture chain assembles correctly: per-test UID, L2 instance
    cloned with an ``e2e_*_<uid>`` prefix, and Config carrying the
    expected ``TestUid`` + ``Harness`` extra tags so ``cfg.tags()``
    propagates them onto every deployed QS resource.

    No DB or AWS work — just verifies the per-test isolation contract.
    M.4.1.b–h add the actual deploy + Playwright assertions on top.
    """
    # Per-test UID is a short hex string.
    assert harness_uid
    assert all(c in "0123456789abcdef" for c in harness_uid)

    # L2 instance was cloned with an ephemeral prefix.
    assert str(harness_l2.instance).startswith("e2e_")
    assert harness_l2.instance.endswith(f"_{harness_uid}")

    # Config carries the harness tags AND propagates them via tags().
    assert harness_cfg.extra_tags == {
        "TestUid": harness_uid,
        "Harness": "e2e",
    }
    assert harness_cfg.l2_instance_prefix == str(harness_l2.instance)

    tag_dict = {t.Key: t.Value for t in harness_cfg.tags()}
    assert tag_dict["ManagedBy"] == "quicksight-gen"
    assert tag_dict["L2Instance"] == str(harness_l2.instance)
    assert tag_dict["TestUid"] == harness_uid
    assert tag_dict["Harness"] == "e2e"


# ---------------------------------------------------------------------------
# M.4.1.b smoke — DB-side seed fixture wires up + planted_manifest lands
# ---------------------------------------------------------------------------


def test_harness_seeded_fixture_lands_with_manifest(
    harness_seeded: dict[str, Any],
    harness_l2: L2Instance,
    harness_db_conn: Any,
) -> None:
    """The full DB-side fixture chain (schema → seed → matview refresh)
    runs cleanly and returns a usable handle for downstream M.4.1.c–e
    fixtures.

    Sanity-checks performed on the deployed DB state:
    1. The base table ``<prefix>_transactions`` exists and has rows
       (broad mode + L1 invariant plants both populate it).
    2. The ``<prefix>_current_transactions`` matview is fresh (rows
       there match the base table; if the refresh step were skipped
       the matview would be empty).
    3. The planted_manifest contains the expected plant kinds for
       l1_plus_broad mode (rail_firing_plants + transfer_template_plants
       at minimum, since these are the broad-layer plants every
       L2 instance with at least one Rail produces).

    Skipped under default pytest (no QS_GEN_E2E); requires Aurora
    via QS_GEN_DEMO_DATABASE_URL.
    """
    instance = harness_seeded["instance"]
    prefix = harness_seeded["prefix"]
    manifest = harness_seeded["planted_manifest"]

    # Sanity: instance handle round-trips.
    assert instance is harness_l2
    assert prefix == str(harness_l2.instance)

    # DB has the prefixed base table with rows.
    with harness_db_conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {prefix}_transactions")
        n_base = cur.fetchone()[0]
    assert n_base > 0, (
        f"{prefix}_transactions has no rows after apply_db_seed; "
        f"either seed planted nothing or schema apply silently failed"
    )

    # current_transactions matview is fresh (count matches base).
    with harness_db_conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {prefix}_current_transactions")
        n_current = cur.fetchone()[0]
    assert n_current == n_base, (
        f"{prefix}_current_transactions out of sync with base "
        f"({n_current} vs {n_base}); refresh_matviews_sql step missed"
    )

    # Manifest carries every plant-kind key the builder declares,
    # and at least the broad-layer kinds are non-empty (every L2
    # instance with rails produces rail_firing_plants in
    # l1_plus_broad mode).
    expected_kinds = {
        "drift_plants",
        "overdraft_plants",
        "limit_breach_plants",
        "stuck_pending_plants",
        "stuck_unbundled_plants",
        "supersession_plants",
        "transfer_template_plants",
        "rail_firing_plants",
    }
    assert set(manifest.keys()) == expected_kinds
    assert len(manifest["rail_firing_plants"]) > 0, (
        "broad mode should plant rail firings for every L2 instance "
        "with at least one Rail whose roles materialize"
    )


# ---------------------------------------------------------------------------
# M.4.1.c smoke — deploy fixture lands both apps + builds embed URLs
# ---------------------------------------------------------------------------


def test_harness_deployed_fixture_lands_with_embed_urls(
    harness_deployed: dict[str, Any],
) -> None:
    """The full deploy chain (generate → deploy → extract IDs →
    build embed URLs) runs cleanly and returns one URL per app.

    Sanity-checks the M.4.1.d/.e contract: both apps' dashboard ids
    + embed URLs are present and well-shaped. The planted_manifest
    + instance + prefix from M.4.1.b survive through the chain.

    Skipped under default pytest (no QS_GEN_E2E); requires QS account
    + region + datasource ARN env vars set, and Aurora available
    (transitively via M.4.1.b's harness_seeded dependency).
    """
    # Both apps deployed.
    dashboard_ids = harness_deployed["dashboard_ids"]
    assert set(dashboard_ids.keys()) == set(HARNESS_APPS)

    # Each dashboard ID carries the per-test L2 prefix (M.2d.3).
    prefix = harness_deployed["prefix"]
    expected_id_prefix = f"qs-gen-{prefix}-"
    for app_name, dashboard_id in dashboard_ids.items():
        assert dashboard_id.startswith(expected_id_prefix), (
            f"{app_name} dashboard_id {dashboard_id!r} doesn't carry "
            f"per-test prefix {expected_id_prefix!r} — check cfg flow"
        )

    # Embed URLs match the dashboard ids 1:1 and look like signed URLs.
    embed_urls = harness_deployed["embed_urls"]
    assert set(embed_urls.keys()) == set(HARNESS_APPS)
    for app_name, url in embed_urls.items():
        assert url.startswith("https://"), (
            f"{app_name} embed URL {url!r} doesn't look like a signed URL"
        )

    # M.4.1.b handles still present (so M.4.1.d/.e can iterate plants).
    assert harness_deployed["instance"] is not None
    assert harness_deployed["prefix"] == prefix
    assert "rail_firing_plants" in harness_deployed["planted_manifest"]


# ---------------------------------------------------------------------------
# M.4.1.d smoke — Playwright walks the L1 dashboard + asserts plants
# ---------------------------------------------------------------------------


def test_harness_l1_planted_scenarios_visible(
    harness_deployed: dict[str, Any],
) -> None:
    """Open the deployed L1 dashboard via Playwright and verify each
    planted scenario surfaces on its corresponding sheet (M.4.1.d).

    Per-plant-kind assertions:
    - DriftPlant → Drift sheet shows account_id
    - OverdraftPlant → Overdraft sheet shows account_id
    - LimitBreachPlant → Limit Breach sheet shows account_id
    - StuckPendingPlant → Pending Aging shows account_id
    - StuckUnbundledPlant → Unbundled Aging shows account_id
    - SupersessionPlant → Supersession Audit shows account_id

    Plus Today's Exceptions KPI rollup: the open-violations count
    matches the sum of planted SHOULD-violation scenarios across
    drift / overdraft / breach / pending / unbundled.

    Skipped under default pytest. Per the existing browser-e2e
    convention, requires Playwright + WebKit installed (via
    ``playwright install webkit`` once per environment).
    """
    from quicksight_gen.common.browser.helpers import (
        wait_for_dashboard_loaded,
        webkit_page,
    )

    embed_url = harness_deployed["embed_urls"]["l1-dashboard"]
    manifest = harness_deployed["planted_manifest"]
    page_timeout = int(os.environ.get("QS_E2E_PAGE_TIMEOUT", "30000"))
    visual_timeout = int(os.environ.get("QS_E2E_VISUAL_TIMEOUT", "30000"))

    # Tall viewport so stacked tables don't sit below the fold during
    # the per-sheet walk — same pattern as the existing L1 browser
    # tests.
    with webkit_page(headless=True, viewport=(1600, 4000)) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        assert_l1_plants_visible(
            page, manifest, timeout_ms=visual_timeout,
        )
        assert_todays_exceptions_kpi_matches(
            page, manifest, timeout_ms=visual_timeout,
        )


# ---------------------------------------------------------------------------
# M.4.1.e smoke — Playwright walks the L2 Flow Tracing dashboard
# ---------------------------------------------------------------------------


def test_harness_l2ft_planted_scenarios_visible(
    harness_deployed: dict[str, Any],
) -> None:
    """Open the deployed L2 Flow Tracing dashboard via Playwright and
    verify each L2-side planted scenario surfaces (M.4.1.e).

    Per-plant-kind assertions:
    - rail_firing_plants → Rails sheet shows each rail_name
      (chain-child plants skipped — they reuse the standalone's
      rail_name and would double-count)
    - transfer_template_plants → Transfer Templates sheet shows
      each template_name

    Plus an L2 Exceptions sanity check: at least one of the 6
    declared check_type categories appears on the L2 Exceptions
    sheet (proves the unified-exceptions dataset rendered against
    the per-test prefix without SQL errors).

    Skipped under default pytest (no QS_GEN_E2E).
    """
    from quicksight_gen.common.browser.helpers import (
        wait_for_dashboard_loaded,
        webkit_page,
    )

    embed_url = harness_deployed["embed_urls"]["l2-flow-tracing"]
    manifest = harness_deployed["planted_manifest"]
    page_timeout = int(os.environ.get("QS_E2E_PAGE_TIMEOUT", "30000"))
    visual_timeout = int(os.environ.get("QS_E2E_VISUAL_TIMEOUT", "30000"))

    with webkit_page(headless=True, viewport=(1600, 4000)) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        assert_l2ft_plants_visible(
            page, manifest, timeout_ms=visual_timeout,
        )
        assert_l2_exceptions_check_types_present(
            page, timeout_ms=visual_timeout,
        )
