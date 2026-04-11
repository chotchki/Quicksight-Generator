"""Tests for the theme preset system."""

import json

import pytest

from quicksight_gen.config import Config
from quicksight_gen.theme import (
    DEFAULT_PRESET,
    PRESETS,
    SASQUATCH_BANK_PRESET,
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

    def test_sasquatch_bank_preset_exists(self):
        assert "sasquatch-bank" in PRESETS

    def test_get_preset_returns_correct_type(self):
        assert isinstance(get_preset("default"), ThemePreset)
        assert isinstance(get_preset("sasquatch-bank"), ThemePreset)

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
        assert DEFAULT_PRESET.theme_name == "Financial Reporting Theme"

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
        assert data["Name"] == "Financial Reporting Theme"


# ---------------------------------------------------------------------------
# Sasquatch National Bank preset spot-checks
# ---------------------------------------------------------------------------

class TestSasquatchBankPreset:
    def test_name(self):
        assert SASQUATCH_BANK_PRESET.theme_name == "Sasquatch National Bank Theme"

    def test_analysis_prefix(self):
        assert SASQUATCH_BANK_PRESET.analysis_name_prefix == "Sasquatch National Bank"

    def test_accent_is_forest_green(self):
        assert SASQUATCH_BANK_PRESET.accent == "#2D6A4F"

    def test_eight_data_colors(self):
        assert len(SASQUATCH_BANK_PRESET.data_colors) == 8

    def test_colors_differ_from_default(self):
        assert SASQUATCH_BANK_PRESET.data_colors != DEFAULT_PRESET.data_colors
        assert SASQUATCH_BANK_PRESET.accent != DEFAULT_PRESET.accent
        assert SASQUATCH_BANK_PRESET.secondary_bg != DEFAULT_PRESET.secondary_bg

    def test_serializes_to_valid_theme(self):
        cfg = Config(
            aws_account_id="111122223333",
            aws_region="us-west-2",
            datasource_arn="arn:aws:quicksight:us-west-2:111122223333:datasource/ds",
            theme_preset="sasquatch-bank",
        )
        theme = build_theme(cfg)
        data = theme.to_aws_json()
        json.loads(json.dumps(data))
        assert data["Name"] == "Sasquatch National Bank Theme"
        assert "forest green" in data["VersionDescription"].lower()


# ---------------------------------------------------------------------------
# Preset integration with analysis names
# ---------------------------------------------------------------------------

class TestPresetAnalysisNames:
    def _cfg(self, preset: str = "default") -> Config:
        return Config(
            aws_account_id="111122223333",
            aws_region="us-west-2",
            datasource_arn="arn:aws:quicksight:us-west-2:111122223333:datasource/ds",
            theme_preset=preset,
        )

    def test_default_financial_name(self):
        from quicksight_gen.analysis import build_analysis

        a = build_analysis(self._cfg())
        assert a.to_aws_json()["Name"] == "Financial Reporting Analysis"

    def test_default_recon_name(self):
        from quicksight_gen.recon_analysis import build_recon_analysis

        a = build_recon_analysis(self._cfg())
        assert a.to_aws_json()["Name"] == "Reconciliation Analysis"

    def test_sasquatch_financial_name(self):
        from quicksight_gen.analysis import build_analysis

        a = build_analysis(self._cfg("sasquatch-bank"))
        assert a.to_aws_json()["Name"] == "Sasquatch National Bank — Financial Reporting"

    def test_sasquatch_recon_name(self):
        from quicksight_gen.recon_analysis import build_recon_analysis

        a = build_recon_analysis(self._cfg("sasquatch-bank"))
        assert a.to_aws_json()["Name"] == "Sasquatch National Bank — Reconciliation"
