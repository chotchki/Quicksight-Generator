"""End-to-end harness cleanup helpers (M.4.1.a).

Per-test cleanup for the M.4.1 end-to-end harness. Two surfaces:

1. ``sweep_qs_resources_by_tag(client, account_id, tag_key, tag_value)``
   — list every QuickSight resource (dashboard / analysis / dataset /
   theme), filter by an `(extra_tag_key, extra_tag_value)` pair the
   harness injects via ``cfg.extra_tags``, and delete in dependency
   order. Returns a count of deletions for the per-test triage manifest.

2. ``drop_prefixed_schema(conn, prefix)`` — DROP every prefixed table /
   view / matview the harness's ``emit_schema(instance)`` created. Uses
   ``CASCADE`` because the L1 invariant matviews depend on the
   ``current_*`` views which depend on the base tables.

Why this is its own module instead of inline-in-the-harness: both
helpers are unit-testable against a mock boto3 client / a sandbox
DB connection without spinning up the full harness fixture chain.
That keeps the per-test-uid sweep logic in a place where a regression
on it doesn't require ``QS_GEN_E2E=1`` + AWS creds + an Aurora cluster
to detect.

Why we don't reuse ``common/cleanup.py``: the production cleanup
module diffs current resources against an ``out/`` directory of
expected JSON ("delete anything not in expected"), which is the right
shape for the production deploy workflow. The harness has no
persistent ``out/`` to diff against — it just deletes its own
resources by tag. Different shape, different module.
"""

from __future__ import annotations

from typing import Any

from quicksight_gen.common.sql import Dialect


# QS resource types swept in dependency order: dashboards reference
# analyses, analyses reference datasets, datasets reference datasources +
# themes. Datasource swept LAST (after datasets) since datasets reference
# it; theme is independent. M.4.1 option 2 — the harness now creates its
# OWN per-test datasource (vs the earlier shared-production-datasource
# pattern), so the sweep needs to delete it.
_QS_DELETION_ORDER = (
    "dashboard", "analysis", "dataset", "datasource", "theme",
)


def sweep_qs_resources_by_tag(
    client: Any,
    account_id: str,
    *,
    tag_key: str,
    tag_value: str,
) -> dict[str, int]:
    """Delete every QS resource carrying ``tag_key == tag_value``.

    Walks dashboards / analyses / datasets / datasources / themes; for
    each, calls ``list_tags_for_resource`` on its ARN; if the tag
    matches, deletes. Datasources are now part of the sweep (M.4.1
    option 2 — harness owns its own per-test datasource).

    Returns a dict ``{resource_type: deletion_count}`` for the
    per-test failure triage manifest (M.4.1.f).

    Robust against partial failures: a delete that errors out is
    logged to stderr but does not abort the sweep — the next test
    needs the rest of the sweep to land or its deploy collides on
    leftover IDs.
    """
    matched = _collect_resources_matching_tag(
        client, account_id, tag_key=tag_key, tag_value=tag_value,
    )
    counts: dict[str, int] = {}
    for kind in _QS_DELETION_ORDER:
        items = matched.get(kind, [])
        deleted = 0
        for resource_id, _arn in items:
            try:
                _delete_one(client, account_id, kind, resource_id)
                deleted += 1
            except Exception as exc:  # noqa: BLE001 — best-effort sweep
                # Per-test cleanup must continue past one bad delete so
                # the rest of the sweep still lands. Bubble the message
                # to stderr for the failure manifest.
                import sys
                print(
                    f"[harness-cleanup] {kind} {resource_id!r} delete failed: "
                    f"{exc}",
                    file=sys.stderr,
                )
        counts[kind] = deleted
    return counts


def _collect_resources_matching_tag(
    client: Any,
    account_id: str,
    *,
    tag_key: str,
    tag_value: str,
) -> dict[str, list[tuple[str, str]]]:
    """Return ``{kind: [(id, arn), ...]}`` for resources carrying the tag."""
    matched: dict[str, list[tuple[str, str]]] = {
        kind: [] for kind in _QS_DELETION_ORDER
    }
    iterators = {
        "dashboard": _iter_dashboards,
        "analysis": _iter_analyses,
        "dataset": _iter_datasets,
        "datasource": _iter_datasources,
        "theme": _iter_themes,
    }
    for kind, it in iterators.items():
        for resource_id, arn in it(client, account_id):
            if not _tag_matches(client, arn, tag_key, tag_value):
                continue
            matched[kind].append((resource_id, arn))
    return matched


def _tag_matches(
    client: Any, arn: str, tag_key: str, tag_value: str,
) -> bool:
    """True if the resource's tags include the (key, value) pair."""
    try:
        resp = client.list_tags_for_resource(ResourceArn=arn)
    except Exception:  # noqa: BLE001 — read failure means "not ours"
        return False
    for tag in resp.get("Tags", []):
        if tag.get("Key") == tag_key and tag.get("Value") == tag_value:
            return True
    return False


def _delete_one(client: Any, account_id: str, kind: str, rid: str) -> None:
    if kind == "dashboard":
        client.delete_dashboard(AwsAccountId=account_id, DashboardId=rid)
    elif kind == "analysis":
        # Force-delete bypasses the 30-day recovery window so the next
        # test's deploy doesn't collide on the resurrectable ID.
        client.delete_analysis(
            AwsAccountId=account_id,
            AnalysisId=rid,
            ForceDeleteWithoutRecovery=True,
        )
    elif kind == "dataset":
        client.delete_data_set(AwsAccountId=account_id, DataSetId=rid)
    elif kind == "datasource":
        client.delete_data_source(AwsAccountId=account_id, DataSourceId=rid)
    elif kind == "theme":
        client.delete_theme(AwsAccountId=account_id, ThemeId=rid)
    else:
        raise ValueError(f"unknown QS resource kind: {kind!r}")


def _iter_dashboards(client: Any, account_id: str):
    paginator = client.get_paginator("list_dashboards")
    for page in paginator.paginate(AwsAccountId=account_id):
        for item in page.get("DashboardSummaryList", []):
            yield item["DashboardId"], item["Arn"]


def _iter_analyses(client: Any, account_id: str):
    paginator = client.get_paginator("list_analyses")
    for page in paginator.paginate(AwsAccountId=account_id):
        for item in page.get("AnalysisSummaryList", []):
            # Skip soft-deleted analyses (DELETED status) — they're
            # already on the way out and a second delete returns a
            # 4xx that confuses the per-test triage manifest.
            if item.get("Status") == "DELETED":
                continue
            yield item["AnalysisId"], item["Arn"]


def _iter_datasets(client: Any, account_id: str):
    paginator = client.get_paginator("list_data_sets")
    for page in paginator.paginate(AwsAccountId=account_id):
        for item in page.get("DataSetSummaries", []):
            yield item["DataSetId"], item["Arn"]


def _iter_datasources(client: Any, account_id: str):
    paginator = client.get_paginator("list_data_sources")
    for page in paginator.paginate(AwsAccountId=account_id):
        for item in page.get("DataSources", []):
            yield item["DataSourceId"], item["Arn"]


def _iter_themes(client: Any, account_id: str):
    paginator = client.get_paginator("list_themes")
    for page in paginator.paginate(AwsAccountId=account_id):
        for item in page.get("ThemeSummaryList", []):
            yield item["ThemeId"], item["Arn"]


# ---------------------------------------------------------------------------
# DB-side cleanup
# ---------------------------------------------------------------------------


def drop_prefixed_schema(
    conn: Any, prefix: str, *, dialect: Dialect = Dialect.POSTGRES,
) -> None:
    """DROP every matview / view / table whose name starts with ``prefix_``.

    Discovers objects via the dialect's catalog views (Postgres:
    ``pg_matviews`` / ``pg_views`` / ``pg_tables``; Oracle:
    ``USER_MVIEWS`` / ``USER_VIEWS`` / ``USER_TABLES``) rather than a
    hand-maintained list — new matviews added to ``schema.py`` get
    cleaned up automatically without a parallel edit here.

    Order matters: matviews first (L1 invariant matviews depend on the
    ``current_*`` matviews), then plain views, then base tables.
    ``CASCADE`` (Postgres) / ``CASCADE CONSTRAINTS PURGE`` (Oracle) on
    each DROP covers any dependent leftover.

    P.9d: dialect-aware so the e2e harness teardown works against
    Oracle as well as Postgres. Postgres uses ``%s`` placeholders +
    ``DROP ... IF EXISTS`` (built-in idempotency); Oracle uses ``:1``
    bind syntax + a PL/SQL ``BEGIN EXCEPTION`` wrapper to swallow
    ORA-942 / ORA-12003 (the missing-IF-EXISTS gap noted in PLAN P.9d).
    """
    pattern = f"{prefix}_%"

    if dialect is Dialect.POSTGRES:
        _drop_prefixed_postgres(conn, pattern)
    else:
        _drop_prefixed_oracle(conn, pattern)


def _drop_prefixed_postgres(conn: Any, pattern: str) -> None:
    with conn.cursor() as cur:
        # 1. Materialized views (most of the surface).
        cur.execute(
            "SELECT matviewname FROM pg_matviews "
            "WHERE schemaname = current_schema() AND matviewname LIKE %s",
            (pattern,),
        )
        matviews = [row[0] for row in cur.fetchall()]
        for name in matviews:
            cur.execute(f"DROP MATERIALIZED VIEW IF EXISTS {name} CASCADE")

        # 2. Plain views (currently none under emit_schema, but a defensive
        # sweep here means future view additions get picked up).
        cur.execute(
            "SELECT viewname FROM pg_views "
            "WHERE schemaname = current_schema() AND viewname LIKE %s",
            (pattern,),
        )
        views = [row[0] for row in cur.fetchall()]
        for name in views:
            cur.execute(f"DROP VIEW IF EXISTS {name} CASCADE")

        # 3. Base tables last (matviews referenced them).
        cur.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = current_schema() AND tablename LIKE %s",
            (pattern,),
        )
        tables = [row[0] for row in cur.fetchall()]
        for name in tables:
            cur.execute(f"DROP TABLE IF EXISTS {name} CASCADE")
    conn.commit()


def _drop_prefixed_oracle(conn: Any, pattern: str) -> None:
    """Oracle equivalent of ``_drop_prefixed_postgres``.

    Oracle has no ``DROP ... IF EXISTS``; per-object DROPs that race
    with another teardown can ORA-942 (table) or ORA-12003 (matview).
    Wrap each DROP in a PL/SQL block that swallows those codes so
    parallel-test teardowns don't fight each other.
    """
    with conn.cursor() as cur:
        # 1. Materialized views.
        cur.execute(
            "SELECT mview_name FROM USER_MVIEWS WHERE mview_name LIKE :1",
            [pattern.upper()],
        )
        matviews = [row[0] for row in cur.fetchall()]
        for name in matviews:
            cur.execute(_oracle_safe_drop(
                f"DROP MATERIALIZED VIEW {name}", ignore_codes=(-12003, -942),
            ))

        # 2. Plain views.
        cur.execute(
            "SELECT view_name FROM USER_VIEWS WHERE view_name LIKE :1",
            [pattern.upper()],
        )
        views = [row[0] for row in cur.fetchall()]
        for name in views:
            cur.execute(_oracle_safe_drop(
                f"DROP VIEW {name}", ignore_codes=(-942,),
            ))

        # 3. Base tables last.
        cur.execute(
            "SELECT table_name FROM USER_TABLES WHERE table_name LIKE :1",
            [pattern.upper()],
        )
        tables = [row[0] for row in cur.fetchall()]
        for name in tables:
            cur.execute(_oracle_safe_drop(
                f"DROP TABLE {name} CASCADE CONSTRAINTS PURGE",
                ignore_codes=(-942,),
            ))
    conn.commit()


def _oracle_safe_drop(
    drop_stmt: str, *, ignore_codes: tuple[int, ...],
) -> str:
    """Wrap an Oracle DROP in a PL/SQL block that swallows the listed
    "does not exist" SQLCODE values. Mirrors the helper in
    ``common/sql/dialect.py``; lifted-by-copy here to keep the harness
    cleanup independent of the schema-emit module."""
    not_in = " AND ".join(f"SQLCODE != {c}" for c in ignore_codes)
    return (
        f"BEGIN EXECUTE IMMEDIATE '{drop_stmt}'; "
        f"EXCEPTION WHEN OTHERS THEN IF {not_in} THEN RAISE; END IF; END;"
    )
