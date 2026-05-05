"""Unit tests for ``common/etl_examples.py`` (X.1.h).

The handbook's ``etl.md`` "exemplary helper" section promises the
``quicksight-gen data etl-example`` CLI emits canonical INSERT
patterns covering every base-table shape. Pre-X.1.h the helper
returned a single placeholder line — these tests guard the rewrite,
asserting every promised pattern is in the output and carries the
documented ``-- WHY:`` / ``-- Consumed by:`` headers.
"""

from __future__ import annotations

import re

import pytest

from quicksight_gen.common.etl_examples import generate_etl_examples_sql


@pytest.fixture(scope="module")
def sql() -> str:
    return generate_etl_examples_sql()


def test_output_is_substantive(sql: str) -> None:
    """The pre-X.1.h placeholder was a single line — guard against
    regression to that shape."""
    assert len(sql) > 5000, (
        f"Output is suspiciously small ({len(sql)} chars) — did the "
        f"helper regress to a placeholder?"
    )
    assert sql.count("\n") > 100, (
        f"Output has only {sql.count(chr(10))} lines — expected many "
        f"more across the documented pattern set."
    )


def test_every_pattern_block_has_why_header(sql: str) -> None:
    """Every Pattern N block carries a ``-- WHY:`` header naming the
    business invariant the pattern protects (per the handbook
    contract)."""
    pattern_count = len(re.findall(r"^-- Pattern \d+", sql, re.MULTILINE))
    why_count = sql.count("-- WHY:")
    assert pattern_count >= 8, (
        f"Expected ≥ 8 Pattern blocks, got {pattern_count}"
    )
    assert why_count == pattern_count, (
        f"Pattern block count ({pattern_count}) ≠ -- WHY: count "
        f"({why_count}); every pattern MUST carry a WHY header per "
        f"the handbook contract."
    )


def test_every_pattern_block_has_consumed_by_header(sql: str) -> None:
    """Every Pattern N block carries a ``-- Consumed by:`` header
    naming the dashboard view that reads the resulting rows."""
    pattern_count = len(re.findall(r"^-- Pattern \d+", sql, re.MULTILINE))
    consumed_count = sql.count("-- Consumed by:")
    assert consumed_count == pattern_count, (
        f"Pattern block count ({pattern_count}) ≠ -- Consumed by: "
        f"count ({consumed_count}); every pattern MUST carry a "
        f"Consumed-by header per the handbook contract."
    )


def test_covers_both_base_tables(sql: str) -> None:
    """The handbook claims the patterns cover every base-table shape;
    both base tables MUST appear in the output."""
    assert "INSERT INTO <prefix>_transactions" in sql, (
        "<prefix>_transactions INSERT pattern missing"
    )
    assert "INSERT INTO <prefix>_daily_balances" in sql, (
        "<prefix>_daily_balances INSERT pattern missing"
    )


def test_uses_example_sentinel_ids(sql: str) -> None:
    """Per the contract — sentinel IDs carry the ``-EXAMPLE``
    suffix so integrators don't accidentally clobber real seeded
    rows when running the patterns verbatim."""
    assert "tx-EXAMPLE-" in sql, "transaction sentinel IDs missing"
    assert "tr-EXAMPLE-" in sql, "transfer sentinel IDs missing"
    assert "acct-EXAMPLE-" in sql, "account sentinel IDs missing"


def test_covers_supersession_lifecycle_and_correction(sql: str) -> None:
    """Both supersession kinds (Lifecycle = Pending → Posted advance,
    TechnicalCorrection = back-office rewrite) MUST be exemplified —
    they're the two L1 Supersession Audit buckets."""
    assert "'Lifecycle'" in sql, (
        "Lifecycle supersedes example missing — Pending → Posted "
        "advancement is the most common supersession class and "
        "drives the L1 Pending Aging sheet."
    )
    assert "'TechnicalCorrection'" in sql, (
        "TechnicalCorrection supersedes example missing — back-office "
        "rewrites need a documented pattern; the L1 Supersession "
        "Audit sheet's TechnicalCorrection bucket reads these rows."
    )


def test_covers_force_posted_origin(sql: str) -> None:
    """The Fed-statement / processor-feed ingest pattern needs
    ``origin='ExternalForcePosted'`` — leaving this out collapses
    the L1 Drift sheet's bank-vs-force breakdown."""
    assert "'ExternalForcePosted'" in sql, (
        "Force-posted origin example missing — Fed-statement ingest "
        "pattern is the canonical use case and the L1 Drift sheet "
        "splits on this."
    )


def test_covers_chained_transfer(sql: str) -> None:
    """transfer_parent_id is what makes the Investigation Money Trail
    + Account Network sheets walkable; missing it from the examples
    silently teaches operators not to populate it."""
    assert "transfer_parent_id" in sql, (
        "Chained-transfer pattern missing — Investigation Money "
        "Trail's recursive walk depends on transfer_parent_id."
    )


def test_covers_bundled_transfer(sql: str) -> None:
    """The L1 Stuck Unbundled view depends on the bundle_id column;
    operators who don't know to populate it get false stuck-unbundled
    fires."""
    assert "bundle_id" in sql, (
        "Bundled-transfer pattern missing — L1 Stuck Unbundled "
        "depends on bundle_id."
    )


def test_covers_metadata_extension(sql: str) -> None:
    """The metadata JSON extension contract is what makes per-rail /
    per-app columns possible without schema migrations; the examples
    MUST show one to teach the open-set extension shape."""
    assert "originating_branch" in sql or "fraud_score" in sql, (
        "Metadata-extension pattern missing — operators won't know "
        "to populate the open-set extras container without an "
        "example."
    )


def test_output_is_deterministic() -> None:
    """The same call MUST produce the same output (no random IDs, no
    clock-dependent timestamps) so the helper is safe to wire into
    CI / docs publishing pipelines without churn."""
    a = generate_etl_examples_sql()
    b = generate_etl_examples_sql()
    assert a == b, "generate_etl_examples_sql output is non-deterministic"
