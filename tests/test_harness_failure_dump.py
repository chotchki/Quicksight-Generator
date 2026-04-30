"""Unit tests for ``tests/e2e/_harness_failure_dump.py`` (M.4.1.f).

Pure-data tests — no live DB, no QS account, no Playwright. The only
thing exercised in the live harness path is the fixture wrapper that
calls ``dump_failure_manifest`` on test failure (covered by the
harness smoke tests under QS_GEN_E2E=1).

Coverage targets:
1. Filename shape: ``<instance>_<test_id_safe>_<ts>.txt`` lands in
   the supplied directory; pytest's ``::`` and ``[`` / ``]`` in the
   test id are filesystem-safed.
2. Section presence: every section the human-side triage needs
   (Test header, Seed Hash, Planted Manifest JSON, Deployed
   Dashboards, Embed URLs, Matview Row Counts, Exception text)
   appears in the output.
3. Graceful degradation: missing dashboard_ids / embed_urls /
   db_conn / exception_text don't crash — the section just shows
   ``<not available>`` (or ``<DB connection not available>``).
4. DB query path: a fake psycopg2-shaped connection is exercised
   against ``_TRIAGE_DB_OBJECTS`` so the SELECT COUNT(*) loop hits
   every prefixed table; missing / failing queries are formatted
   inline (``<missing>`` / ``<error: ...>``) rather than aborting
   the dump.
5. Decimal coercion: planted_manifest values that contain
   ``decimal.Decimal`` (typical for seed amounts) round-trip through
   the JSON serializer without crashing.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# Add tests/e2e to import path so the test can pull in the helper
# module directly without adding it to the package install.
sys.path.insert(0, str(Path(__file__).parent / "e2e"))
from _harness_failure_dump import (  # noqa: E402
    _TRIAGE_DB_OBJECTS,
    _decimal_safe,
    dump_failure_manifest,
)

from quicksight_gen.common.l2 import load_instance


_SPEC_YAML = Path(__file__).parent / "l2" / "spec_example.yaml"


def _instance():
    """Real L2Instance for tests — uses the spec_example fixture so
    seed_hash is non-None and instance is a real Identifier."""
    return load_instance(_SPEC_YAML)


def _planted_manifest() -> dict[str, list[dict[str, Any]]]:
    """Synthetic planted_manifest in the build_planted_manifest shape.

    Includes a Decimal so the JSON serializer's _decimal_safe path
    is exercised.
    """
    return {
        "drift_plants": [
            {
                "account_id": "cust-001",
                "balance_date": date(2030, 1, 1),
                "magnitude": Decimal("250.00"),
            },
        ],
        "rail_firing_plants": [
            {"rail_name": "CustomerCashDeposit", "days_ago": 3},
        ],
        # Empty kinds still appear — manifest builder always returns
        # the full key set even when the picker planted nothing.
        "limit_breach_plants": [],
    }


# ---------------------------------------------------------------------------
# 1. Filename shape
# ---------------------------------------------------------------------------


def test_filename_carries_instance_and_safe_test_id(tmp_path: Path) -> None:
    inst = _instance()
    out_path = dump_failure_manifest(
        tmp_path,
        test_id="tests/e2e/test_x.py::test_y[spec_example]",
        instance=inst,
        planted_manifest={},
    )
    assert out_path.parent == tmp_path
    name = out_path.name
    # Instance leads.
    assert name.startswith(f"{inst.instance}_")
    # `::` and `[` / `]` got rewritten so the path stays portable.
    assert "::" not in name
    assert "[" not in name
    assert "]" not in name
    assert name.endswith(".txt")


def test_failure_dir_created_on_demand(tmp_path: Path) -> None:
    """Sub-directory under tmp_path is created if it doesn't yet exist."""
    nested = tmp_path / "deep" / "nested" / "failures"
    assert not nested.exists()
    out_path = dump_failure_manifest(
        nested,
        test_id="t",
        instance=_instance(),
        planted_manifest={},
    )
    assert nested.is_dir()
    assert out_path.parent == nested


# ---------------------------------------------------------------------------
# 2. Section presence
# ---------------------------------------------------------------------------


def test_all_required_sections_present(tmp_path: Path) -> None:
    out_path = dump_failure_manifest(
        tmp_path,
        test_id="t1",
        instance=_instance(),
        planted_manifest=_planted_manifest(),
        dashboard_ids={"l1-dashboard": "qs-gen-spec_example-l1-dashboard"},
        embed_urls={"l1-dashboard": "https://example.amazonaws.com/embed/abc"},
        db_conn=None,
        exception_text="AssertionError: Drift sheet missing account cust-001",
    )
    text = out_path.read_text()
    for header in (
        "Test",
        "Seed Hash (YAML)",
        "Planted Manifest",
        "Deployed Dashboards",
        "Embed URLs (single-use)",
        "Matview Row Counts",
        "Exception",
    ):
        assert header in text, f"section {header!r} missing from dump"


def test_seed_hash_section_carries_yaml_hash(tmp_path: Path) -> None:
    """P.5.b — seed_hash is now a per-dialect dict; the dump renders one
    line per (dialect, hash) entry. Every locked hash must appear."""
    inst = _instance()
    out_path = dump_failure_manifest(
        tmp_path, test_id="t", instance=inst, planted_manifest={},
    )
    text = out_path.read_text()
    assert inst.seed_hash is not None
    for dialect, h in inst.seed_hash.items():
        assert h in text, f"{dialect} hash missing from dump: {h}"


def test_planted_manifest_round_trips_as_json(tmp_path: Path) -> None:
    """The Decimal in the manifest must serialize as a string (no
    ``Object of type Decimal is not JSON serializable`` blowup)."""
    out_path = dump_failure_manifest(
        tmp_path, test_id="t", instance=_instance(),
        planted_manifest=_planted_manifest(),
    )
    text = out_path.read_text()
    # The Decimal value should appear as-is (str-coerced).
    assert "250.00" in text
    # And the kind keys.
    assert "drift_plants" in text
    assert "rail_firing_plants" in text


def test_exception_section_carries_full_text(tmp_path: Path) -> None:
    msg = "AssertionError: Sheet 'Drift' missing row for account cust-001"
    out_path = dump_failure_manifest(
        tmp_path, test_id="t", instance=_instance(),
        planted_manifest={}, exception_text=msg,
    )
    assert msg in out_path.read_text()


# ---------------------------------------------------------------------------
# 3. Graceful degradation when optional inputs are None
# ---------------------------------------------------------------------------


def test_missing_optionals_do_not_crash(tmp_path: Path) -> None:
    """All four optional sections (dashboard_ids, embed_urls, db_conn,
    exception_text) can be absent without raising — the dump just
    prints sentinel placeholders."""
    out_path = dump_failure_manifest(
        tmp_path, test_id="t", instance=_instance(),
        planted_manifest={},
    )
    text = out_path.read_text()
    assert "<not available>" in text  # dashboard_ids + embed_urls
    assert "<DB connection not available>" in text
    assert "<not captured>" in text  # exception_text


# ---------------------------------------------------------------------------
# 4. DB query path
# ---------------------------------------------------------------------------


class _FakeCursor:
    """psycopg2-cursor-shaped: ``with conn.cursor() as cur`` + execute
    + fetchone. Returns counts from ``responses[<sql>]`` if matched,
    raises if the SQL is in ``raises``."""

    def __init__(
        self,
        responses: dict[str, int],
        raises: dict[str, type[Exception]] | None = None,
    ) -> None:
        self.responses = responses
        self.raises = raises or {}
        self.executed: list[str] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.executed.append(sql)
        if sql in self.raises:
            raise self.raises[sql]("simulated error")

    def fetchone(self) -> tuple[int]:
        # Last-executed SQL drives the response.
        last = self.executed[-1]
        return (self.responses.get(last, 0),)


class _FakeConn:
    """psycopg2-connection-shaped: ``cursor()`` returns a cursor;
    ``rollback()`` is callable. Tracks rollback calls."""

    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.rollbacks = 0

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def rollback(self) -> None:
        self.rollbacks += 1


def test_db_counts_render_for_every_triage_object(tmp_path: Path) -> None:
    """Every name in ``_TRIAGE_DB_OBJECTS`` gets one ``SELECT COUNT(*)``
    and a row in the dump's matview-counts section."""
    prefix = "spec_example"
    responses = {
        f"SELECT COUNT(*) FROM {prefix}_{obj}": (i + 1) * 10
        for i, obj in enumerate(_TRIAGE_DB_OBJECTS)
    }
    cur = _FakeCursor(responses)
    conn = _FakeConn(cur)

    out_path = dump_failure_manifest(
        tmp_path, test_id="t", instance=_instance(),
        planted_manifest={}, db_conn=conn,
    )
    text = out_path.read_text()
    # Each triage object name appears as a row.
    for obj in _TRIAGE_DB_OBJECTS:
        assert obj in text, f"triage object {obj} missing from dump"
    # And every SELECT was issued.
    assert len(cur.executed) == len(_TRIAGE_DB_OBJECTS)
    # No rollbacks because nothing failed.
    assert conn.rollbacks == 0


def test_db_query_failure_renders_inline_and_rolls_back(
    tmp_path: Path,
) -> None:
    """A failing SELECT is logged as ``<error: ...>`` and the txn
    gets rolled back so subsequent objects still get queried."""
    prefix = "spec_example"
    failing_obj = _TRIAGE_DB_OBJECTS[2]  # current_transactions
    failing_sql = f"SELECT COUNT(*) FROM {prefix}_{failing_obj}"
    responses = {
        f"SELECT COUNT(*) FROM {prefix}_{obj}": 1
        for obj in _TRIAGE_DB_OBJECTS
        if obj != failing_obj
    }
    raises = {failing_sql: RuntimeError}
    cur = _FakeCursor(responses, raises=raises)
    conn = _FakeConn(cur)

    out_path = dump_failure_manifest(
        tmp_path, test_id="t", instance=_instance(),
        planted_manifest={}, db_conn=conn,
    )
    text = out_path.read_text()
    # Failing object renders the error tag.
    assert re.search(rf"{re.escape(failing_obj)}\s*:\s*<error:", text)
    # Subsequent objects still got queried (loop didn't abort).
    assert len(cur.executed) == len(_TRIAGE_DB_OBJECTS)
    # Rollback fired exactly once (for the one failing query).
    assert conn.rollbacks == 1


def test_kv_section_handles_empty_dict_gracefully(tmp_path: Path) -> None:
    """Passing an empty dashboard_ids dict (rather than None) renders
    ``<not available>`` rather than crashing on max() of an empty seq."""
    out_path = dump_failure_manifest(
        tmp_path, test_id="t", instance=_instance(),
        planted_manifest={},
        dashboard_ids={},  # empty dict, not None
        embed_urls={},
    )
    text = out_path.read_text()
    # Empty dict falls through to the {"<not available>": ""} placeholder
    # via the `or` short-circuit.
    assert "<not available>" in text


# ---------------------------------------------------------------------------
# 5. Decimal coercion helper
# ---------------------------------------------------------------------------


def test_decimal_safe_handles_nested_structures() -> None:
    """``_decimal_safe`` recurses into dicts and lists and leaves
    non-Decimal types alone."""
    result = _decimal_safe({
        "amount": Decimal("100.50"),
        "nested": {"more": Decimal("0.01")},
        "list": [Decimal("1"), "str", 42, None],
        "untouched": "hello",
    })
    assert result == {
        "amount": "100.50",
        "nested": {"more": "0.01"},
        "list": ["1", "str", 42, None],
        "untouched": "hello",
    }


def test_decimal_safe_passes_through_non_collections() -> None:
    assert _decimal_safe("plain") == "plain"
    assert _decimal_safe(42) == 42
    assert _decimal_safe(None) is None
    assert _decimal_safe(Decimal("3.14")) == "3.14"
