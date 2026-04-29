"""Unit tests for ``tests/e2e/_harness_l2ft_assertions.py``'s pure-data
dispatch + constants (M.4.1.e).

The Playwright assertion bodies need a live browser + deployed
dashboard, so they integration-test only via the harness smoke test.
This file covers what's testable without a browser:

1. ``L2FT_SHEET_FOR_PLANT_KIND`` — dispatch from L2-side plant kind →
   L2 Flow Tracing sheet name. Adding a new L2 plant kind to
   ScenarioPlant needs a corresponding entry; this test catches the
   drift if someone forgets.

2. ``L2_EXCEPTION_CHECK_TYPES`` — pinned constant of the 6 check_type
   discriminator labels. Drift catches: a SQL-side rename of a CAST
   literal in ``build_unified_l2_exceptions_dataset`` would break
   the assertion silently if this set isn't updated.

3. Cross-check with the L1 dispatch table (M.4.1.d) — the two
   modules' plant-kind partitions must be disjoint (no plant kind
   is both an L1 and L2 surface).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add tests/e2e to import path so the test can pull in the helper
# module directly without adding it to the package install.
sys.path.insert(0, str(Path(__file__).parent / "e2e"))
from _harness_l1_assertions import (  # noqa: E402
    L1_SHEET_FOR_PLANT_KIND,
)
from _harness_l2ft_assertions import (  # noqa: E402
    L2_EXCEPTION_CHECK_TYPES,
    L2FT_SHEET_FOR_PLANT_KIND,
)


# ---------------------------------------------------------------------------
# Dispatch table sanity
# ---------------------------------------------------------------------------


def test_l2ft_sheet_dispatch_covers_l2_plant_kinds() -> None:
    """Both L2-side plant kinds (rail firings + TT plants) are
    covered. L1 kinds aren't here — those are M.4.1.d's surface."""
    expected_l2_kinds = {
        "rail_firing_plants",
        "transfer_template_plants",
    }
    assert set(L2FT_SHEET_FOR_PLANT_KIND.keys()) == expected_l2_kinds


def test_l2ft_sheet_names_are_unique() -> None:
    """No two L2 plant kinds dispatch to the same sheet (would
    indicate a copy-paste in the table)."""
    sheet_names = list(L2FT_SHEET_FOR_PLANT_KIND.values())
    assert len(sheet_names) == len(set(sheet_names))


def test_l1_and_l2ft_dispatch_partitions_are_disjoint() -> None:
    """A plant kind belongs to exactly one of the two assertion
    modules — not both. Catches drift if a kind moves between
    L1/L2FT surfaces (e.g. a refactor adds rail_firing_plants to
    the L1 dashboard) without updating both dispatch tables.
    """
    l1_kinds = set(L1_SHEET_FOR_PLANT_KIND.keys())
    l2_kinds = set(L2FT_SHEET_FOR_PLANT_KIND.keys())
    assert l1_kinds.isdisjoint(l2_kinds), (
        f"plant kinds appear in both L1 + L2FT dispatch tables: "
        f"{sorted(l1_kinds & l2_kinds)!r}"
    )


# ---------------------------------------------------------------------------
# L2 Exception check_type pinning
# ---------------------------------------------------------------------------


def test_check_types_match_unified_exceptions_dataset_labels() -> None:
    """The 6 labels in L2_EXCEPTION_CHECK_TYPES must match the CAST
    literals in ``build_unified_l2_exceptions_dataset``'s UNION ALL
    branches. A SQL-side rename without a matching constant update
    would break the L2 Exceptions sanity assertion silently.

    Reads the actual dataset SQL via the builder + grep to extract
    the literals; compares to the pinned set. If the SQL gets
    refactored (e.g., labels go into a CTE instead of inline CAST),
    this test surfaces the change and the constant gets re-grepped
    or moved into a shared definition module.
    """
    import re
    from datetime import date  # noqa: F401 — needed by the build call below

    from quicksight_gen.common.config import Config
    from quicksight_gen.common.l2 import load_instance
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_unified_l2_exceptions_dataset,
    )

    cfg = Config(
        aws_account_id="111122223333",
        aws_region="us-west-2",
        datasource_arn=(
            "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
        ),
        l2_instance_prefix="check_type_test",
    )
    instance = load_instance(
        Path(__file__).parent / "l2" / "spec_example.yaml",
    )
    ds = build_unified_l2_exceptions_dataset(cfg, instance)
    sql = ds.PhysicalTableMap[
        "l2ft-unified-exceptions"
    ].CustomSql.SqlQuery

    # Grep for `CAST('<label>' AS VARCHAR(50)) AS check_type` and
    # also bare `CAST('<label>' AS VARCHAR(50))` in subsequent UNION
    # ALL branches.
    found = set(re.findall(
        r"CAST\('([^']+)' AS VARCHAR\(50\)\)", sql,
    ))
    assert found == L2_EXCEPTION_CHECK_TYPES, (
        f"L2 Exception check_type literals drifted from constant:\n"
        f"  in dataset SQL: {sorted(found)!r}\n"
        f"  in constant:    {sorted(L2_EXCEPTION_CHECK_TYPES)!r}\n"
        f"Update L2_EXCEPTION_CHECK_TYPES (or rename in the dataset)."
    )
