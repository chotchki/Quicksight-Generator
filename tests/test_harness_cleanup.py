"""Unit tests for ``tests/e2e/_harness_cleanup.py`` (M.4.1.a).

The harness's per-test cleanup is the most safety-critical piece of
the M.4.1 substep tree — a buggy sweep either (a) leaves stale QS
resources behind so the next test's deploy collides, or (b) deletes
resources belonging to the production deploy. So this file exercises
the sweep logic against mock boto3 clients without spinning up the
actual harness.

Two surfaces under test:

1. ``sweep_qs_resources_by_tag`` — given a fake QS client that returns
   pre-canned dashboard / analysis / dataset / theme listings + tag
   reads, assert the sweep picks the right resources and calls the
   right ``delete_*`` method per kind.

2. ``drop_prefixed_schema`` — given a fake psycopg2 connection that
   records issued SQL, assert the matview/view/table discovery queries
   fire in the right order and DROP statements use ``CASCADE``.

Lives at the project test root (not under ``tests/e2e/``) so it runs
in the default ``pytest`` invocation — these are unit tests on the
sweep logic, not e2e tests against AWS.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


# Add tests/e2e to import path so the test can pull in the helper
# module directly without adding it to the package install.
sys.path.insert(0, str(Path(__file__).parent / "e2e"))
from _harness_cleanup import (  # noqa: E402
    drop_prefixed_schema,
    sweep_qs_resources_by_tag,
)


# ---------------------------------------------------------------------------
# Mock QS client — minimal shape the sweep helper consumes
# ---------------------------------------------------------------------------


class _FakeQsClient:
    """Records delete calls + serves canned list / tag-read results."""

    def __init__(
        self,
        *,
        dashboards: list[tuple[str, str]],
        analyses: list[tuple[str, str]],
        datasets: list[tuple[str, str]],
        themes: list[tuple[str, str]],
        tags_by_arn: dict[str, list[dict[str, str]]],
    ) -> None:
        self._dashboards = dashboards
        self._analyses = analyses
        self._datasets = datasets
        self._themes = themes
        self._tags_by_arn = tags_by_arn
        self.deletions: list[tuple[str, str]] = []  # (kind, id)

    # The cleanup module uses paginators with `.paginate(AwsAccountId=...)`
    # — emulate just enough to walk a single page.
    def get_paginator(self, op_name: str):
        kind_to_pages = {
            "list_dashboards": (
                "DashboardSummaryList",
                [
                    {"DashboardId": rid, "Arn": arn}
                    for rid, arn in self._dashboards
                ],
            ),
            "list_analyses": (
                "AnalysisSummaryList",
                [
                    {"AnalysisId": rid, "Arn": arn, "Status": "CREATION_SUCCESSFUL"}
                    for rid, arn in self._analyses
                ],
            ),
            "list_data_sets": (
                "DataSetSummaries",
                [
                    {"DataSetId": rid, "Arn": arn}
                    for rid, arn in self._datasets
                ],
            ),
            "list_themes": (
                "ThemeSummaryList",
                [
                    {"ThemeId": rid, "Arn": arn}
                    for rid, arn in self._themes
                ],
            ),
        }
        key, items = kind_to_pages[op_name]
        return _FakePaginator(key, items)

    def list_tags_for_resource(self, *, ResourceArn: str):
        return {"Tags": self._tags_by_arn.get(ResourceArn, [])}

    def delete_dashboard(self, *, AwsAccountId: str, DashboardId: str):
        self.deletions.append(("dashboard", DashboardId))

    def delete_analysis(
        self,
        *,
        AwsAccountId: str,
        AnalysisId: str,
        ForceDeleteWithoutRecovery: bool,
    ):
        assert ForceDeleteWithoutRecovery is True
        self.deletions.append(("analysis", AnalysisId))

    def delete_data_set(self, *, AwsAccountId: str, DataSetId: str):
        self.deletions.append(("dataset", DataSetId))

    def delete_theme(self, *, AwsAccountId: str, ThemeId: str):
        self.deletions.append(("theme", ThemeId))


class _FakePaginator:
    def __init__(self, key: str, items: list[dict[str, Any]]) -> None:
        self._key = key
        self._items = items

    def paginate(self, **_kwargs: Any):
        yield {self._key: self._items}


# ---------------------------------------------------------------------------
# sweep_qs_resources_by_tag tests
# ---------------------------------------------------------------------------


def _arn(account: str, kind: str, rid: str) -> str:
    return f"arn:aws:quicksight:us-west-2:{account}:{kind}/{rid}"


def test_sweep_deletes_only_tag_matching_resources() -> None:
    """Resources WITHOUT the harness tag must NOT be deleted."""
    account = "111122223333"
    matching_arn = _arn(account, "dashboard", "qs-gen-e2e-spec-dash")
    other_arn = _arn(account, "dashboard", "qs-gen-prod-dash")
    client = _FakeQsClient(
        dashboards=[
            ("qs-gen-e2e-spec-dash", matching_arn),
            ("qs-gen-prod-dash", other_arn),
        ],
        analyses=[],
        datasets=[],
        themes=[],
        tags_by_arn={
            matching_arn: [
                {"Key": "TestUid", "Value": "abc123"},
                {"Key": "ManagedBy", "Value": "quicksight-gen"},
            ],
            other_arn: [{"Key": "ManagedBy", "Value": "quicksight-gen"}],
        },
    )

    counts = sweep_qs_resources_by_tag(
        client, account, tag_key="TestUid", tag_value="abc123",
    )

    assert client.deletions == [("dashboard", "qs-gen-e2e-spec-dash")]
    assert counts == {
        "dashboard": 1, "analysis": 0, "dataset": 0, "theme": 0,
    }


def test_sweep_deletes_in_dependency_order() -> None:
    """Dashboards delete BEFORE analyses BEFORE datasets BEFORE themes —
    QS rejects e.g. dataset deletion while a dashboard still references it.
    """
    account = "111122223333"
    tags = [{"Key": "TestUid", "Value": "uid42"}]
    arns = {
        kind: _arn(account, kind, f"qs-gen-e2e-{kind}")
        for kind in ("dashboard", "analysis", "dataset", "theme")
    }
    client = _FakeQsClient(
        dashboards=[("qs-gen-e2e-dashboard", arns["dashboard"])],
        analyses=[("qs-gen-e2e-analysis", arns["analysis"])],
        datasets=[("qs-gen-e2e-dataset", arns["dataset"])],
        themes=[("qs-gen-e2e-theme", arns["theme"])],
        tags_by_arn={arn: tags for arn in arns.values()},
    )

    sweep_qs_resources_by_tag(
        client, account, tag_key="TestUid", tag_value="uid42",
    )

    assert client.deletions == [
        ("dashboard", "qs-gen-e2e-dashboard"),
        ("analysis", "qs-gen-e2e-analysis"),
        ("dataset", "qs-gen-e2e-dataset"),
        ("theme", "qs-gen-e2e-theme"),
    ]


def test_sweep_skips_deleted_analyses() -> None:
    """An analysis already in DELETED status (soft-deleted, awaiting
    permanent reaper) must NOT be re-deleted — the second delete returns
    a 4xx that confuses the per-test triage manifest. The iter helper
    handles this by filtering on status."""
    account = "111122223333"
    arn = _arn(account, "analysis", "qs-gen-e2e-already-deleted")

    class _SoftDeletedAnalysisClient(_FakeQsClient):
        def get_paginator(self, op_name: str):
            if op_name == "list_analyses":
                return _FakePaginator(
                    "AnalysisSummaryList",
                    [{
                        "AnalysisId": "qs-gen-e2e-already-deleted",
                        "Arn": arn,
                        "Status": "DELETED",
                    }],
                )
            return super().get_paginator(op_name)

    client = _SoftDeletedAnalysisClient(
        dashboards=[],
        analyses=[],
        datasets=[],
        themes=[],
        tags_by_arn={arn: [{"Key": "TestUid", "Value": "uid42"}]},
    )

    counts = sweep_qs_resources_by_tag(
        client, account, tag_key="TestUid", tag_value="uid42",
    )

    assert client.deletions == []
    assert counts["analysis"] == 0


def test_sweep_continues_past_individual_delete_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One failing delete must not abort the whole sweep — the next
    test needs the rest of the resources gone or its deploy collides."""
    account = "111122223333"
    tags = [{"Key": "TestUid", "Value": "uid42"}]
    a_arn = _arn(account, "dataset", "qs-gen-e2e-bad")
    b_arn = _arn(account, "dataset", "qs-gen-e2e-good")

    class _OneBadDeleteClient(_FakeQsClient):
        def delete_data_set(self, *, AwsAccountId: str, DataSetId: str):
            if DataSetId == "qs-gen-e2e-bad":
                raise RuntimeError("simulated 5xx")
            super().delete_data_set(
                AwsAccountId=AwsAccountId, DataSetId=DataSetId,
            )

    client = _OneBadDeleteClient(
        dashboards=[],
        analyses=[],
        datasets=[
            ("qs-gen-e2e-bad", a_arn),
            ("qs-gen-e2e-good", b_arn),
        ],
        themes=[],
        tags_by_arn={a_arn: tags, b_arn: tags},
    )

    counts = sweep_qs_resources_by_tag(
        client, account, tag_key="TestUid", tag_value="uid42",
    )

    # Both visited; only the second succeeded.
    assert ("dataset", "qs-gen-e2e-good") in client.deletions
    assert ("dataset", "qs-gen-e2e-bad") not in client.deletions
    assert counts["dataset"] == 1
    # Failure was logged to stderr for the per-test triage manifest.
    captured = capsys.readouterr()
    assert "qs-gen-e2e-bad" in captured.err
    assert "simulated 5xx" in captured.err


def test_sweep_does_not_touch_datasources() -> None:
    """Datasources are explicitly excluded from the sweep — they're
    shared across tests, owned by the production deploy.
    """
    account = "111122223333"

    class _DataSourceWatchingClient(_FakeQsClient):
        def __init__(self, **kw: Any) -> None:
            super().__init__(**kw)
            self.list_datasource_called = False

        def get_paginator(self, op_name: str):
            if op_name == "list_data_sources":
                self.list_datasource_called = True
            return super().get_paginator(op_name)

    client = _DataSourceWatchingClient(
        dashboards=[], analyses=[], datasets=[], themes=[], tags_by_arn={},
    )

    sweep_qs_resources_by_tag(
        client, account, tag_key="TestUid", tag_value="uid42",
    )

    assert client.list_datasource_called is False


# ---------------------------------------------------------------------------
# drop_prefixed_schema tests
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, query_results: dict[str, list[tuple[str]]]) -> None:
        self._query_results = query_results
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self._last_select_table: str | None = None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed.append((sql, params))
        # Discover queries: figure out which catalog table is being read
        # so the next fetchall returns the matching results.
        if "FROM pg_matviews" in sql:
            self._last_select_table = "pg_matviews"
        elif "FROM pg_views" in sql:
            self._last_select_table = "pg_views"
        elif "FROM pg_tables" in sql:
            self._last_select_table = "pg_tables"

    def fetchall(self) -> list[tuple[str]]:
        if self._last_select_table is None:
            return []
        return self._query_results.get(self._last_select_table, [])

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _FakeConn:
    def __init__(self, query_results: dict[str, list[tuple[str]]]) -> None:
        self._cursor = _FakeCursor(query_results)
        self.commits = 0

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1


def test_drop_prefixed_schema_drops_in_dependency_order() -> None:
    """Matviews drop BEFORE views BEFORE tables (CASCADE on each)."""
    conn = _FakeConn({
        "pg_matviews": [
            ("e2e_spec_uid_drift",),
            ("e2e_spec_uid_current_transactions",),
        ],
        "pg_views": [],
        "pg_tables": [
            ("e2e_spec_uid_transactions",),
            ("e2e_spec_uid_daily_balances",),
        ],
    })

    drop_prefixed_schema(conn, "e2e_spec_uid")

    # Pull just the DROP statements in execution order.
    drops = [sql for sql, _ in conn._cursor.executed if sql.startswith("DROP")]
    assert drops == [
        "DROP MATERIALIZED VIEW IF EXISTS e2e_spec_uid_drift CASCADE",
        "DROP MATERIALIZED VIEW IF EXISTS e2e_spec_uid_current_transactions CASCADE",
        "DROP TABLE IF EXISTS e2e_spec_uid_transactions CASCADE",
        "DROP TABLE IF EXISTS e2e_spec_uid_daily_balances CASCADE",
    ]
    assert conn.commits == 1


def test_drop_prefixed_schema_uses_pattern_matching_for_discovery() -> None:
    """Discovery uses LIKE on `<prefix>_%` so future schema additions
    get cleaned up automatically without hand-editing the helper."""
    conn = _FakeConn({"pg_matviews": [], "pg_views": [], "pg_tables": []})

    drop_prefixed_schema(conn, "e2e_test_xyz")

    selects = [
        (sql, params) for sql, params in conn._cursor.executed
        if sql.startswith("SELECT")
    ]
    # 3 discovery queries, all using the prefix pattern.
    assert len(selects) == 3
    for _, params in selects:
        assert params == ("e2e_test_xyz_%",)


def test_drop_prefixed_schema_no_op_on_empty_prefix() -> None:
    """Calling with a prefix that has no objects is a no-op (commits
    happen but no DROPs fire)."""
    conn = _FakeConn({"pg_matviews": [], "pg_views": [], "pg_tables": []})

    drop_prefixed_schema(conn, "e2e_nothing_here")

    drops = [sql for sql, _ in conn._cursor.executed if sql.startswith("DROP")]
    assert drops == []
    assert conn.commits == 1
