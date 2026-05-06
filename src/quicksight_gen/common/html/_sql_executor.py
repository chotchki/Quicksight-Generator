"""X.2.f — generic SQL executor with dialect-aware filter substitution.

Today's ``_db_fetcher.py`` hand-writes WHERE clauses + bind params
inline per visual. X.2.g will need the same pattern across dozens
of visuals — at that point the boilerplate becomes the bug surface.
This module is the abstraction: a Visual + its dataset SQL + the
URL-keyed filter dict → executed query → ``(rows, columns)``.

Filter param convention (from X.2.d's URL contract):

    date_from    → WHERE <date_col> >= :date_from
    date_to      → WHERE <date_col> <= :date_to
    param_<name> → bound to ``:<name>`` in dataset SQL
    filter_<col> → WHERE <col> IN (...) (comma-split server side)
    min_<col>    → WHERE <col> >= :min_<col>
    max_<col>    → WHERE <col> <= :max_<col>

The dataset SQL author opts in to filters by referencing them as
``:date_from`` / ``:param_view`` / etc. Filters not referenced are
silently ignored (zero-impact when a sheet doesn't carry them).

Placeholder dispatch:

    Postgres → ``%(name)s``  (psycopg2 named bind)
    Oracle   → ``:name``     (oracledb named bind)
    SQLite   → ``:name``     (sqlite3 named bind)

So Oracle and SQLite share the source form (``:name``); Postgres
gets a single rewrite pass before execution.

Pure module — no network / no DB. The connection_factory is the
seam. ``execute_visual_sql`` is renderer-agnostic; ``shape_for_kind``
in ``_data_shape.py`` is the per-renderer step that follows.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from quicksight_gen.common.sql.dialect import Dialect


# Matches ``:name`` placeholders. Excludes ``::`` (Postgres cast
# operator) by requiring the colon to NOT be preceded by another
# colon — uses a negative lookbehind. Identifier characters per
# Python identifier rules + digits.
_NAMED_PLACEHOLDER_RE = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


def rewrite_placeholders_for_dialect(sql: str, dialect: Dialect) -> str:
    """Convert ``:name`` placeholders to dialect-native form.

    SQLite + Oracle accept ``:name`` natively (DB-API 2.0 named
    paramstyle); Postgres uses ``%(name)s``. The rewrite is purely
    string-level — caller still passes the same dict of bind values
    regardless of dialect. ``::`` (PG cast) is preserved.
    """
    if dialect is Dialect.POSTGRES:
        return _NAMED_PLACEHOLDER_RE.sub(r"%(\1)s", sql)
    # Oracle + SQLite already accept ``:name``.
    return sql


def collect_bind_params(
    sql: str,
    url_params: dict[str, str],
) -> dict[str, Any]:
    """Build the bind-param dict for the SQL string.

    Walks ``sql`` for ``:name`` placeholders, looks up each name in
    ``url_params``, and returns the dict the DB driver wants. Names
    not present in ``url_params`` get an empty string — the dataset
    SQL author is responsible for guarding against empty filters
    (typically ``WHERE col >= :date_from OR :date_from = ''``).
    Names referenced in ``url_params`` but NOT in the SQL are
    dropped (no-op in the bind dict — the DB driver would reject
    them with "too many parameters" otherwise).
    """
    referenced = set(_NAMED_PLACEHOLDER_RE.findall(sql))
    return {name: url_params.get(name, "") for name in referenced}


def execute_visual_sql(
    connection_factory: Callable[[], Any],
    sql: str,
    url_params: dict[str, str],
    *,
    dialect: Dialect,
) -> tuple[list[tuple[Any, ...]], list[str]]:
    """Execute a Visual's dataset SQL + return ``(rows, columns)``.

    Args:
        connection_factory: returns a fresh DB-API 2.0 connection.
            Caller is responsible for pooling / sharing if relevant
            — the spike opens + closes per call.
        sql: dataset SQL with ``:name`` placeholders (any dialect).
        url_params: the URL-keyed filter dict the App2 server
            extracted from the request query string. Keys not
            referenced in ``sql`` are ignored.
        dialect: SQL dialect of the connection. Drives placeholder
            rewriting (PG → ``%(name)s``; Oracle / SQLite stay).

    Returns:
        ``(rows, columns)``: rows is a list of tuples, columns is
        the list of column names from ``cursor.description``. The
        per-renderer shape adapter in ``_data_shape.py`` consumes
        this tuple.

    Raises:
        Whatever the DB driver raises on bad SQL / connection
        failure. The App2 server's themed-500 handler (X.2.m)
        catches it.
    """
    rewritten = rewrite_placeholders_for_dialect(sql, dialect)
    binds = collect_bind_params(sql, url_params)
    conn = connection_factory()
    try:
        cur = conn.cursor()
        try:
            cur.execute(rewritten, binds)
            rows = list(cur.fetchall())
            description = cur.description or []
            columns = [str(c[0]) for c in description]
        finally:
            cur.close()
    finally:
        conn.close()
    return [tuple(r) for r in rows], columns
