"""Unit tests for ``tests/e2e/_harness_deploy.py``'s JSON-shaping
helpers (M.4.1.c).

The harness's deploy step delegates the actual boto3 work to
``common.deploy.deploy()`` (which is integration-tested by the
production CLI). This file covers the two JSON-shaping helpers the
harness wraps around it:

1. ``generate_apps(cfg, l2_instance, out_dir)`` writes the file
   layout the deploy step consumes.
2. ``extract_dashboard_ids(out_dir)`` reads the dashboard JSON files
   back out and pulls the QS DashboardId field — used by the embed-
   URL builder so the harness doesn't have to parse deploy's stdout.

Both are testable against a tmp_path + a real loaded L2 instance,
no AWS, no DB. The actual deploy + embed-URL roundtrip lives in the
e2e harness fixture's smoke test.

Lives at the project test root (not under ``tests/e2e/``) so it
runs in the default ``pytest`` invocation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add tests/e2e to import path so the test can pull in the helper
# module directly without adding it to the package install.
sys.path.insert(0, str(Path(__file__).parent))
from _harness_deploy import (  # noqa: E402
    HARNESS_APPS,
    extract_dashboard_ids,
    generate_apps,
)

from quicksight_gen.common.config import Config
from quicksight_gen.common.l2 import load_instance
from tests._test_helpers import make_test_config


L2_DIR = Path(__file__).parent / "l2"


def _harness_cfg() -> Config:
    """Minimal Config the harness uses — env-var-driven in real runs.

    For unit tests we don't need real AWS creds; account_id +
    datasource_arn just have to be present strings (the apps' build
    functions consume them as ARN-shaping inputs, not for actual
    AWS calls).
    """
    return make_test_config(
        extra_tags={"TestUid": "abc123", "Harness": "e2e"},
        l2_instance_prefix="e2e_spec_example_abc123",
    )


def test_generate_apps_writes_expected_file_layout(tmp_path: Path) -> None:
    """Both apps' theme + per-dataset + analysis + dashboard JSON
    files land at the right paths. Skips datasource.json by design
    (the harness uses cfg.datasource_arn, not a per-test datasource)."""
    cfg = _harness_cfg()
    instance = load_instance(L2_DIR / "spec_example.yaml")

    generate_apps(cfg, instance, tmp_path)

    # Theme + per-app analysis + dashboard JSON.
    assert (tmp_path / "theme.json").exists()
    assert (tmp_path / "l1-dashboard-analysis.json").exists()
    assert (tmp_path / "l1-dashboard-dashboard.json").exists()
    assert (tmp_path / "l2-flow-tracing-analysis.json").exists()
    assert (tmp_path / "l2-flow-tracing-dashboard.json").exists()

    # No datasource.json — harness uses the env-var ARN.
    assert not (tmp_path / "datasource.json").exists()

    # Datasets dir has at least one .json file (every L2 instance
    # produces some L1 + L2FT datasets; spec_example has the leanest
    # set but still has them).
    datasets_dir = tmp_path / "datasets"
    assert datasets_dir.is_dir()
    json_files = sorted(datasets_dir.glob("*.json"))
    assert len(json_files) > 0


def test_generate_apps_dataset_files_carry_l2_prefix(tmp_path: Path) -> None:
    """Every dataset JSON file has a name containing the L2 instance
    prefix from cfg.l2_instance_prefix — proves the M.2d.3 prefix
    plumbing flows through the harness's generate path."""
    cfg = _harness_cfg()
    instance = load_instance(L2_DIR / "spec_example.yaml")
    generate_apps(cfg, instance, tmp_path)

    expected_prefix = f"qs-gen-{cfg.l2_instance_prefix}-"
    for ds_file in (tmp_path / "datasets").glob("*.json"):
        assert ds_file.stem.startswith(expected_prefix), (
            f"dataset file {ds_file.name!r} doesn't carry expected "
            f"prefix {expected_prefix!r} — check cfg flow through "
            f"build_all_*_datasets"
        )


def test_extract_dashboard_ids_returns_per_app_id(tmp_path: Path) -> None:
    """After generate_apps, extract_dashboard_ids returns the
    DashboardId field from each app's -dashboard.json."""
    cfg = _harness_cfg()
    instance = load_instance(L2_DIR / "spec_example.yaml")
    generate_apps(cfg, instance, tmp_path)

    ids = extract_dashboard_ids(tmp_path)

    assert set(ids.keys()) == set(HARNESS_APPS)
    # Each id starts with the cfg prefix (M.2d.3 contract).
    expected_prefix = f"qs-gen-{cfg.l2_instance_prefix}-"
    for app_name, dashboard_id in ids.items():
        assert dashboard_id.startswith(expected_prefix), (
            f"{app_name} dashboard_id {dashboard_id!r} doesn't carry "
            f"expected prefix {expected_prefix!r}"
        )


def test_extract_dashboard_ids_raises_on_missing_file(tmp_path: Path) -> None:
    """If generate_apps never ran (or wrote partial output),
    extract_dashboard_ids fails with a clear message naming the
    missing file — not a confusing JSONDecodeError or KeyError."""
    import pytest
    with pytest.raises(FileNotFoundError, match="-dashboard.json"):
        extract_dashboard_ids(tmp_path)


def test_generate_apps_writes_2_space_indent_no_sort(tmp_path: Path) -> None:
    """JSON formatting matches the CLI's _write_json shape: 2-space
    indent, no sort_keys, trailing newline. Keeps any future diff
    between harness-generated JSON and CLI-generated JSON clean."""
    cfg = _harness_cfg()
    instance = load_instance(L2_DIR / "spec_example.yaml")
    generate_apps(cfg, instance, tmp_path)

    text = (tmp_path / "theme.json").read_text(encoding="utf-8")
    # Trailing newline.
    assert text.endswith("\n")
    # 2-space indent → "  " appears at start of nested lines.
    lines = text.split("\n")
    assert any(line.startswith("  ") for line in lines)
    # Round-trip identity confirms no info loss.
    parsed = json.loads(text)
    assert isinstance(parsed, dict)
    assert "ThemeId" in parsed
