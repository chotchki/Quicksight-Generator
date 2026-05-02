"""Unit tests for the probe parser + assertion helper."""

from __future__ import annotations

import pytest

from quicksight_gen.common.probe import (
    ProbedError,
    _parse_stream_error,
    assert_no_datasource_errors,
)


_ORA_STREAM_LINE = (
    'Stream error occurred: '
    '{"accountId":"470656905821","timestampInMillis":1777611217046,'
    '"requestId":"abc","region":"us-east-1",'
    '"errorCodeHierarchyPrimitiveModel":['
    '{"name":"GENERIC_SQL_EXCEPTION","type":"ERROR"},'
    '{"name":"GENERIC_DATA_SOURCE_EXCEPTION","type":"FAULT"},'
    '{"name":"SERVICE_EXCEPTION","type":"FAULT"}],'
    '"error":"SERVICE",'
    '"internalMessage":"ORA-00904: \\"table_count\\": invalid identifier'
    '\\n\\nhttps://docs.oracle.com/error-help/db/ora-00904/",'
    '"cid":"abc"}'
)


def test_parse_oracle_invalid_identifier() -> None:
    err = _parse_stream_error(_ORA_STREAM_LINE)
    assert err is not None
    assert err.error_class == "GENERIC_SQL_EXCEPTION"
    assert "ORA-00904" in err.message
    assert "table_count" in err.message
    # The Oracle help URL trailer is stripped so the message reads cleanly.
    assert "docs.oracle.com" not in err.message


def test_parse_non_stream_error_line_returns_none() -> None:
    assert _parse_stream_error("[log] just some console noise") is None
    assert _parse_stream_error("Stream error occurred: not-json-here") is None


def test_assert_no_datasource_errors_passes_when_clean() -> None:
    # Mix of console noise that doesn't include any Stream error payload.
    assert_no_datasource_errors([
        "[log] React DevTools",
        "[warning] HydrateFallback element missing",
        "[error] Failed to load resource: 404",
    ])


def test_assert_no_datasource_errors_raises_on_ora_error() -> None:
    with pytest.raises(AssertionError) as exc_info:
        assert_no_datasource_errors(
            [_ORA_STREAM_LINE], context="dashboard demo-l1",
        )
    msg = str(exc_info.value)
    assert "demo-l1" in msg
    assert "ORA-00904" in msg
    assert "GENERIC_SQL_EXCEPTION" in msg


def test_assert_no_datasource_errors_dedupes_repeated_errors() -> None:
    # The same error fires once per visual/page rerender; we collapse
    # identical (error_class, message) pairs so the assertion message
    # stays scannable instead of repeating the same line dozens of times.
    with pytest.raises(AssertionError) as exc_info:
        assert_no_datasource_errors([_ORA_STREAM_LINE] * 5)
    body = str(exc_info.value)
    assert body.count("ORA-00904") == 1


def test_probed_error_is_named_tuple() -> None:
    e = ProbedError(error_class="X", message="y")
    assert e.error_class == "X"
    assert e.message == "y"
    # Acts like a tuple — useful for set-keying in the dedupe path.
    assert (e.error_class, e.message) == ("X", "y")
