"""Dialect-specific SQL helpers — Phase P.2 catalog + P.3 Oracle fill +
P.3.e cleanup.

Every helper takes an explicit ``Dialect`` (no defaults — see "P.3.e
cleanup" below) and returns a dialect-appropriate SQL string. The
helpers split into two output shapes:

**Statement helpers** — return a fully terminated, self-contained
statement. Postgres branch ends in ``;``; Oracle branch wraps in
a PL/SQL block ending in ``END;``. Callers concatenate without
appending a separate ``;``.

  - ``drop_table_if_exists``
  - ``drop_matview_if_exists``
  - ``drop_index_if_exists``
  - ``drop_view_if_exists``
  - ``refresh_matview``
  - ``analyze_table``

**Fragment helpers** — return an expression-level SQL string with no
trailing ``;``. Substituted into larger SQL templates by the caller,
which decides where the statement boundary lives.

  - Type names (``serial_type``, ``timestamp_tz_type``, ``text_type``,
    ``varchar_type``, ``decimal_type``, ``boolean_type``, ``decimal_type``)
  - Casts (``cast``, ``typed_null``, ``to_date``, ``date_trunc_day``)
  - Date arithmetic (``epoch_seconds_between``, ``interval_days``,
    ``date_minus_days``)
  - Constraints (``json_check``)
  - Other clauses (``with_recursive``, ``create_matview``,
    ``matview_options``)

Phase notes:
- P.2 shipped every helper with a Postgres branch only.
- P.3 filled in the Oracle branches (19c Standard Edition target).
- P.3.e dropped the ``dialect: Dialect = Dialect.POSTGRES`` defaults
  so call sites must be explicit. Every in-tree caller already passed
  a dialect by then; defaults were a rollout convenience that's no
  longer load-bearing.
- ``_matview_options`` moved into this module from ``common.l2.schema``
  in P.3.e — it's a pure dialect helper and belongs alongside
  ``create_matview`` / ``refresh_matview``.
"""

from __future__ import annotations

from enum import Enum


class Dialect(str, Enum):
    """Target SQL dialect.

    Postgres covers Postgres 17+ (the version floor required by the
    SQL/JSON path syntax we already use). Oracle covers Oracle 19c
    Standard Edition (the long-term-support version Phase P targets).
    """

    POSTGRES = "postgres"
    ORACLE = "oracle"


# -- Type names (DDL) --------------------------------------------------------


def serial_type(dialect: Dialect) -> str:
    """Auto-incrementing 64-bit append-only key.

    Postgres ``BIGSERIAL`` / Oracle ``NUMBER GENERATED ALWAYS AS IDENTITY``.
    """
    if dialect is Dialect.POSTGRES:
        return "BIGSERIAL"
    return "NUMBER GENERATED ALWAYS AS IDENTITY"


def boolean_type(dialect: Dialect) -> str:
    """Boolean column type.

    Postgres has a native ``BOOLEAN``; Oracle 19c does not, so the
    canonical encoding is ``NUMBER(1)`` with a ``CHECK (col IN (0, 1))``.
    The helper returns just the type name — callers that need the
    CHECK constraint compose it themselves.
    """
    if dialect is Dialect.POSTGRES:
        return "BOOLEAN"
    return "NUMBER(1)"


def text_type(dialect: Dialect) -> str:
    """Unbounded character data.

    Postgres ``TEXT`` / Oracle ``CLOB``.
    """
    if dialect is Dialect.POSTGRES:
        return "TEXT"
    return "CLOB"


def timestamp_tz_type(dialect: Dialect) -> str:
    """Timestamp with time zone.

    Postgres ``TIMESTAMPTZ`` / Oracle ``TIMESTAMP WITH TIME ZONE``.
    """
    if dialect is Dialect.POSTGRES:
        return "TIMESTAMPTZ"
    return "TIMESTAMP WITH TIME ZONE"


def pk_safe_timestamp_type(dialect: Dialect) -> str:
    """Timestamp type usable in a PRIMARY KEY column.

    Postgres allows ``TIMESTAMPTZ`` in PKs; Oracle 19c rejects it
    with ORA-02329 ("column of datatype TIME/TIMESTAMP WITH TIME ZONE
    cannot be unique or a primary key"). Demote to plain
    ``TIMESTAMP`` on Oracle — loses the TZ metadata, but day-anchored
    snapshot timestamps (the only PK use in this codebase) don't
    depend on it.
    """
    if dialect is Dialect.POSTGRES:
        return "TIMESTAMPTZ"
    return "TIMESTAMP"


def varchar_type(n: int, dialect: Dialect) -> str:
    """Bounded variable-length character.

    Postgres ``VARCHAR(n)`` / Oracle ``VARCHAR2(n)``.
    """
    if dialect is Dialect.POSTGRES:
        return f"VARCHAR({n})"
    return f"VARCHAR2({n})"


def decimal_type(precision: int, scale: int, dialect: Dialect) -> str:
    """Fixed-precision decimal.

    Postgres ``DECIMAL(p,s)`` / Oracle ``NUMBER(p,s)``.
    """
    if dialect is Dialect.POSTGRES:
        return f"DECIMAL({precision},{scale})"
    return f"NUMBER({precision},{scale})"


# -- Casts -------------------------------------------------------------------


def cast(expr: str, type_name: str, dialect: Dialect) -> str:
    """Cast ``expr`` to ``type_name``.

    Postgres ``expr::type`` / Oracle ``CAST(expr AS type)``. Note the
    caller is responsible for passing a logical Postgres-style type
    name (``numeric``, ``bigint``, ``text``, ``TIMESTAMP``); the
    Oracle branch translates via ``_oracle_type_alias``.
    """
    if dialect is Dialect.POSTGRES:
        return f"{expr}::{type_name}"
    return f"CAST({expr} AS {_oracle_type_alias(type_name)})"


def typed_null(type_name: str, dialect: Dialect) -> str:
    """Typed NULL literal.

    Postgres ``NULL::type`` / Oracle ``CAST(NULL AS type)``. Postgres
    needs the explicit type because untyped NULL infers as ``text``,
    which breaks downstream ``numeric > text`` comparisons.
    """
    if dialect is Dialect.POSTGRES:
        return f"NULL::{type_name}"
    return f"CAST(NULL AS {_oracle_type_alias(type_name)})"


def to_date(timestamp_expr: str, dialect: Dialect) -> str:
    """Truncate a timestamp expression to its date component.

    Postgres ``expr::date`` / Oracle ``TRUNC(expr)``. Oracle's
    ``CAST(expr AS DATE)`` would also work but ``TRUNC`` is the
    idiomatic "drop the time" expression and reads cleaner for
    callers writing per-day rollups.
    """
    if dialect is Dialect.POSTGRES:
        return f"{timestamp_expr}::date"
    return f"TRUNC({timestamp_expr})"


# Oracle type-name canonicalization. Postgres uses lowercase
# ``numeric`` / ``bigint`` / ``date`` / ``timestamp`` per its docs;
# Oracle wants ``NUMBER`` / ``DATE`` / ``TIMESTAMP``. The
# ``_oracle_type_alias`` table keeps the helpers' callers free to
# pass Postgres-shape type names while the Oracle branch substitutes
# the right name automatically.
_ORACLE_TYPE_ALIASES = {
    "numeric": "NUMBER",
    "bigint": "NUMBER(19)",
    "int": "NUMBER(10)",
    "integer": "NUMBER(10)",
    "smallint": "NUMBER(5)",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
    "text": "CLOB",
    "boolean": "NUMBER(1)",
}


def _oracle_type_alias(type_name: str) -> str:
    """Return the Oracle equivalent of a Postgres-shape type name."""
    return _ORACLE_TYPE_ALIASES.get(type_name.lower(), type_name)


# -- JSON --------------------------------------------------------------------


def json_check(col: str, dialect: Dialect) -> str:
    """``CHECK (col IS NULL OR col IS JSON)`` in either dialect.

    The constraint syntax is identical in Postgres 16+ and Oracle
    12.2+ (both implement the SQL/JSON standard). Helper exists so
    the OR-NULL guard pattern stays consistent across emit sites
    and so future Oracle-side variants (e.g. ``IS JSON STRICT``)
    can land in one place.

    ``dialect`` is currently ignored (output is identical) but the
    parameter is kept so the signature matches every other helper —
    one less special case for callers to remember.
    """
    del dialect  # see docstring; reserved for future Oracle variants
    return f"CHECK ({col} IS NULL OR {col} IS JSON)"


# -- Date / time arithmetic --------------------------------------------------


def epoch_seconds_between(later: str, earlier: str, dialect: Dialect) -> str:
    """Difference between two timestamps in whole + fractional seconds.

    Postgres ``EXTRACT(EPOCH FROM (later - earlier))``. Oracle has
    no EPOCH unit; the equivalent for TIMESTAMP arithmetic (which
    yields ``INTERVAL DAY TO SECOND``) is the sum of
    EXTRACT(DAY/HOUR/MINUTE/SECOND FROM …) terms.
    """
    if dialect is Dialect.POSTGRES:
        return f"EXTRACT(EPOCH FROM ({later} - {earlier}))"
    diff = f"({later} - {earlier})"
    return (
        f"(EXTRACT(DAY FROM {diff}) * 86400 "
        f"+ EXTRACT(HOUR FROM {diff}) * 3600 "
        f"+ EXTRACT(MINUTE FROM {diff}) * 60 "
        f"+ EXTRACT(SECOND FROM {diff}))"
    )


def interval_days(n: int, dialect: Dialect) -> str:
    """A SQL interval literal of ``n`` days.

    Postgres ``INTERVAL '<n> day'`` / Oracle ``INTERVAL '<n>' DAY``.
    """
    if dialect is Dialect.POSTGRES:
        return f"INTERVAL '{n} day'"
    return f"INTERVAL '{n}' DAY"


def date_minus_days(date_expr: str, n: int, dialect: Dialect) -> str:
    """Subtract ``n`` days from a date expression.

    Postgres uses ``date - INTERVAL '<n> day'``; Oracle's DATE
    arithmetic interprets ``date - n`` as N days directly.
    """
    if dialect is Dialect.POSTGRES:
        return f"({date_expr} - {interval_days(n, dialect)})"
    return f"({date_expr} - {n})"


def date_trunc_day(timestamp_expr: str, dialect: Dialect) -> str:
    """Truncate a timestamp expression to its day boundary, preserving
    a timestamp-shaped result type so downstream JOINs against
    TIMESTAMPTZ columns don't fall through implicit conversion.

    Postgres ``DATE_TRUNC('day', expr)`` returns the same type as the
    input (TIMESTAMPTZ → TIMESTAMPTZ at 00:00:00). Oracle's ``TRUNC(X)``
    on a TIMESTAMP returns a DATE, which loses subseconds + the
    timestamp shape; wrapping in ``CAST(... AS TIMESTAMP)`` puts it
    back in the timestamp domain so the L1 invariant matviews compare
    equality the same way on both dialects.

    Distinct from ``to_date`` (which returns DATE-shape on both): use
    ``date_trunc_day`` when the result needs to behave as a timestamp
    in joins / comparisons; use ``to_date`` when the result is the
    final column the dashboard reads as a date.
    """
    if dialect is Dialect.POSTGRES:
        return f"DATE_TRUNC('day', {timestamp_expr})"
    return f"CAST(TRUNC({timestamp_expr}) AS TIMESTAMP)"


# -- DDL idempotency ---------------------------------------------------------


def drop_table_if_exists(name: str, dialect: Dialect) -> str:
    """Idempotent DROP TABLE — emits CASCADE so dependent FKs / views
    drop transitively.

    Postgres has native ``DROP TABLE IF EXISTS … CASCADE``. Oracle 19c
    needs a PL/SQL block that catches ORA-00942 (table not found).

    Returned string is **fully terminated** (Postgres trailing ``;``,
    Oracle ``END;`` PL/SQL terminator). Callers concatenate directly
    without appending ``;`` to avoid a double-semicolon that Oracle's
    PL/SQL parser rejects.
    """
    if dialect is Dialect.POSTGRES:
        return f"DROP TABLE IF EXISTS {name} CASCADE;"
    return _oracle_drop_if_exists(
        f"DROP TABLE {name} CASCADE CONSTRAINTS", ignore_codes=(-942,),
    )


def drop_matview_if_exists(name: str, dialect: Dialect) -> str:
    """Idempotent DROP MATERIALIZED VIEW.

    Postgres ``DROP MATERIALIZED VIEW IF EXISTS …;`` / Oracle PL/SQL
    block catching ORA-12003 (matview does not exist). Returned string
    is **fully terminated** — same convention as ``drop_table_if_exists``.
    """
    if dialect is Dialect.POSTGRES:
        return f"DROP MATERIALIZED VIEW IF EXISTS {name};"
    return _oracle_drop_if_exists(
        f"DROP MATERIALIZED VIEW {name}", ignore_codes=(-12003, -942),
    )


def drop_index_if_exists(name: str, dialect: Dialect) -> str:
    """Idempotent DROP INDEX.

    Postgres ``DROP INDEX IF EXISTS …;`` / Oracle PL/SQL block
    catching ORA-01418 (index does not exist). Returned string is
    **fully terminated**.
    """
    if dialect is Dialect.POSTGRES:
        return f"DROP INDEX IF EXISTS {name};"
    return _oracle_drop_if_exists(
        f"DROP INDEX {name}", ignore_codes=(-1418,),
    )


def drop_view_if_exists(name: str, dialect: Dialect) -> str:
    """Idempotent DROP VIEW.

    Postgres ``DROP VIEW IF EXISTS …;`` / Oracle PL/SQL block
    catching ORA-00942. Returned string is **fully terminated**.
    """
    if dialect is Dialect.POSTGRES:
        return f"DROP VIEW IF EXISTS {name};"
    return _oracle_drop_if_exists(
        f"DROP VIEW {name}", ignore_codes=(-942,),
    )


def _oracle_drop_if_exists(
    drop_stmt: str, *, ignore_codes: tuple[int, ...],
) -> str:
    """Wrap an Oracle DROP statement in a PL/SQL block that swallows
    "does not exist" errors so the script is idempotent.

    Re-raises any other SQLCODE so genuine failures (privilege issues,
    bad syntax) still surface. ``ignore_codes`` lists the negative
    SQLCODE values to swallow per object type (e.g. ORA-00942 = -942
    for TABLE / VIEW; ORA-01418 = -1418 for INDEX; ORA-12003 = -12003
    for MATERIALIZED VIEW).
    """
    not_in = " AND ".join(f"SQLCODE != {c}" for c in ignore_codes)
    return (
        f"BEGIN EXECUTE IMMEDIATE '{drop_stmt}'; "
        f"EXCEPTION WHEN OTHERS THEN IF {not_in} THEN RAISE; END IF; END;"
    )


# -- Materialized views ------------------------------------------------------


def create_matview(name: str, body_sql: str, dialect: Dialect) -> str:
    """``CREATE MATERIALIZED VIEW`` with the right options per dialect.

    Postgres: bare ``CREATE MATERIALIZED VIEW name AS body`` (build-
    on-create + manual refresh are the defaults). Oracle: explicit
    ``BUILD IMMEDIATE REFRESH ON DEMAND`` so behavior matches the
    Postgres expectation; without those options Oracle defaults to
    ``REFRESH FORCE ON DEMAND`` (incremental fast-refresh attempt
    first), which has more setup requirements.

    Note this helper does NOT add a trailing ``;`` — it's a one-shot
    convenience for callers that want the whole CREATE in one string,
    but most callers in this codebase splice the ``BUILD IMMEDIATE …``
    suffix into a template via ``matview_options(dialect)`` instead
    so the SELECT body stays inline + readable.
    """
    if dialect is Dialect.POSTGRES:
        return f"CREATE MATERIALIZED VIEW {name} AS {body_sql}"
    return (
        f"CREATE MATERIALIZED VIEW {name} "
        f"BUILD IMMEDIATE REFRESH COMPLETE ON DEMAND AS {body_sql}"
    )


def matview_options(dialect: Dialect) -> str:
    """Per-dialect suffix between ``CREATE MATERIALIZED VIEW <name>`` and
    ``AS <body>``. Postgres takes none; Oracle needs ``BUILD IMMEDIATE
    REFRESH COMPLETE ON DEMAND`` to match Postgres's build-on-create +
    manual-REFRESH semantics (without it Oracle defaults to
    ``REFRESH FORCE ON DEMAND``, which has more setup requirements).

    Used by ``common.l2.schema`` to splice the suffix into per-matview
    template strings (so the SELECT body stays inline + readable).
    Returns the empty string on Postgres so the substitution is a no-op.
    """
    if dialect is Dialect.POSTGRES:
        return ""
    return " BUILD IMMEDIATE REFRESH COMPLETE ON DEMAND"


def refresh_matview(name: str, dialect: Dialect) -> str:
    """``REFRESH MATERIALIZED VIEW`` per dialect.

    Postgres: ``REFRESH MATERIALIZED VIEW name;``. Oracle: a PL/SQL
    block invoking ``DBMS_MVIEW.REFRESH('name', method => 'C')`` —
    ``C`` = complete refresh, matching Postgres semantics. Returned
    string is **fully terminated** — same convention as the drop
    helpers.
    """
    if dialect is Dialect.POSTGRES:
        return f"REFRESH MATERIALIZED VIEW {name};"
    return f"BEGIN DBMS_MVIEW.REFRESH('{name}', method => 'C'); END;"


def analyze_table(name: str, dialect: Dialect) -> str:
    """Refresh planner statistics on a table or matview.

    Postgres: ``ANALYZE name;``. Oracle: ``BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'name'); END;``. Returned
    string is **fully terminated**.
    """
    if dialect is Dialect.POSTGRES:
        return f"ANALYZE {name};"
    return f"BEGIN DBMS_STATS.GATHER_TABLE_STATS(USER, '{name}'); END;"


# -- Recursive CTE -----------------------------------------------------------


def with_recursive(dialect: Dialect) -> str:
    """Recursive-CTE preamble keyword.

    Postgres requires the explicit ``WITH RECURSIVE`` keyword. Oracle
    19c infers recursion from the CTE body's self-reference and
    accepts (but does not require) ``RECURSIVE`` — emit just ``WITH``
    for portability across older Oracle releases.
    """
    if dialect is Dialect.POSTGRES:
        return "WITH RECURSIVE"
    return "WITH"
