"""QuickSight theme definition with selectable presets.

The ``default`` preset is a neutral blue/grey professional palette used for
production dashboards. Demo presets (e.g. ``sasquatch-bank``) brand the output
for demo scenarios and prefix the analysis name with ``Demo —``.
"""

from __future__ import annotations

from dataclasses import dataclass

from quicksight_gen.common.config import Config
from quicksight_gen.common.models import (
    DataColorPalette,
    FontFamily,
    Gutter,
    Margin,
    ResourcePermission,
    SheetStyle,
    Theme,
    ThemeConfiguration,
    Tile,
    TileBorder,
    TileLayout,
    Typography,
    UIColorPalette,
)


# ---------------------------------------------------------------------------
# Preset dataclass
# ---------------------------------------------------------------------------

@dataclass
class ThemePreset:
    """Everything that varies between theme variants."""

    theme_name: str
    version_description: str
    analysis_name_prefix: str | None  # None → use default analysis names

    # Data colour palette
    data_colors: list[str]
    empty_fill_color: str
    gradient: list[str]  # [light, dark] for min/max

    # UI colour palette
    primary_bg: str
    secondary_bg: str
    primary_fg: str
    secondary_fg: str
    accent: str
    accent_fg: str
    danger: str
    danger_fg: str
    warning: str
    warning_fg: str
    success: str
    success_fg: str
    dimension: str
    dimension_fg: str
    measure: str
    measure_fg: str


# ---------------------------------------------------------------------------
# Default preset — blues and greys
# ---------------------------------------------------------------------------

# Primary blues (dark → light)
_NAVY = "#1B2A4A"
_DARK_BLUE = "#2E5090"
_MEDIUM_BLUE = "#4A7DC7"
_LIGHT_BLUE = "#7BAAF7"
_PALE_BLUE = "#C5DAF7"

# Greys
_CHARCOAL = "#2D2D2D"
_DARK_GREY = "#4A4A4A"
_MEDIUM_GREY = "#8C8C8C"
_LIGHT_GREY = "#D9D9D9"
_OFF_WHITE = "#F5F6FA"
_WHITE = "#FFFFFF"

# Semantic
_SUCCESS_GREEN = "#2E7D32"
_WARNING_AMBER = "#E65100"
_DANGER_RED = "#C62828"

DEFAULT_PRESET = ThemePreset(
    theme_name="QuickSight Gen Theme",
    version_description="Auto-generated dashboard theme",
    analysis_name_prefix=None,
    data_colors=[
        _DARK_BLUE,
        "#E07B39",       # warm orange contrast
        "#3A9E6F",       # teal green
        _MEDIUM_BLUE,
        "#8E5EA2",       # muted purple
        "#E6B422",       # gold
        "#4BC0C0",       # cyan
        _MEDIUM_GREY,    # neutral fallback
    ],
    empty_fill_color=_LIGHT_GREY,
    gradient=[_PALE_BLUE, _DARK_BLUE],
    primary_bg=_WHITE,
    secondary_bg=_OFF_WHITE,
    primary_fg=_CHARCOAL,
    secondary_fg=_DARK_GREY,
    accent=_DARK_BLUE,
    accent_fg=_WHITE,
    danger=_DANGER_RED,
    danger_fg=_WHITE,
    warning=_WARNING_AMBER,
    warning_fg=_WHITE,
    success=_SUCCESS_GREEN,
    success_fg=_WHITE,
    dimension=_MEDIUM_BLUE,
    dimension_fg=_WHITE,
    measure=_NAVY,
    measure_fg=_WHITE,
)


# ---------------------------------------------------------------------------
# Sasquatch National Bank preset — forest greens, earth tones, gold
# ---------------------------------------------------------------------------

# Greens (dark → light)
_DEEP_FOREST = "#1B4332"
_FOREST_GREEN = "#2D6A4F"
_SAGE = "#52796F"
_MOSS = "#74A892"
_PALE_SAGE = "#C5DDD3"

# Earth / accent
_BARK_BROWN = "#5C4033"
_BANK_GOLD = "#C49A2A"
_PARCHMENT = "#FAF6F1"

# Warm greys
_DARK_WARM_GREY = "#3D3D3A"
_MEDIUM_WARM_GREY = "#7A7A72"

SASQUATCH_BANK_PRESET = ThemePreset(
    theme_name="Sasquatch National Bank Theme",
    version_description="Sasquatch National Bank — forest green and gold palette",
    analysis_name_prefix="Demo",
    data_colors=[
        _FOREST_GREEN,
        _BANK_GOLD,
        _BARK_BROWN,
        _SAGE,
        "#B85C38",           # rust
        _MOSS,
        "#6B4C8A",           # plum
        _MEDIUM_WARM_GREY,
    ],
    empty_fill_color="#D6D6CE",
    gradient=[_PALE_SAGE, _DEEP_FOREST],
    primary_bg=_WHITE,
    secondary_bg=_PARCHMENT,
    primary_fg=_DARK_WARM_GREY,
    secondary_fg=_SAGE,
    accent=_FOREST_GREEN,
    accent_fg=_WHITE,
    danger="#B71C1C",
    danger_fg=_WHITE,
    warning="#BF6D0A",
    warning_fg=_WHITE,
    success=_FOREST_GREEN,
    success_fg=_WHITE,
    dimension=_SAGE,
    dimension_fg=_WHITE,
    measure=_DEEP_FOREST,
    measure_fg=_WHITE,
)


# ---------------------------------------------------------------------------
# Preset registry
# ---------------------------------------------------------------------------

PRESETS: dict[str, ThemePreset] = {
    "default": DEFAULT_PRESET,
    "sasquatch-bank": SASQUATCH_BANK_PRESET,
}


def get_preset(name: str) -> ThemePreset:
    """Look up a theme preset by name.

    Raises ``ValueError`` for unknown names.
    """
    if name not in PRESETS:
        available = ", ".join(sorted(PRESETS))
        raise ValueError(
            f"Unknown theme preset '{name}'. Available: {available}"
        )
    return PRESETS[name]


# ---------------------------------------------------------------------------
# Theme builder
# ---------------------------------------------------------------------------

def build_theme(cfg: Config) -> Theme:
    """Build the complete QuickSight Theme resource using the configured preset."""
    preset = get_preset(cfg.theme_preset)
    theme_id = cfg.prefixed("theme")

    permissions = None
    if cfg.principal_arns:
        theme_actions = [
            "quicksight:DescribeTheme",
            "quicksight:DescribeThemeAlias",
            "quicksight:DescribeThemePermissions",
            "quicksight:ListThemeAliases",
            "quicksight:ListThemeVersions",
            "quicksight:UpdateTheme",
            "quicksight:UpdateThemeAlias",
            "quicksight:UpdateThemePermissions",
            "quicksight:DeleteTheme",
            "quicksight:DeleteThemeAlias",
            "quicksight:CreateThemeAlias",
        ]
        permissions = [
            ResourcePermission(Principal=arn, Actions=theme_actions)
            for arn in cfg.principal_arns
        ]

    return Theme(
        AwsAccountId=cfg.aws_account_id,
        ThemeId=theme_id,
        Name=preset.theme_name,
        BaseThemeId="CLASSIC",
        Tags=cfg.tags(),
        Configuration=ThemeConfiguration(
            DataColorPalette=DataColorPalette(
                Colors=preset.data_colors,
                EmptyFillColor=preset.empty_fill_color,
                MinMaxGradient=preset.gradient,
            ),
            UIColorPalette=UIColorPalette(
                PrimaryBackground=preset.primary_bg,
                SecondaryBackground=preset.secondary_bg,
                PrimaryForeground=preset.primary_fg,
                SecondaryForeground=preset.secondary_fg,
                Accent=preset.accent,
                AccentForeground=preset.accent_fg,
                Danger=preset.danger,
                DangerForeground=preset.danger_fg,
                Warning=preset.warning,
                WarningForeground=preset.warning_fg,
                Success=preset.success,
                SuccessForeground=preset.success_fg,
                Dimension=preset.dimension,
                DimensionForeground=preset.dimension_fg,
                Measure=preset.measure,
                MeasureForeground=preset.measure_fg,
            ),
            Sheet=SheetStyle(
                Tile=Tile(
                    Border=TileBorder(Show=True),
                ),
                TileLayout=TileLayout(
                    Gutter=Gutter(Show=True),
                    Margin=Margin(Show=True),
                ),
            ),
            Typography=Typography(
                FontFamilies=[
                    FontFamily(FontFamily="Amazon Ember"),
                    FontFamily(FontFamily="sans-serif"),
                ],
            ),
        ),
        Permissions=permissions,
        VersionDescription=preset.version_description,
    )
