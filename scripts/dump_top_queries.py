"""Dump the top-N most expensive queries hitting the test schema.

W.8a — perf-debug companion to the e2e suite. After tests run
(``e2e-pg-api`` / ``e2e-pg-browser`` / ``e2e-oracle-api``), this
queries the dialect's stats view to surface the slowest queries
that touched our L2 instance's tables, writes a markdown table to
``--output``, and the workflow uploads it as a CI artifact.

Sources:

* PostgreSQL — ``pg_stat_statements`` (auto-loaded on Aurora; needs
  ``CREATE EXTENSION pg_stat_statements`` once per database).
* Oracle — ``v$sqlstats`` (DBA view; the ``admin`` user on RDS
  Oracle SE2 has read access by default).

Both sources are cumulative across the operator's other workloads
on the shared DB. We filter to queries whose text contains the
configured ``--like`` substring (default: ``spec_example``, the CI
L2 instance prefix) so the output is ours, not noise from other
tenants.

Output is best-effort. When the stats view is unavailable
(extension not installed, permission denied, dialect not yet
supported), this exits 0 with a "skipped" note in the markdown so
a missing perf snapshot never breaks CI.

Usage::

    .venv/bin/python scripts/dump_top_queries.py \\
        -c /tmp/ci-pg.yaml -o /tmp/top-queries.md --top 50
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quicksight_gen.common.config import load_config  # noqa: E402
from quicksight_gen.common.db import connect_demo_db  # noqa: E402
from quicksight_gen.common.sql import Dialect  # noqa: E402


# pg_stat_statements: top-N rows by cumulative execution time. Cast
# microsecond columns to ms for human readability. Filter on query
# text containing the L2 instance prefix so we drop the operator's
# unrelated traffic on the shared database.
_PG_TOP_QUERIES_SQL = """
SELECT
    calls,
    ROUND(total_exec_time::numeric, 1) AS total_ms,
    ROUND(mean_exec_time::numeric, 2)  AS mean_ms,
    rows,
    LEFT(REGEXP_REPLACE(query, '\\s+', ' ', 'g'), 400) AS query_text
FROM pg_stat_statements
WHERE query ILIKE %s
ORDER BY total_exec_time DESC
LIMIT %s
"""


# v$sqlstats: same shape, micro to ms via /1000. ``elapsed_time`` is
# the closest analog to ``total_exec_time``. Oracle uses bind-style
# parameters (``:1``, ``:2``) for the prepared statement.
_ORACLE_TOP_QUERIES_SQL = """
SELECT
    executions,
    ROUND(elapsed_time / 1000.0, 1) AS total_ms,
    ROUND((elapsed_time / NULLIF(executions, 0)) / 1000.0, 2) AS mean_ms,
    rows_processed,
    SUBSTR(REGEXP_REPLACE(sql_fulltext, '\\s+', ' '), 1, 400) AS query_text
FROM v$sqlstats
WHERE UPPER(sql_fulltext) LIKE UPPER(:1)
ORDER BY elapsed_time DESC
FETCH FIRST :2 ROWS ONLY
"""


def _fetch_postgres(conn: Any, like_pattern: str, top: int) -> list[tuple[Any, ...]]:
    cur = conn.cursor()
    try:
        # Idempotent bootstrap. On Aurora PG the rds_superuser role
        # (default for the master user) can run this; on locked-down
        # PGs it'll raise InsufficientPrivilege which we swallow so
        # the next query falls into the script's "skipped" path with
        # a useful reason.
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
            conn.commit()
        except Exception:
            conn.rollback()
        cur.execute(_PG_TOP_QUERIES_SQL, (f"%{like_pattern}%", top))
        return list(cur.fetchall())
    finally:
        cur.close()


def _fetch_oracle(conn: Any, like_pattern: str, top: int) -> list[tuple[Any, ...]]:
    cur = conn.cursor()
    try:
        cur.execute(_ORACLE_TOP_QUERIES_SQL, (f"%{like_pattern}%", top))
        return list(cur.fetchall())
    finally:
        cur.close()


def _format_markdown(
    *,
    title: str,
    dialect: str,
    like_pattern: str,
    rows: list[tuple[Any, ...]],
    note: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- **Dialect:** {dialect}")
    lines.append(f"- **Filter (LIKE):** `%{like_pattern}%`")
    lines.append(f"- **Rows returned:** {len(rows)}")
    if note:
        lines.append(f"- **Note:** {note}")
    lines.append("")
    if not rows:
        lines.append("_No matching rows._")
        return "\n".join(lines) + "\n"
    lines.append("| Calls | Total (ms) | Mean (ms) | Rows | Query |")
    lines.append("|---:|---:|---:|---:|---|")
    for r in rows:
        calls, total_ms, mean_ms, n_rows, query_text = r
        # Markdown table escapes — pipes inside the query break the
        # row, backticks make literal-render look right.
        q = (query_text or "").replace("|", "\\|").replace("\n", " ")
        q = textwrap.shorten(q, width=380, placeholder="…")
        lines.append(
            f"| {calls} | {total_ms} | {mean_ms} | {n_rows} | `{q}` |"
        )
    return "\n".join(lines) + "\n"


def _format_skipped(*, title: str, dialect: str, reason: str) -> str:
    return (
        f"# {title}\n\n"
        f"- **Dialect:** {dialect}\n"
        f"- **Status:** _skipped_\n"
        f"- **Reason:** {reason}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", required=True, type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument(
        "--like",
        default="spec_example",
        help=(
            "Filter queries whose text contains this substring "
            "(default: spec_example, the CI L2 instance prefix)."
        ),
    )
    parser.add_argument(
        "--top", type=int, default=50, help="Number of rows to dump (default: 50)."
    )
    parser.add_argument(
        "--title",
        default="Top expensive queries",
        help="Heading for the markdown output (default: 'Top expensive queries').",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    dialect = "postgres" if cfg.dialect is Dialect.POSTGRES else "oracle"

    try:
        conn = connect_demo_db(cfg)
    except Exception as e:
        # Connection failure: surface as a skipped note, never break CI.
        args.output.write_text(
            _format_skipped(
                title=args.title,
                dialect=dialect,
                reason=f"could not connect: {e!r}",
            )
        )
        print(f"[dump_top_queries] connect failed: {e!r}", file=sys.stderr)
        return 0

    try:
        if cfg.dialect is Dialect.POSTGRES:
            rows = _fetch_postgres(conn, args.like, args.top)
        elif cfg.dialect is Dialect.ORACLE:
            rows = _fetch_oracle(conn, args.like, args.top)
        else:
            args.output.write_text(
                _format_skipped(
                    title=args.title,
                    dialect=dialect,
                    reason=f"unsupported dialect {cfg.dialect!r}",
                )
            )
            return 0
    except Exception as e:
        # Most likely: pg_stat_statements not installed (PG) or
        # ORA-00942 / ORA-01031 on v$sqlstats (Oracle, no privilege).
        # Either way, write a skipped marker and exit clean.
        args.output.write_text(
            _format_skipped(
                title=args.title,
                dialect=dialect,
                reason=(
                    f"stats view unavailable: {type(e).__name__}: {e}. "
                    f"Pre-req for postgres: ``CREATE EXTENSION "
                    f"pg_stat_statements;``. For oracle: SELECT on "
                    f"``v$sqlstats``."
                ),
            )
        )
        print(f"[dump_top_queries] query failed: {e!r}", file=sys.stderr)
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass

    args.output.write_text(
        _format_markdown(
            title=args.title,
            dialect=dialect,
            like_pattern=args.like,
            rows=rows,
        )
    )
    print(
        f"[dump_top_queries] wrote {len(rows)} rows to {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
