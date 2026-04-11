"""QuickSight theme definition — blues and greys palette.

Designed for financial reporting: high contrast, clean readability,
professional look with blue accents and neutral grey backgrounds.
"""

from __future__ import annotations

from quicksight_gen.config import Config
from quicksight_gen.models import (
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
# Colour constants
# ---------------------------------------------------------------------------

# Primary blues (dark → light)
NAVY = "#1B2A4A"
DARK_BLUE = "#2E5090"
MEDIUM_BLUE = "#4A7DC7"
LIGHT_BLUE = "#7BAAF7"
PALE_BLUE = "#C5DAF7"

# Greys (dark → light)
CHARCOAL = "#2D2D2D"
DARK_GREY = "#4A4A4A"
MEDIUM_GREY = "#8C8C8C"
LIGHT_GREY = "#D9D9D9"
OFF_WHITE = "#F5F6FA"
WHITE = "#FFFFFF"

# Semantic colours
SUCCESS_GREEN = "#2E7D32"
WARNING_AMBER = "#E65100"
DANGER_RED = "#C62828"

# Chart data colours — 8 distinct, ordered for visual separation
DATA_COLOURS = [
    DARK_BLUE,    # primary series
    "#E07B39",    # warm orange contrast
    "#3A9E6F",    # teal green
    MEDIUM_BLUE,  # secondary blue
    "#8E5EA2",    # muted purple
    "#E6B422",    # gold
    "#4BC0C0",    # cyan
    MEDIUM_GREY,  # neutral fallback
]


def build_theme(cfg: Config) -> Theme:
    """Build the complete QuickSight Theme resource."""
    theme_id = cfg.prefixed("theme")

    permissions = None
    if cfg.principal_arn:
        permissions = [
            ResourcePermission(
                Principal=cfg.principal_arn,
                Actions=[
                    "quicksight:DescribeTheme",
                    "quicksight:DescribeThemeAlias",
                    "quicksight:ListThemeAliases",
                    "quicksight:ListThemeVersions",
                    "quicksight:UpdateTheme",
                    "quicksight:DeleteTheme",
                    "quicksight:UpdateThemePermissions",
                    "quicksight:DescribeThemePermissions",
                ],
            )
        ]

    return Theme(
        AwsAccountId=cfg.aws_account_id,
        ThemeId=theme_id,
        Name="Financial Reporting Theme",
        BaseThemeId="CLASSIC",
        Tags=cfg.tags(),
        Configuration=ThemeConfiguration(
            DataColorPalette=DataColorPalette(
                Colors=DATA_COLOURS,
                EmptyFillColor=LIGHT_GREY,
                MinMaxGradient=[PALE_BLUE, DARK_BLUE],
            ),
            UIColorPalette=UIColorPalette(
                # Backgrounds
                PrimaryBackground=WHITE,
                SecondaryBackground=OFF_WHITE,
                # Text
                PrimaryForeground=CHARCOAL,
                SecondaryForeground=DARK_GREY,
                # Accent (interactive elements, selected states)
                Accent=DARK_BLUE,
                AccentForeground=WHITE,
                # Semantic
                Danger=DANGER_RED,
                DangerForeground=WHITE,
                Warning=WARNING_AMBER,
                WarningForeground=WHITE,
                Success=SUCCESS_GREEN,
                SuccessForeground=WHITE,
                # Dimension / Measure field pills
                Dimension=MEDIUM_BLUE,
                DimensionForeground=WHITE,
                Measure=NAVY,
                MeasureForeground=WHITE,
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
                    FontFamily(FontFamily="Helvetica"),
                    FontFamily(FontFamily="Arial"),
                ],
            ),
        ),
        Permissions=permissions,
        VersionDescription="Auto-generated financial reporting theme",
    )
