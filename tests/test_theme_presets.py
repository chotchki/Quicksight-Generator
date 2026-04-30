"""Tests for the theme preset system.

Per N.1.g, the registry holds only the ``default`` preset; per-instance
brand palettes live inline on the L2 YAML's ``theme:`` block. The
sasquatch-bank / sasquatch-bank-investigation entries dropped here.
"""

import json

import pytest

from quicksight_gen.common.config import Config
from quicksight_gen.common.theme import (
    DEFAULT_PRESET,
    PRESETS,
    ThemePreset,
    build_theme,
    get_preset,
)


# ---------------------------------------------------------------------------
# Preset registry
# ---------------------------------------------------------------------------

class TestPresetRegistry:
    def test_default_preset_exists(self):
        assert "default" in PRESETS

    def test_registry_has_only_default_post_n1g(self):
        # The persona-flavored presets used to live here; per N.1 they
        # moved to inline ``theme:`` blocks on L2 YAMLs. The registry
        # is now a single-entry fallback for L2 instances that omit
        # the theme block.
        assert set(PRESETS) == {"default"}

    def test_get_preset_returns_correct_type(self):
        assert isinstance(get_preset("default"), ThemePreset)

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown theme preset 'nope'"):
            get_preset("nope")

    def test_error_lists_available_presets(self):
        with pytest.raises(ValueError, match="default"):
            get_preset("bad")


# ---------------------------------------------------------------------------
# Default preset spot-checks
# ---------------------------------------------------------------------------

class TestDefaultPreset:
    def test_name(self):
        assert DEFAULT_PRESET.theme_name == "QuickSight Gen Theme"

    def test_no_analysis_prefix(self):
        assert DEFAULT_PRESET.analysis_name_prefix is None

    def test_accent_is_blue(self):
        assert DEFAULT_PRESET.accent == "#2E5090"

    def test_eight_data_colors(self):
        assert len(DEFAULT_PRESET.data_colors) == 8

    def test_serializes_to_valid_theme(self):
        cfg = Config(
            aws_account_id="111122223333",
            aws_region="us-west-2",
            datasource_arn="arn:aws:quicksight:us-west-2:111122223333:datasource/ds",
        )
        theme = build_theme(cfg)
        data = theme.to_aws_json()
        # Round-trip through JSON to catch serialization issues
        json.loads(json.dumps(data))
        assert data["Name"] == "QuickSight Gen Theme"
