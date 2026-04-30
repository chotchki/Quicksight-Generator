"""Unit tests for ``common.sql.dialect``.

Phase P.2 shipped every helper with a Postgres branch only; Phase
P.3 filled in the Oracle branches. Tests cover both — the Postgres
branch returns the canonical bytes, the Oracle branch returns the
Oracle 19c-compatible equivalent.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.sql import (
    Dialect,
    analyze_table,
    boolean_type,
    cast,
    create_matview,
    date_minus_days,
    decimal_type,
    drop_index_if_exists,
    drop_matview_if_exists,
    drop_table_if_exists,
    drop_view_if_exists,
    epoch_seconds_between,
    interval_days,
    json_check,
    refresh_matview,
    serial_type,
    text_type,
    timestamp_tz_type,
    to_date,
    typed_null,
    varchar_type,
    with_recursive,
)


PG = Dialect.POSTGRES
ORA = Dialect.ORACLE


# -- Postgres branches -------------------------------------------------------


class TestPostgresTypeNames:
    def test_serial_type(self):
        assert serial_type(PG) == "BIGSERIAL"

    def test_boolean_type(self):
        assert boolean_type(PG) == "BOOLEAN"

    def test_text_type(self):
        assert text_type(PG) == "TEXT"

    def test_timestamp_tz_type(self):
        assert timestamp_tz_type(PG) == "TIMESTAMPTZ"

    def test_varchar_type(self):
        assert varchar_type(100, PG) == "VARCHAR(100)"

    def test_decimal_type(self):
        assert decimal_type(20, 2, PG) == "DECIMAL(20,2)"


class TestPostgresCasts:
    def test_cast(self):
        assert cast("col", "numeric", PG) == "col::numeric"
        assert cast("(a + b)", "bigint", PG) == "(a + b)::bigint"

    def test_typed_null(self):
        assert typed_null("numeric", PG) == "NULL::numeric"
        assert typed_null("bigint", PG) == "NULL::bigint"

    def test_to_date(self):
        assert to_date("posting", PG) == "posting::date"
        assert to_date("recipient.posting", PG) == "recipient.posting::date"


class TestPortableJson:
    def test_json_check_postgres(self):
        assert json_check("metadata", PG) == (
            "CHECK (metadata IS NULL OR metadata IS JSON)"
        )

    def test_json_check_oracle_identical(self):
        # Both dialects ship SQL/JSON-standard IS JSON since
        # Postgres 16+ / Oracle 12.2+ — bytes-identical output.
        assert json_check("metadata", ORA) == (
            "CHECK (metadata IS NULL OR metadata IS JSON)"
        )


class TestPostgresDateTime:
    def test_epoch_seconds_between(self):
        assert epoch_seconds_between(
            "CURRENT_TIMESTAMP", "ct.posting", PG,
        ) == "EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - ct.posting))"

    def test_interval_days(self):
        assert interval_days(1, PG) == "INTERVAL '1 day'"
        assert interval_days(7, PG) == "INTERVAL '7 day'"

    def test_date_minus_days(self):
        assert date_minus_days("pw.posted_day", 1, PG) == (
            "(pw.posted_day - INTERVAL '1 day')"
        )


class TestPostgresDdlIdempotency:
    # P.3.d.2 — DDL idempotency + statement-runner helpers return
    # **fully terminated** statements so the Oracle PL/SQL ``END;`` and
    # the Postgres trailing ``;`` share one convention. Callers
    # concatenate without appending ``;``.

    def test_drop_table(self):
        assert drop_table_if_exists("foo", PG) == (
            "DROP TABLE IF EXISTS foo CASCADE;"
        )

    def test_drop_matview(self):
        assert drop_matview_if_exists("p_drift", PG) == (
            "DROP MATERIALIZED VIEW IF EXISTS p_drift;"
        )

    def test_drop_index(self):
        assert drop_index_if_exists("idx_foo", PG) == (
            "DROP INDEX IF EXISTS idx_foo;"
        )

    def test_drop_view(self):
        assert drop_view_if_exists("v_foo", PG) == "DROP VIEW IF EXISTS v_foo;"


class TestPostgresMatviews:
    def test_create_matview(self):
        # ``create_matview`` is the only matview helper that does NOT
        # carry its own terminator — its caller wraps the whole
        # CREATE in a ; or stitches it inline in a template.
        result = create_matview("p_drift", "SELECT 1", PG)
        assert result == "CREATE MATERIALIZED VIEW p_drift AS SELECT 1"

    def test_refresh_matview(self):
        assert refresh_matview("p_drift", PG) == (
            "REFRESH MATERIALIZED VIEW p_drift;"
        )

    def test_analyze_table(self):
        assert analyze_table("p_drift", PG) == "ANALYZE p_drift;"


class TestPostgresRecursiveCte:
    def test_with_recursive(self):
        assert with_recursive(PG) == "WITH RECURSIVE"


# -- Oracle branches ---------------------------------------------------------


class TestOracleTypeNames:
    def test_serial_type(self):
        assert serial_type(ORA) == "NUMBER GENERATED ALWAYS AS IDENTITY"

    def test_boolean_type(self):
        # Oracle 19c has no native BOOLEAN; canonical encoding is
        # NUMBER(1). Caller composes the CHECK (col IN (0,1)).
        assert boolean_type(ORA) == "NUMBER(1)"

    def test_text_type(self):
        assert text_type(ORA) == "CLOB"

    def test_timestamp_tz_type(self):
        assert timestamp_tz_type(ORA) == "TIMESTAMP WITH TIME ZONE"

    def test_varchar_type(self):
        assert varchar_type(100, ORA) == "VARCHAR2(100)"

    def test_decimal_type(self):
        assert decimal_type(20, 2, ORA) == "NUMBER(20,2)"


class TestOracleCasts:
    def test_cast_numeric_aliases_to_number(self):
        # Postgres-shape "numeric" → Oracle "NUMBER".
        assert cast("col", "numeric", ORA) == "CAST(col AS NUMBER)"

    def test_cast_bigint_aliases_to_number_19(self):
        assert cast("(a + b)", "bigint", ORA) == "CAST((a + b) AS NUMBER(19))"

    def test_cast_unaliased_type_passes_through(self):
        # Type names not in the Postgres-alias table pass through verbatim.
        assert cast("col", "VARCHAR2(50)", ORA) == "CAST(col AS VARCHAR2(50))"

    def test_typed_null_numeric(self):
        assert typed_null("numeric", ORA) == "CAST(NULL AS NUMBER)"

    def test_typed_null_bigint(self):
        assert typed_null("bigint", ORA) == "CAST(NULL AS NUMBER(19))"

    def test_to_date(self):
        assert to_date("posting", ORA) == "TRUNC(posting)"


class TestOracleDateTime:
    def test_epoch_seconds_between(self):
        # Oracle has no EPOCH unit; replicate via DAY*86400 +
        # HOUR*3600 + MINUTE*60 + SECOND on the INTERVAL DAY TO SECOND
        # result.
        result = epoch_seconds_between("CURRENT_TIMESTAMP", "ct.posting", ORA)
        assert "EXTRACT(DAY FROM " in result
        assert "* 86400" in result
        assert "EXTRACT(SECOND FROM " in result

    def test_interval_days(self):
        assert interval_days(1, ORA) == "INTERVAL '1' DAY"
        assert interval_days(7, ORA) == "INTERVAL '7' DAY"

    def test_date_minus_days(self):
        # Oracle DATE arithmetic interprets "date - n" as N days.
        assert date_minus_days("pw.posted_day", 1, ORA) == "(pw.posted_day - 1)"


class TestOracleDdlIdempotency:
    def test_drop_table_wraps_in_plsql_block(self):
        sql = drop_table_if_exists("foo", ORA)
        assert sql.startswith("BEGIN EXECUTE IMMEDIATE 'DROP TABLE foo CASCADE CONSTRAINTS'")
        assert "EXCEPTION" in sql
        assert "SQLCODE != -942" in sql
        assert sql.endswith("END;")

    def test_drop_matview_swallows_two_codes(self):
        sql = drop_matview_if_exists("p_drift", ORA)
        # ORA-12003 (matview) AND ORA-942 (table-or-view, in case the
        # object has been recreated as a regular table) both ignored.
        assert "SQLCODE != -12003" in sql
        assert "SQLCODE != -942" in sql

    def test_drop_index_swallows_1418(self):
        sql = drop_index_if_exists("idx_foo", ORA)
        assert "SQLCODE != -1418" in sql

    def test_drop_view_swallows_942(self):
        sql = drop_view_if_exists("v_foo", ORA)
        assert "SQLCODE != -942" in sql


class TestOracleMatviews:
    def test_create_matview_emits_build_immediate(self):
        sql = create_matview("p_drift", "SELECT 1", ORA)
        assert "BUILD IMMEDIATE" in sql
        assert "REFRESH COMPLETE ON DEMAND" in sql
        assert sql.endswith("AS SELECT 1")

    def test_refresh_matview_uses_dbms_mview(self):
        assert refresh_matview("p_drift", ORA) == (
            "BEGIN DBMS_MVIEW.REFRESH('p_drift', method => 'C'); END;"
        )

    def test_analyze_table_uses_dbms_stats(self):
        assert analyze_table("p_drift", ORA) == (
            "BEGIN DBMS_STATS.GATHER_TABLE_STATS(USER, 'p_drift'); END;"
        )


class TestOracleRecursiveCte:
    def test_with_recursive_drops_keyword(self):
        # Oracle 19c infers recursion from self-reference; "WITH" alone.
        assert with_recursive(ORA) == "WITH"


# -- Dialect enum ------------------------------------------------------------


class TestDialectEnum:
    def test_string_values(self):
        assert Dialect.POSTGRES.value == "postgres"
        assert Dialect.ORACLE.value == "oracle"

    def test_round_trip_from_string(self):
        assert Dialect("postgres") is Dialect.POSTGRES
        assert Dialect("oracle") is Dialect.ORACLE


# -- Default-arg behavior ---------------------------------------------------


class TestDefaultDialect:
    """Every helper defaults to Postgres so existing callers don't
    have to thread a dialect argument until P.4 propagates it.
    """

    @pytest.mark.parametrize(
        "fn,args,expected",
        [
            (serial_type, (), "BIGSERIAL"),
            (boolean_type, (), "BOOLEAN"),
            (text_type, (), "TEXT"),
            (timestamp_tz_type, (), "TIMESTAMPTZ"),
            (varchar_type, (50,), "VARCHAR(50)"),
            (decimal_type, (10, 2), "DECIMAL(10,2)"),
            (typed_null, ("numeric",), "NULL::numeric"),
            (interval_days, (1,), "INTERVAL '1 day'"),
            (with_recursive, (), "WITH RECURSIVE"),
            (refresh_matview, ("foo",), "REFRESH MATERIALIZED VIEW foo;"),
            (analyze_table, ("foo",), "ANALYZE foo;"),
        ],
    )
    def test_postgres_default(self, fn, args, expected):
        assert fn(*args) == expected
