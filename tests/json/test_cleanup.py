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


# -- _collect_stale: tagging_enabled=False (v8.6.11) ------------------------


def test_collect_stale_no_tagging_matches_by_id_prefix():
    """With ``tagging_enabled=False`` the tag check is bypassed and
    sweep eligibility is just ID-prefix membership. Resources that
    don't share the prefix stay safe; resources that do — regardless
    of ``ManagedBy`` tag presence — get swept."""
    client = _StubClient(
        summaries_by_kind={
            "dashboard": [
                ("qs-ci-12345-pg-l1-dashboard",        "arn:ours-1"),
                ("qs-ci-12345-pg-investigation",       "arn:ours-2"),
                ("qs-ci-99999-pg-l1-dashboard",        "arn:other-prefix"),
                ("manually-built-dashboard",           "arn:rando"),
            ],
        },
        # No tag map needed — when tagging is disabled the cleanup
        # path doesn't ``list_tags_for_resource`` at all. Pass empty
        # to prove the assertion: matching is purely ID-prefix.
        tags_by_arn={},
    )
    stale = _collect_stale(
        client, "111", _empty_expected(),
        resource_prefix="qs-ci-12345-pg",
        tagging_enabled=False,
    )
    stale_dash_ids = {rid for rid, _ in stale["dashboard"]}
    assert stale_dash_ids == {
        "qs-ci-12345-pg-l1-dashboard",
        "qs-ci-12345-pg-investigation",
    }


def test_collect_stale_no_tagging_skips_id_in_expected():
    """Even with tagging off, IDs in the current ``out/`` set stay safe —
    they're the live deploy, not stale."""
    client = _StubClient(
        summaries_by_kind={
            "dashboard": [
                ("qs-ci-12345-pg-live",    "arn:live"),
                ("qs-ci-12345-pg-stale",   "arn:stale"),
            ],
        },
        tags_by_arn={},
    )
    expected = _empty_expected()
    expected["dashboard"].add("qs-ci-12345-pg-live")
    stale = _collect_stale(
        client, "111", expected,
        resource_prefix="qs-ci-12345-pg",
        tagging_enabled=False,
    )
    stale_dash_ids = {rid for rid, _ in stale["dashboard"]}
    assert stale_dash_ids == {"qs-ci-12345-pg-stale"}


def test_collect_stale_no_tagging_requires_resource_prefix():
    """Without either tags OR an ID-prefix scope there's no way to
    distinguish our resources from anyone else's. Refuse to run rather
    than risk sweeping unrelated dashboards."""
    import pytest as _pytest
    client = _StubClient(summaries_by_kind={}, tags_by_arn={})
    with _pytest.raises(ValueError, match="requires resource_prefix"):
        _collect_stale(
            client, "111", _empty_expected(),
            tagging_enabled=False,
        )


# -- _delete_stale -----------------------------------------------------------
#
# v8.6.12 — coverage uplift. Asserts the per-kind delete loop dispatches
# to the right boto3 method per resource type and aggregates failures.


class _DeleteStubClient:
    """Captures every ``delete_*`` invocation + can be told to raise on
    a designated ID for failure-counting tests."""

    def __init__(self, fail_on_id: str | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail_on_id = fail_on_id

    def _maybe_fail(self, op: str, rid: str) -> None:
        self.calls.append((op, rid))
        if rid == self._fail_on_id:
            from botocore.exceptions import ClientError
            raise ClientError(
                {"Error": {"Code": "Boom", "Message": "fail"}}, op,
            )

    def delete_dashboard(self, *, AwsAccountId: str, DashboardId: str) -> None:
        self._maybe_fail("delete_dashboard", DashboardId)

    def delete_analysis(
        self, *, AwsAccountId: str, AnalysisId: str,
        ForceDeleteWithoutRecovery: bool = False,
    ) -> None:
        # Asserts the recovery-skip flag is set; without it QS holds
        # the analysis in soft-deleted state for 30 days and the next
        # apply collides on the same ID.
        assert ForceDeleteWithoutRecovery is True
        self._maybe_fail("delete_analysis", AnalysisId)

    def delete_data_set(self, *, AwsAccountId: str, DataSetId: str) -> None:
        self._maybe_fail("delete_data_set", DataSetId)

    def delete_theme(self, *, AwsAccountId: str, ThemeId: str) -> None:
        self._maybe_fail("delete_theme", ThemeId)

    def delete_data_source(
        self, *, AwsAccountId: str, DataSourceId: str,
    ) -> None:
        self._maybe_fail("delete_data_source", DataSourceId)


def test_delete_stale_dispatches_per_kind():
    from quicksight_gen.common.cleanup import _delete_stale
    client = _DeleteStubClient()
    failures = _delete_stale(client, "111", {
        "dashboard": [("d-1", "arn:d:1")],
        "analysis": [("a-1", "arn:a:1")],
        "dataset": [("ds-1", "arn:ds:1")],
        "theme": [("t-1", "arn:t:1")],
        "datasource": [("dsrc-1", "arn:dsrc:1")],
    })
    assert failures == 0
    # Order matters — dashboard before analysis (analysis depends on
    # dashboard via embedded references), datasets before themes,
    # datasource last (datasets reference it).
    ops = [op for op, _ in client.calls]
    assert ops == [
        "delete_dashboard", "delete_analysis", "delete_data_set",
        "delete_theme", "delete_data_source",
    ]


def test_delete_stale_counts_failures_and_continues():
    from quicksight_gen.common.cleanup import _delete_stale
    client = _DeleteStubClient(fail_on_id="ds-failing")
    failures = _delete_stale(client, "111", {
        "dashboard": [("d-1", "arn:d:1")],
        "analysis": [],
        "dataset": [
            ("ds-failing", "arn:ds:fail"),
            ("ds-after", "arn:ds:after"),
        ],
        "theme": [],
        "datasource": [],
    })
    # The failing delete is counted; the loop continues to the
    # next dataset rather than aborting on the first error.
    assert failures == 1
    rids_attempted = [rid for _, rid in client.calls]
    assert rids_attempted == ["d-1", "ds-failing", "ds-after"]


# -- run_cleanup --------------------------------------------------------------


def _patched_boto3_client(monkeypatch, stub) -> None:
    """Make ``boto3.client('quicksight', ...)`` return our stub instead
    of trying to talk to AWS."""
    import boto3
    monkeypatch.setattr(boto3, "client", lambda *_a, **_k: stub)


def _make_cfg(tagging_enabled: bool = True):
    from quicksight_gen.common.config import Config
    return Config(
        aws_account_id="111",
        aws_region="us-east-1",
        datasource_arn="arn:aws:quicksight:us-east-1:111:datasource/x",
        resource_prefix="qs-test",
        tagging_enabled=tagging_enabled,
    )


def test_run_cleanup_short_circuits_when_no_stale(tmp_path, monkeypatch):
    """Empty inventory + empty expected → nothing to do, exit 0
    without dispatching any delete calls."""
    from quicksight_gen.common.cleanup import run_cleanup
    stub = _DeleteStubClient()
    # Patch the listing surface too — give it the tagged stub shape.
    listing = _StubClient(summaries_by_kind={}, tags_by_arn={})
    # Compose: when run_cleanup grabs boto3.client it gets a thing with
    # both surfaces. Easier: monkey-patch the cleanup module's helpers.
    import quicksight_gen.common.cleanup as cu
    monkeypatch.setattr(
        cu, "_collect_stale",
        lambda *_a, **_k: {kind: [] for kind in (
            "dashboard", "analysis", "dataset", "theme", "datasource",
        )},
    )
    _patched_boto3_client(monkeypatch, stub)

    rc = run_cleanup(_make_cfg(), tmp_path)
    assert rc == 0
    assert stub.calls == []


def test_run_cleanup_dry_run_skips_delete(tmp_path, monkeypatch):
    """``dry_run=True`` prints the plan but never invokes boto3 delete."""
    from quicksight_gen.common.cleanup import run_cleanup
    stub = _DeleteStubClient()
    import quicksight_gen.common.cleanup as cu
    monkeypatch.setattr(
        cu, "_collect_stale",
        lambda *_a, **_k: {
            "dashboard": [("d-1", "arn:1")],
            "analysis": [], "dataset": [], "theme": [], "datasource": [],
        },
    )
    _patched_boto3_client(monkeypatch, stub)

    rc = run_cleanup(_make_cfg(), tmp_path, dry_run=True)
    assert rc == 0
    assert stub.calls == []


def test_run_cleanup_skip_confirm_executes_delete(tmp_path, monkeypatch):
    """``skip_confirm=True`` bypasses the click prompt and runs the
    delete loop directly. Mirrors the path the standalone CI cleanup
    job hits when there's no terminal."""
    from quicksight_gen.common.cleanup import run_cleanup
    stub = _DeleteStubClient()
    import quicksight_gen.common.cleanup as cu
    monkeypatch.setattr(
        cu, "_collect_stale",
        lambda *_a, **_k: {
            "dashboard": [("d-1", "arn:1")],
            "analysis": [], "dataset": [], "theme": [], "datasource": [],
        },
    )
    _patched_boto3_client(monkeypatch, stub)

    rc = run_cleanup(_make_cfg(), tmp_path, skip_confirm=True)
    assert rc == 0
    assert ("delete_dashboard", "d-1") in stub.calls


def test_run_cleanup_confirm_no_aborts(tmp_path, monkeypatch):
    """Operator typed ``n`` at the prompt — no delete fires."""
    from quicksight_gen.common.cleanup import run_cleanup
    stub = _DeleteStubClient()
    import quicksight_gen.common.cleanup as cu
    monkeypatch.setattr(
        cu, "_collect_stale",
        lambda *_a, **_k: {
            "dashboard": [("d-1", "arn:1")],
            "analysis": [], "dataset": [], "theme": [], "datasource": [],
        },
    )
    _patched_boto3_client(monkeypatch, stub)
    # Simulate the user answering "no" to the prompt.
    monkeypatch.setattr(
        "click.confirm", lambda *_a, **_k: False,
    )

    rc = run_cleanup(_make_cfg(), tmp_path)
    assert rc == 0
    assert stub.calls == []


def test_run_cleanup_no_tagging_announces_id_prefix_mode(
    tmp_path, monkeypatch, capsys,
):
    """The startup banner must call out the weakened isolation when
    tagging is disabled — operators relying on the warning to spot
    misconfiguration depend on the message landing in stdout."""
    from quicksight_gen.common.cleanup import run_cleanup
    stub = _DeleteStubClient()
    import quicksight_gen.common.cleanup as cu
    monkeypatch.setattr(
        cu, "_collect_stale",
        lambda *_a, **_k: {kind: [] for kind in (
            "dashboard", "analysis", "dataset", "theme", "datasource",
        )},
    )
    _patched_boto3_client(monkeypatch, stub)

    run_cleanup(_make_cfg(tagging_enabled=False), tmp_path)
    out = capsys.readouterr().out
    assert "tagging disabled" in out
    assert "ID prefix only" in out


def test_run_cleanup_purge_all_ignores_out_dir(tmp_path, monkeypatch):
    """v8.6.13 — purge mode must NOT consult ``out_dir``. Even when
    the directory holds JSON files for the live deploy, every
    matching resource gets queued for sweep."""
    from quicksight_gen.common.cleanup import run_cleanup
    stub = _DeleteStubClient()
    expected_seen: list[dict] = []

    import quicksight_gen.common.cleanup as cu

    def _capture(_client, _account, expected, **_kwargs):
        expected_seen.append(expected)
        # Pretend we found nothing so the test exits cleanly.
        return {kind: [] for kind in (
            "dashboard", "analysis", "dataset", "theme", "datasource",
        )}

    # Drop a fake live-deploy file into out_dir — without purge mode,
    # this would carve the dashboard out of the sweep set.
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "live-dashboard.json").write_text(
        '{"DashboardId": "live-deploy-x"}'
    )
    monkeypatch.setattr(cu, "_collect_stale", _capture)
    _patched_boto3_client(monkeypatch, stub)

    run_cleanup(_make_cfg(), out_dir, purge_all=True)
    # Empty expected = nothing carved out, even though out_dir has a
    # live-deploy entry.
    assert expected_seen[0]["dashboard"] == set()


def test_run_cleanup_purge_all_announces_purge_mode(
    tmp_path, monkeypatch, capsys,
):
    """The startup banner must call out PURGE-ALL mode so the operator
    can spot it in shell history and CI logs — distinguishes from
    everyday ``clean`` output."""
    from quicksight_gen.common.cleanup import run_cleanup
    stub = _DeleteStubClient()
    import quicksight_gen.common.cleanup as cu
    monkeypatch.setattr(
        cu, "_collect_stale",
        lambda *_a, **_k: {kind: [] for kind in (
            "dashboard", "analysis", "dataset", "theme", "datasource",
        )},
    )
    _patched_boto3_client(monkeypatch, stub)

    run_cleanup(_make_cfg(), tmp_path, purge_all=True)
    out = capsys.readouterr().out
    assert "PURGE-ALL" in out
