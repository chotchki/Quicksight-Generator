"""Dialect-specific SQL helpers — Phase P.2 catalog.

Each helper accepts a ``Dialect`` enum value and returns a dialect-
appropriate SQL fragment. Phase P.2 ships every helper with a
Postgres branch only; the Oracle branch raises
``NotImplementedError`` until Phase P.3 fills it in.

Usage convention: import the enum + the helpers you need, pass
``Dialect.POSTGRES`` (the current default) or
``Dialect.ORACLE`` (Phase P.3 onward) at the call site. Default
parameter values keep existing call sites compatible while the
dialect plumbing propagates inward.
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


def _oracle_not_yet(name: str) -> str:
    return (
        f"{name}: the Oracle branch is not implemented yet. "
        "Phase P.3 fills this in."
    )


# -- Type names (DDL) --------------------------------------------------------


def serial_type(dialect: Dialect = Dialect.POSTGRES) -> str:
    """Auto-incrementing 64-bit append-only key.

    Postgres ``BIGSERIAL`` / Oracle ``NUMBER GENERATED ALWAYS AS IDENTITY``.
    """
    if dialect is Dialect.POSTGRES:
        return "BIGSERIAL"
    raise NotImplementedError(_oracle_not_yet("serial_type"))


def boolean_type(dialect: Dialect = Dialect.POSTGRES) -> str:
    """Boolean column type.

    Postgres has a native ``BOOLEAN``; Oracle 19c does not, so it
    encodes via ``NUMBER(1) CHECK (col IN (0, 1))``. The helper
    returns just the type name; callers that need the CHECK build
    it inline.
    """
    if dialect is Dialect.POSTGRES:
        return "BOOLEAN"
    raise NotImplementedError(_oracle_not_yet("boolean_type"))


def text_type(dialect: Dialect = Dialect.POSTGRES) -> str:
    """Unbounded character data.

    Postgres ``TEXT`` / Oracle ``CLOB``.
    """
    if dialect is Dialect.POSTGRES:
        return "TEXT"
    raise NotImplementedError(_oracle_not_yet("text_type"))


def timestamp_tz_type(dialect: Dialect = Dialect.POSTGRES) -> str:
    """Timestamp with time zone.

    Postgres ``TIMESTAMPTZ`` / Oracle ``TIMESTAMP WITH TIME ZONE``.
    """
    if dialect is Dialect.POSTGRES:
        return "TIMESTAMPTZ"
    raise NotImplementedError(_oracle_not_yet("timestamp_tz_type"))


def varchar_type(n: int, dialect: Dialect = Dialect.POSTGRES) -> str:
    """Bounded variable-length character.

    Postgres ``VARCHAR(n)`` / Oracle ``VARCHAR2(n)``.
    """
    if dialect is Dialect.POSTGRES:
        return f"VARCHAR({n})"
    raise NotImplementedError(_oracle_not_yet("varchar_type"))


def decimal_type(
    precision: int, scale: int, dialect: Dialect = Dialect.POSTGRES
) -> str:
    """Fixed-precision decimal.

    Postgres ``DECIMAL(p,s)`` / Oracle ``NUMBER(p,s)``.
    """
    if dialect is Dialect.POSTGRES:
        return f"DECIMAL({precision},{scale})"
    raise NotImplementedError(_oracle_not_yet("decimal_type"))


# -- Casts -------------------------------------------------------------------


def cast(expr: str, type_name: str, dialect: Dialect = Dialect.POSTGRES) -> str:
    """Cast ``expr`` to ``type_name``.

    Postgres ``expr::type`` / Oracle ``CAST(expr AS type)``.
    """
    if dialect is Dialect.POSTGRES:
        return f"{expr}::{type_name}"
    raise NotImplementedError(_oracle_not_yet("cast"))


def typed_null(type_name: str, dialect: Dialect = Dialect.POSTGRES) -> str:
    """Typed NULL literal.

    Postgres ``NULL::type`` / Oracle ``CAST(NULL AS type)``. Postgres
    needs the explicit type because untyped NULL infers as ``text``,
    which breaks downstream ``numeric > text`` comparisons.
    """
    if dialect is Dialect.POSTGRES:
        return f"NULL::{type_name}"
    raise NotImplementedError(_oracle_not_yet("typed_null"))


def to_date(
    timestamp_expr: str, dialect: Dialect = Dialect.POSTGRES
) -> str:
    """Truncate a timestamp expression to its date component.

    Postgres ``expr::date`` / Oracle ``CAST(expr AS DATE)`` (which
    coincidentally also truncates the time component on Oracle DATE,
    since Oracle's DATE type carries seconds resolution).
    """
    if dialect is Dialect.POSTGRES:
        return f"{timestamp_expr}::date"
    raise NotImplementedError(_oracle_not_yet("to_date"))


# -- JSON --------------------------------------------------------------------


def json_check(col: str, dialect: Dialect = Dialect.POSTGRES) -> str:
    """``CHECK (col IS NULL OR col IS JSON)`` in either dialect.

    Helper exists so the OR-NULL guard pattern stays consistent
    across emit sites (and so future Oracle-side variants — e.g.
    ``IS JSON STRICT`` — can land in one place).
    """
    if dialect is Dialect.POSTGRES:
        return f"CHECK ({col} IS NULL OR {col} IS JSON)"
    raise NotImplementedError(_oracle_not_yet("json_check"))


# -- Date / time arithmetic --------------------------------------------------


def epoch_seconds_between(
    later: str,
    earlier: str,
    dialect: Dialect = Dialect.POSTGRES,
) -> str:
    """Difference between two timestamps in whole + fractional seconds.

    Postgres ``EXTRACT(EPOCH FROM (later - earlier))`` / Oracle
    has no EPOCH unit; the equivalent is the sum of EXTRACT(DAY/HOUR/
    MINUTE/SECOND FROM …) terms. Helper insulates the call site.
    """
    if dialect is Dialect.POSTGRES:
        return f"EXTRACT(EPOCH FROM ({later} - {earlier}))"
    raise NotImplementedError(_oracle_not_yet("epoch_seconds_between"))


def interval_days(n: int, dialect: Dialect = Dialect.POSTGRES) -> str:
    """A SQL interval literal of ``n`` days.

    Postgres ``INTERVAL '<n> day'`` / Oracle ``INTERVAL '<n>' DAY``.
    """
    if dialect is Dialect.POSTGRES:
        return f"INTERVAL '{n} day'"
    raise NotImplementedError(_oracle_not_yet("interval_days"))


def date_minus_days(
    date_expr: str, n: int, dialect: Dialect = Dialect.POSTGRES
) -> str:
    """Subtract ``n`` days from a date expression.

    Postgres uses ``date - INTERVAL '<n> day'``; Oracle's DATE
    arithmetic interprets ``date - n`` as N days. Helper lets call
    sites stay agnostic.
    """
    if dialect is Dialect.POSTGRES:
        return f"({date_expr} - {interval_days(n, dialect)})"
    raise NotImplementedError(_oracle_not_yet("date_minus_days"))


# -- DDL idempotency ---------------------------------------------------------


def drop_table_if_exists(
    name: str, dialect: Dialect = Dialect.POSTGRES
) -> str:
    """Idempotent DROP TABLE — emits CASCADE so dependent FKs / views
    drop transitively.

    Postgres has native ``DROP TABLE IF EXISTS … CASCADE``. Oracle 19c
    needs a PL/SQL block that catches ORA-00942 (table not found).
    """
    if dialect is Dialect.POSTGRES:
        return f"DROP TABLE IF EXISTS {name} CASCADE"
    raise NotImplementedError(_oracle_not_yet("drop_table_if_exists"))


def drop_matview_if_exists(
    name: str, dialect: Dialect = Dialect.POSTGRES
) -> str:
    """Idempotent DROP MATERIALIZED VIEW.

    Postgres ``DROP MATERIALIZED VIEW IF EXISTS …`` / Oracle PL/SQL
    block catching ORA-12003 (no such matview).
    """
    if dialect is Dialect.POSTGRES:
        return f"DROP MATERIALIZED VIEW IF EXISTS {name}"
    raise NotImplementedError(_oracle_not_yet("drop_matview_if_exists"))


def drop_index_if_exists(
    name: str, dialect: Dialect = Dialect.POSTGRES
) -> str:
    """Idempotent DROP INDEX.

    Postgres ``DROP INDEX IF EXISTS …`` / Oracle PL/SQL block
    catching ORA-01418 (no such index).
    """
    if dialect is Dialect.POSTGRES:
        return f"DROP INDEX IF EXISTS {name}"
    raise NotImplementedError(_oracle_not_yet("drop_index_if_exists"))


def drop_view_if_exists(
    name: str, dialect: Dialect = Dialect.POSTGRES
) -> str:
    """Idempotent DROP VIEW.

    Postgres ``DROP VIEW IF EXISTS …`` / Oracle PL/SQL block
    catching ORA-00942.
    """
    if dialect is Dialect.POSTGRES:
        return f"DROP VIEW IF EXISTS {name}"
    raise NotImplementedError(_oracle_not_yet("drop_view_if_exists"))


# -- Materialized views ------------------------------------------------------


def create_matview(
    name: str, body_sql: str, dialect: Dialect = Dialect.POSTGRES
) -> str:
    """``CREATE MATERIALIZED VIEW`` with the right options per dialect.

    Postgres: bare ``CREATE MATERIALIZED VIEW name AS body``. Oracle:
    ``CREATE MATERIALIZED VIEW name BUILD IMMEDIATE REFRESH ON DEMAND
    AS body`` — the Oracle defaults differ from what we want, so we
    spell the options.
    """
    if dialect is Dialect.POSTGRES:
        return f"CREATE MATERIALIZED VIEW {name} AS {body_sql}"
    raise NotImplementedError(_oracle_not_yet("create_matview"))


def refresh_matview(
    name: str, dialect: Dialect = Dialect.POSTGRES
) -> str:
    """``REFRESH MATERIALIZED VIEW`` per dialect.

    Postgres: bare ``REFRESH MATERIALIZED VIEW name``. Oracle: a PL/SQL
    block invoking ``DBMS_MVIEW.REFRESH('name')``.
    """
    if dialect is Dialect.POSTGRES:
        return f"REFRESH MATERIALIZED VIEW {name}"
    raise NotImplementedError(_oracle_not_yet("refresh_matview"))


def analyze_table(
    name: str, dialect: Dialect = Dialect.POSTGRES
) -> str:
    """Refresh planner statistics on a table or matview.

    Postgres: ``ANALYZE name``. Oracle: ``BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'name'); END;``.
    """
    if dialect is Dialect.POSTGRES:
        return f"ANALYZE {name}"
    raise NotImplementedError(_oracle_not_yet("analyze_table"))


# -- Recursive CTE -----------------------------------------------------------


def with_recursive(dialect: Dialect = Dialect.POSTGRES) -> str:
    """Recursive-CTE preamble keyword.

    Postgres requires the explicit ``WITH RECURSIVE`` keyword. Oracle
    19c infers recursion from the CTE body's self-reference and
    rejects ``RECURSIVE`` — so the preamble there is just ``WITH``.
    """
    if dialect is Dialect.POSTGRES:
        return "WITH RECURSIVE"
    raise NotImplementedError(_oracle_not_yet("with_recursive"))
