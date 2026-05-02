"""Cleanup-scope tests for ``common.cleanup`` (M.2d.3).

The cleanup module talks to boto3, so these tests stub the QuickSight
client. The unit-level surface here is the per-instance scoping
introduced by M.2d.3:

- ``_read_managed_tags`` returns the full tag map for ManagedBy
  resources (None for unmanaged).
- ``_collect_stale`` with ``l2_instance_prefix`` set only sweeps
  resources whose ``L2Instance`` tag matches; without it, falls back
  to the legacy "any ManagedBy resource" pass.
"""

from __future__ import annotations

from collections.abc import Iterator

from quicksight_gen.common.cleanup import _collect_stale, _read_managed_tags


# -- A minimal stub that mimics the QuickSight client surface ----------------


class _StubClient:
    """Records ``list_tags_for_resource`` calls + serves canned tag maps.

    Also serves the per-resource paginators each iterator uses. Tests
    construct one with `tags_by_arn` (the source of truth for what the
    client "knows") and `summaries_by_kind` (what the list_* paginators
    return).
    """

    def __init__(
        self,
        tags_by_arn: dict[str, list[dict[str, str]]],
        summaries_by_kind: dict[str, list[tuple[str, str]]],
    ) -> None:
        self._tags = tags_by_arn
        self._summaries = summaries_by_kind

    def list_tags_for_resource(self, *, ResourceArn: str) -> dict:
        return {"Tags": self._tags.get(ResourceArn, [])}

    def get_paginator(self, op: str) -> "_StubPaginator":
        kind_map = {
            "list_dashboards": ("dashboard", "DashboardSummaryList", "DashboardId"),
            "list_analyses": ("analysis", "AnalysisSummaryList", "AnalysisId"),
            "list_data_sets": ("dataset", "DataSetSummaries", "DataSetId"),
            "list_themes": ("theme", "ThemeSummaryList", "ThemeId"),
            "list_data_sources": ("datasource", "DataSources", "DataSourceId"),
        }
        if op not in kind_map:
            raise KeyError(op)
        kind, key, id_field = kind_map[op]
        return _StubPaginator(self._summaries.get(kind, []), key, id_field)


class _StubPaginator:
    def __init__(
        self, items: list[tuple[str, str]], page_key: str, id_field: str,
    ) -> None:
        self._items = items
        self._page_key = page_key
        self._id_field = id_field

    def paginate(self, **_kwargs) -> Iterator[dict]:
        yield {
            self._page_key: [
                {self._id_field: rid, "Arn": arn} for rid, arn in self._items
            ]
        }


# -- Helpers ------------------------------------------------------------------


def _mk_tag(key: str, value: str) -> dict[str, str]:
    return {"Key": key, "Value": value}


def _empty_expected() -> dict[str, set[str]]:
    return {kind: set() for kind in (
        "dashboard", "analysis", "dataset", "theme", "datasource",
    )}


# -- _read_managed_tags ------------------------------------------------------


def test_read_managed_tags_returns_map_for_managed_resource():
    client = _StubClient(
        tags_by_arn={
            "arn:dash:1": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("L2Instance", "sasquatch_ar"),
            ],
        },
        summaries_by_kind={},
    )
    tags = _read_managed_tags(client, "arn:dash:1")
    assert tags == {"ManagedBy": "quicksight-gen", "L2Instance": "sasquatch_ar"}


def test_read_managed_tags_returns_none_for_unmanaged():
    client = _StubClient(
        tags_by_arn={"arn:other:1": [_mk_tag("Owner", "someone-else")]},
        summaries_by_kind={},
    )
    assert _read_managed_tags(client, "arn:other:1") is None


def test_read_managed_tags_returns_none_when_arn_unknown():
    client = _StubClient(tags_by_arn={}, summaries_by_kind={})
    assert _read_managed_tags(client, "arn:missing") is None


# -- _collect_stale: legacy (no l2_instance_prefix) ---------------------------


def test_collect_stale_legacy_sweeps_all_managed_resources():
    """Without l2_instance_prefix, cleanup behaves as it did before
    M.2d.3 — any ManagedBy resource not in `expected` is stale,
    regardless of L2Instance tag."""
    client = _StubClient(
        summaries_by_kind={
            "dashboard": [
                ("legacy-dash", "arn:legacy"),
                ("instance-a-dash", "arn:a"),
                ("instance-b-dash", "arn:b"),
            ],
        },
        tags_by_arn={
            "arn:legacy": [_mk_tag("ManagedBy", "quicksight-gen")],
            "arn:a": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("L2Instance", "sasquatch_ar"),
            ],
            "arn:b": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("L2Instance", "wonkawash"),
            ],
        },
    )
    stale = _collect_stale(client, "111", _empty_expected())
    stale_dash_ids = {rid for rid, _ in stale["dashboard"]}
    assert stale_dash_ids == {"legacy-dash", "instance-a-dash", "instance-b-dash"}


# -- _collect_stale: per-instance scope (l2_instance_prefix set) -------------


def test_collect_stale_scoped_only_sweeps_matching_l2_instance_tag():
    """With l2_instance_prefix='sasquatch_ar', only sweep matching-tag
    resources. Other-instance resources + untagged-legacy resources
    are owned by a different scope and skipped."""
    client = _StubClient(
        summaries_by_kind={
            "dashboard": [
                ("legacy-dash", "arn:legacy"),
                ("instance-a-dash", "arn:a"),
                ("instance-b-dash", "arn:b"),
                ("third-party", "arn:other"),
            ],
        },
        tags_by_arn={
            "arn:legacy": [_mk_tag("ManagedBy", "quicksight-gen")],
            "arn:a": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("L2Instance", "sasquatch_ar"),
            ],
            "arn:b": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("L2Instance", "wonkawash"),
            ],
            "arn:other": [_mk_tag("Owner", "data-eng-team")],
        },
    )
    stale = _collect_stale(
        client, "111", _empty_expected(), l2_instance_prefix="sasquatch_ar",
    )
    stale_dash_ids = {rid for rid, _ in stale["dashboard"]}
    assert stale_dash_ids == {"instance-a-dash"}


def test_collect_stale_scoped_skips_resources_in_expected_set():
    """Even matching-tag resources are skipped if they're in `expected`."""
    client = _StubClient(
        summaries_by_kind={
            "dashboard": [
                ("instance-a-dash", "arn:a"),
                ("instance-a-dash-stale", "arn:a-stale"),
            ],
        },
        tags_by_arn={
            "arn:a": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("L2Instance", "sasquatch_ar"),
            ],
            "arn:a-stale": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("L2Instance", "sasquatch_ar"),
            ],
        },
    )
    expected = _empty_expected()
    expected["dashboard"].add("instance-a-dash")
    stale = _collect_stale(
        client, "111", expected, l2_instance_prefix="sasquatch_ar",
    )
    stale_dash_ids = {rid for rid, _ in stale["dashboard"]}
    assert stale_dash_ids == {"instance-a-dash-stale"}
