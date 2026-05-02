"""Tests for the theme preset system.

Per N.4.l, the lookup-by-name registry was dropped — `DEFAULT_PRESET`
is the single fallback preset (used when an L2 instance omits its
inline ``theme:`` block). All other brand palettes live inline on
each L2 YAML's ``theme:`` block.
"""

import json

import pytest

from quicksight_gen.common.config import Config
from quicksight_gen.common.theme import (
    DEFAULT_PRESET,
    ThemePreset,
    build_theme,
)


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
        theme = build_theme(cfg, DEFAULT_PRESET)
        assert theme is not None
        data = theme.to_aws_json()
        # Round-trip through JSON to catch serialization issues
        json.loads(json.dumps(data))
        assert data["Name"] == "QuickSight Gen Theme"

    def test_silent_fallback_returns_none_when_no_theme(self):
        """N.4.k silent-fallback: ``build_theme(cfg, None)`` returns
        None so the CLI skips theme.json emission and AWS QuickSight
        CLASSIC takes over at deploy."""
        cfg = Config(
            aws_account_id="111122223333",
            aws_region="us-west-2",
            datasource_arn="arn:aws:quicksight:us-west-2:111122223333:datasource/ds",
        )
        assert build_theme(cfg, None) is None
