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


# -- _collect_stale: per-deploy ResourcePrefix scope (v8.4.0) ----------------
#
# v8.4.0 hotfix for the W.3 cleanup-collision class. Three cases this
# test class locks down:
#
# 1. ResourcePrefix-scoped cleanup ONLY sweeps resources whose
#    ResourcePrefix tag matches. (Previously L2Instance-scoped only;
#    a CI run sharing the spec_example L2 with a local deploy would
#    sweep both.)
# 2. Resources with NO ResourcePrefix tag (pre-v8.4.0 deploys) are
#    fail-CLOSED — skipped, NOT swept. Forces operators to opt into
#    the new scope by re-deploying so resources gain the tag.
# 3. ResourcePrefix + L2Instance compose: BOTH must match for a
#    resource to be eligible.


def test_collect_stale_resource_prefix_only_sweeps_matching():
    """v8.4.0 — with resource_prefix='qs-ci-12345-pg', only sweep
    resources whose ResourcePrefix tag matches that exact value.
    Other-prefix resources (concurrent CI run, local deploy) skipped."""
    client = _StubClient(
        summaries_by_kind={
            "dashboard": [
                ("ci-run-12345-dash", "arn:ci-12345"),
                ("ci-run-67890-dash", "arn:ci-67890"),
                ("local-deploy-dash", "arn:local"),
                ("legacy-untagged-dash", "arn:legacy"),
            ],
        },
        tags_by_arn={
            "arn:ci-12345": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("ResourcePrefix", "qs-ci-12345-pg"),
            ],
            "arn:ci-67890": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("ResourcePrefix", "qs-ci-67890-pg"),
            ],
            "arn:local": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("ResourcePrefix", "qs-gen-postgres"),
            ],
            # Pre-v8.4.0 deploy: no ResourcePrefix tag at all.
            "arn:legacy": [_mk_tag("ManagedBy", "quicksight-gen")],
        },
    )
    stale = _collect_stale(
        client, "111", _empty_expected(),
        resource_prefix="qs-ci-12345-pg",
    )
    stale_dash_ids = {rid for rid, _ in stale["dashboard"]}
    # Only the matching prefix is swept; other-prefix + legacy-untagged
    # are skipped (different scope / pre-tag opt-in respectively).
    assert stale_dash_ids == {"ci-run-12345-dash"}


def test_collect_stale_resource_prefix_fails_closed_on_missing_tag():
    """v8.4.0 — resources without a ResourcePrefix tag are NEVER
    swept by a prefix-scoped cleanup. Operators must re-deploy
    (which adds the tag) before prefix-scoped cleanup can touch them.
    Belt-and-suspenders against the W.3 incident: even if a CI run's
    cleanup misfires somehow, pre-tag local deploys are immune."""
    client = _StubClient(
        summaries_by_kind={
            "dashboard": [("untagged", "arn:untagged")],
        },
        tags_by_arn={
            # Only ManagedBy — no ResourcePrefix tag.
            "arn:untagged": [_mk_tag("ManagedBy", "quicksight-gen")],
        },
    )
    stale = _collect_stale(
        client, "111", _empty_expected(),
        resource_prefix="qs-ci-12345-pg",
    )
    stale_dash_ids = {rid for rid, _ in stale["dashboard"]}
    assert stale_dash_ids == set(), (
        "Pre-v8.4.0 untagged resources must NOT be swept by a "
        "prefix-scoped cleanup. The operator's local deploy of "
        "spec_example shouldn't be wiped by a CI run's cleanup just "
        "because the operator hasn't redeployed since v8.4.0."
    )


def test_collect_stale_resource_prefix_and_l2_instance_compose():
    """v8.4.0 — when both resource_prefix AND l2_instance_prefix are
    set, BOTH tags must match for a resource to be eligible. This is
    the production CI shape (per-run prefix + per-L2-instance scope)."""
    client = _StubClient(
        summaries_by_kind={
            "dashboard": [
                ("right-prefix-right-l2", "arn:right-right"),
                ("right-prefix-wrong-l2", "arn:right-wrong"),
                ("wrong-prefix-right-l2", "arn:wrong-right"),
            ],
        },
        tags_by_arn={
            "arn:right-right": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("ResourcePrefix", "qs-ci-12345-pg"),
                _mk_tag("L2Instance", "spec_example"),
            ],
            "arn:right-wrong": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("ResourcePrefix", "qs-ci-12345-pg"),
                _mk_tag("L2Instance", "sasquatch_pr"),
            ],
            "arn:wrong-right": [
                _mk_tag("ManagedBy", "quicksight-gen"),
                _mk_tag("ResourcePrefix", "qs-ci-67890-pg"),
                _mk_tag("L2Instance", "spec_example"),
            ],
        },
    )
    stale = _collect_stale(
        client, "111", _empty_expected(),
        resource_prefix="qs-ci-12345-pg",
        l2_instance_prefix="spec_example",
    )
    stale_dash_ids = {rid for rid, _ in stale["dashboard"]}
    # Only the resource matching BOTH gets swept.
    assert stale_dash_ids == {"right-prefix-right-l2"}
