"""Tests for ``emit_baseline_seed`` (Phase R).

R.2.a — skeleton-level tests. Pin the public entry point's signature +
the deterministic helpers (RNG sub-stream layout, business-day calendar)
so R.2.b–e can fill in the body without accidentally regressing the API.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from quicksight_gen.common.l2.loader import load_instance
from quicksight_gen.common.l2.seed import (
    _BASELINE_BASE_SEED,
    _business_days_in_window,
    _seed_for_rail,
    emit_baseline_seed,
)


_SPEC_EXAMPLE = Path(__file__).parent / "l2" / "spec_example.yaml"
_SASQUATCH_PR = Path(__file__).parent / "l2" / "sasquatch_pr.yaml"
_ANCHOR = date(2026, 4, 30)


class TestSeedForRail:
    """The per-Rail RNG sub-stream layout (R.1.f §4)."""

    def test_seed_for_rail_is_deterministic(self) -> None:
        assert _seed_for_rail("CustomerInboundACH") == _seed_for_rail(
            "CustomerInboundACH",
        )

    def test_seed_for_rail_isolates_rails(self) -> None:
        a = _seed_for_rail("CustomerInboundACH")
        b = _seed_for_rail("CustomerOutboundACH")
        assert a != b, (
            "Per-Rail RNG seeds must differ so renaming one Rail can't "
            "perturb another's emitted bytes."
        )

    def test_seed_for_rail_xors_against_base(self) -> None:
        # Empty-name edge case lands on BASE_SEED itself (crc32("") = 0).
        assert _seed_for_rail("") == _BASELINE_BASE_SEED


class TestBusinessDaysCalendar:
    """The 90-day business-day calendar (R.1.f §3)."""

    def test_window_excludes_weekends(self) -> None:
        days = _business_days_in_window(_ANCHOR, 90)
        assert all(d.weekday() < 5 for d in days), (
            "Business-day calendar must drop Sat/Sun."
        )

    def test_window_is_sorted_ascending(self) -> None:
        days = _business_days_in_window(_ANCHOR, 90)
        assert days == sorted(days)

    def test_window_anchor_is_inclusive(self) -> None:
        # 2026-04-30 is a Thursday — should be in the window.
        days = _business_days_in_window(_ANCHOR, 90)
        assert _ANCHOR in days

    def test_window_count_in_expected_range(self) -> None:
        # 90 days spans ~13 weeks → ~65 weekdays. Holidays-package may
        # shave 2-4 more if installed; either way, well above 50.
        days = _business_days_in_window(_ANCHOR, 90)
        assert 50 <= len(days) <= 66


class TestEmitBaselineSeedSkeleton:
    """R.2.a: the skeleton emits a valid header + empty INSERT bodies."""

    @pytest.mark.parametrize("yaml_path", [_SPEC_EXAMPLE, _SASQUATCH_PR])
    def test_emit_returns_string(self, yaml_path: Path) -> None:
        instance = load_instance(yaml_path)
        sql = emit_baseline_seed(instance, anchor=_ANCHOR)
        assert isinstance(sql, str)
        assert len(sql) > 0

    def test_header_carries_instance_prefix(self) -> None:
        instance = load_instance(_SPEC_EXAMPLE)
        sql = emit_baseline_seed(instance, anchor=_ANCHOR)
        assert "L2 instance: spec_example" in sql

    def test_header_carries_anchor(self) -> None:
        instance = load_instance(_SPEC_EXAMPLE)
        sql = emit_baseline_seed(instance, anchor=_ANCHOR)
        assert _ANCHOR.isoformat() in sql

    def test_header_reports_rail_and_chain_counts(self) -> None:
        instance = load_instance(_SASQUATCH_PR)
        sql = emit_baseline_seed(instance, anchor=_ANCHOR)
        assert f"Rails declared: {len(instance.rails)}" in sql
        assert f"Chains declared: {len(instance.chains)}" in sql

    def test_window_days_default_is_90(self) -> None:
        instance = load_instance(_SPEC_EXAMPLE)
        sql = emit_baseline_seed(instance, anchor=_ANCHOR)
        assert "90-day rolling window" in sql

    def test_window_days_override(self) -> None:
        instance = load_instance(_SPEC_EXAMPLE)
        sql = emit_baseline_seed(instance, anchor=_ANCHOR, window_days=30)
        assert "30-day rolling window" in sql

    def test_skeleton_emits_stub_markers(self) -> None:
        # R.2.a: the bodies are stubbed. R.2.b/e fills replace these
        # markers with real INSERT statements; the test will fail loudly
        # at that point and we update it.
        instance = load_instance(_SPEC_EXAMPLE)
        sql = emit_baseline_seed(instance, anchor=_ANCHOR)
        assert "no baseline transactions yet — R.2.b in progress" in sql
        assert "no baseline daily_balances yet — R.2.e in progress" in sql

    def test_emit_is_deterministic_for_fixed_anchor(self) -> None:
        instance = load_instance(_SASQUATCH_PR)
        a = emit_baseline_seed(instance, anchor=_ANCHOR)
        b = emit_baseline_seed(instance, anchor=_ANCHOR)
        assert a == b
