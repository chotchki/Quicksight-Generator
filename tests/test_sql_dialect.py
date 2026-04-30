"""Unit tests for ``common.sql.dialect``.

Phase P.2 ships every helper with a Postgres branch only; the Oracle
branch raises ``NotImplementedError`` as the placeholder. Tests
cover the full Postgres surface + assert that every helper fails
loudly on Oracle until P.3 fills it in.
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


class TestPostgresJson:
    def test_json_check(self):
        assert json_check("metadata", PG) == (
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
    def test_drop_table(self):
        assert drop_table_if_exists("foo", PG) == (
            "DROP TABLE IF EXISTS foo CASCADE"
        )

    def test_drop_matview(self):
        assert drop_matview_if_exists("p_drift", PG) == (
            "DROP MATERIALIZED VIEW IF EXISTS p_drift"
        )

    def test_drop_index(self):
        assert drop_index_if_exists("idx_foo", PG) == (
            "DROP INDEX IF EXISTS idx_foo"
        )

    def test_drop_view(self):
        assert drop_view_if_exists("v_foo", PG) == "DROP VIEW IF EXISTS v_foo"


class TestPostgresMatviews:
    def test_create_matview(self):
        result = create_matview("p_drift", "SELECT 1", PG)
        assert result == "CREATE MATERIALIZED VIEW p_drift AS SELECT 1"

    def test_refresh_matview(self):
        assert refresh_matview("p_drift", PG) == (
            "REFRESH MATERIALIZED VIEW p_drift"
        )

    def test_analyze_table(self):
        assert analyze_table("p_drift", PG) == "ANALYZE p_drift"


class TestPostgresRecursiveCte:
    def test_with_recursive(self):
        assert with_recursive(PG) == "WITH RECURSIVE"


# -- Oracle branches all NotImplementedError --------------------------------


_ORACLE_HELPERS_NULLARY = [
    serial_type, boolean_type, text_type, timestamp_tz_type, with_recursive,
]

_ORACLE_HELPERS_UNARY = [
    drop_table_if_exists, drop_matview_if_exists, drop_index_if_exists,
    drop_view_if_exists, refresh_matview, analyze_table,
    typed_null, to_date, json_check,
]


class TestOracleNotYet:
    @pytest.mark.parametrize("fn", _ORACLE_HELPERS_NULLARY)
    def test_nullary_oracle_raises(self, fn):
        with pytest.raises(NotImplementedError, match="Oracle branch"):
            fn(ORA)

    @pytest.mark.parametrize("fn", _ORACLE_HELPERS_UNARY)
    def test_unary_oracle_raises(self, fn):
        with pytest.raises(NotImplementedError, match="Oracle branch"):
            fn("foo", ORA)

    def test_varchar_oracle_raises(self):
        with pytest.raises(NotImplementedError, match="Oracle branch"):
            varchar_type(100, ORA)

    def test_decimal_oracle_raises(self):
        with pytest.raises(NotImplementedError, match="Oracle branch"):
            decimal_type(20, 2, ORA)

    def test_cast_oracle_raises(self):
        with pytest.raises(NotImplementedError, match="Oracle branch"):
            cast("col", "numeric", ORA)

    def test_epoch_seconds_oracle_raises(self):
        with pytest.raises(NotImplementedError, match="Oracle branch"):
            epoch_seconds_between("a", "b", ORA)

    def test_interval_days_oracle_raises(self):
        with pytest.raises(NotImplementedError, match="Oracle branch"):
            interval_days(1, ORA)

    def test_date_minus_days_oracle_raises(self):
        with pytest.raises(NotImplementedError, match="Oracle branch"):
            date_minus_days("d", 1, ORA)

    def test_create_matview_oracle_raises(self):
        with pytest.raises(NotImplementedError, match="Oracle branch"):
            create_matview("name", "SELECT 1", ORA)


# -- Dialect enum ------------------------------------------------------------


class TestDialectEnum:
    def test_string_values(self):
        assert Dialect.POSTGRES.value == "postgres"
        assert Dialect.ORACLE.value == "oracle"

    def test_round_trip_from_string(self):
        assert Dialect("postgres") is Dialect.POSTGRES
        assert Dialect("oracle") is Dialect.ORACLE
