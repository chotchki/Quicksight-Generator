# How do I reskin the dashboards for my brand?

*Customization walkthrough — Developer / Product Owner. Reskinning + extending.*

## The story

You've stood up the dashboards against your data. Marketing
walks by, sees the demo's "Sasquatch National Bank" forest-green
palette in production, and asks the obvious question: *can we
get our actual brand colors on this?*

The answer is yes, and it takes about ten minutes. The visual
layer never references hex colors directly — every accent,
foreground, background, and link tint resolves at generate time
from a `ThemePreset` object. To rebrand, you register one new
preset (your bank's color tokens + name prefix), point your
config at it, and `quicksight-gen deploy --all --generate`. The
analysis name, KPI accent colors, table-cell tints, conditional
formatting, and font family all flip together.

The rebrand surface is deliberately small: one file, one preset
registration, no per-visual edits. The same constraint that
keeps the visual layer rebrand-friendly (no hardcoded hex codes
in `analysis.py` or `visuals.py`) is what makes this customization
walkthrough this short.

## The question

"My bank's brand book says navy blue and silver, our typography
is Inter, and our analysis names need to read 'SNB Treasury' not
'Account Reconciliation'. Where do I drop those in?"

## Where to look

Two reference points:

- **`src/quicksight_gen/common/theme.py`** — the `ThemePreset`
  dataclass at line 34, the three shipped presets (`default`,
  `sasquatch-bank`, `sasquatch-bank-ar`), and the `PRESETS`
  registry that exposes them by name. Adding a preset is one
  edit to this file.
- **`config.yaml` → `theme_preset`** — selects which preset the
  build uses. Defaults to `default`. Override per-environment
  via the `QS_GEN_THEME_PRESET` env var.

## What you'll see in the demo

Look at any of the shipped presets to see the color token
contract. The `default` preset (used in production by anyone
who hasn't customized) is in `theme.py:94-127`:

```python
DEFAULT_PRESET = ThemePreset(
    theme_name="QuickSight Gen Theme",
    version_description="Auto-generated dashboard theme",
    analysis_name_prefix=None,
    data_colors=[_DARK_BLUE, "#E07B39", "#3A9E6F", _MEDIUM_BLUE, ...],
    empty_fill_color=_LIGHT_GREY,
    gradient=[_PALE_BLUE, _DARK_BLUE],
    primary_bg=_WHITE,
    secondary_bg=_OFF_WHITE,
    primary_fg=_CHARCOAL,
    accent=_DARK_BLUE,
    accent_fg=_WHITE,
    link_tint="#E8EFF9",
    danger=_DANGER_RED,
    warning=_WARNING_AMBER,
    success=_SUCCESS_GREEN,
    ...
)
```

Every token has a job. The three load-bearing ones (the ones
that change the most when you swap in your brand):

- **`accent`** — the dashboard's primary brand color. Drives
  KPI value text, clickable cell text, accent-colored bar fills,
  filter pill backgrounds. The single token most strongly tied
  to "this looks like our brand."
- **`primary_fg`** — body text color. Almost always a near-black
  on a near-white background. Pick a true neutral; an off-spec
  primary_fg can make the whole dashboard feel "off" without
  the user being able to name why.
- **`link_tint`** — the pale-accent background applied to table
  cells whose click target is a right-click menu (drill-action
  cells). Should be ~12% opacity of `accent` on white. The
  `_E8EFF9` in DEFAULT_PRESET is exactly that for `_DARK_BLUE`.

The rest (data palette, gradient, semantic colors, dimension /
measure colors) are bulk fills — they affect chart series order
and KPI tile chrome, but the brand-recognition load lives on the
three above.

## What it means

Reskinning is three steps:

### Step 1 — Register your preset

Add your preset above the `PRESETS` registry in
`common/theme.py`. Pattern:

```python
# Brand palette — pull these from your bank's brand book.
_SNB_NAVY     = "#0A2647"
_SNB_SILVER   = "#A4B0BE"
_SNB_GOLD     = "#D4A017"
_SNB_PARCHMENT = "#FBF7EE"
_SNB_INK      = "#1F2933"
_SNB_WHITE    = "#FFFFFF"

ACME_TREASURY_PRESET = ThemePreset(
    theme_name="ACME Treasury Theme",
    version_description="ACME Treasury brand palette",
    analysis_name_prefix=None,                  # production: no prefix
    data_colors=[
        _SNB_NAVY, _SNB_GOLD, _SNB_SILVER,      # series 1, 2, 3
        "#5E8B7E", "#B85C38", "#6B4C8A",         # bulk fills
        "#3A9E6F", "#7A7A72",                    # neutrals
    ],
    empty_fill_color="#D9D9D9",
    gradient=["#D6E4F5", _SNB_NAVY],
    primary_bg=_SNB_WHITE,
    secondary_bg=_SNB_PARCHMENT,
    primary_fg=_SNB_INK,
    secondary_fg=_SNB_SILVER,
    accent=_SNB_NAVY,
    accent_fg=_SNB_WHITE,
    link_tint="#E5EAF2",                         # ~12% opacity navy on white
    danger="#C62828",
    danger_fg=_SNB_WHITE,
    warning="#E65100",
    warning_fg=_SNB_WHITE,
    success="#2E7D32",
    success_fg=_SNB_WHITE,
    dimension=_SNB_NAVY,
    dimension_fg=_SNB_WHITE,
    measure=_SNB_INK,
    measure_fg=_SNB_WHITE,
)
```

Then add it to the `PRESETS` dict at `theme.py:252`:

```python
PRESETS: dict[str, ThemePreset] = {
    "default": DEFAULT_PRESET,
    "sasquatch-bank": SASQUATCH_BANK_PRESET,
    "sasquatch-bank-ar": SASQUATCH_BANK_AR_PRESET,
    "acme-treasury": ACME_TREASURY_PRESET,       # ← new entry
}
```

### Step 2 — Point your config at it

Edit `config.yaml`:

```yaml
theme_preset: acme-treasury
```

Or override per-environment:

```bash
QS_GEN_THEME_PRESET=acme-treasury quicksight-gen deploy --all --generate
```

### Step 3 — Regenerate and deploy

```bash
quicksight-gen deploy --all --generate -c config.yaml -o out/
```

The deploy delete-then-creates the theme + analyses + dashboards
with your new tokens. Existing user-saved bookmarks survive (the
dashboard ID is stable across re-deploys); the visual chrome
flips on next load.

## Drilling in

A few tokens to know about beyond the obvious accent:

- **`analysis_name_prefix`** — set to `None` for production
  (analysis reads "Account Reconciliation" / "Payment
  Reconciliation"). Set to `"Demo"` on demo presets to name them
  "Demo — Account Reconciliation" and visually distinguish demo
  vs production analyses in the QuickSight authoring UI. The
  resolution lives in `_analysis_name()` at
  `apps/account_recon/analysis.py:1045` and the equivalent in
  `apps/payment_recon/analysis.py`.
- **`data_colors`** — the eight-color series palette. First
  three are most prominent (single-series KPIs, two-series bar
  charts, three-segment stacked charts). Pick three brand
  colors; the remaining five are bulk fills used only on
  high-cardinality breakdowns (which the AR / PR dashboards
  rarely produce).
- **`gradient`** — `[light, dark]` for any min/max gradient
  fills (currently the aging bar chart shaded by bucket). Pick
  a tinted version of `accent` for `dark` and a near-white
  tinted version for `light`. Don't pick a complementary color;
  the visual coherence depends on the gradient reading as "more
  of the same brand color."
- **`link_tint`** — keep this paler than you think. The pattern
  guideline (CLAUDE.md "Conventions") is that accent text on a
  pale-tint background signals a right-click drill action.
  Customers who pick a saturated link_tint accidentally make
  every drill cell look like a primary CTA — the cell becomes
  hard to read and competes with the accent KPIs. ~12% opacity
  of accent on white is the safe target.
- **Font family** — currently hardcoded to `Amazon Ember` →
  `sans-serif` fallback in `build_theme()` at
  `theme.py:340-345`. Not yet a preset token. If you need a
  brand font, edit the `Typography` block directly — the
  trade-off is QuickSight ships with a fixed font catalog and
  arbitrary fonts (your bank's `Inter` license, say) won't load
  reliably across browsers.

## Next step

Once your preset is registered and the deploy reflects your
brand:

1. **Spot-check the three load-bearing surfaces.** Open the AR
   Exceptions tab and check: KPI text colors (`accent`), table
   cells with right-click drills (`link_tint` background), and
   the aging bar chart (gradient + data_colors series order).
   These are the three places where a wrong token surfaces
   most visibly.
2. **Confirm the analysis name.** With
   `analysis_name_prefix=None`, the analysis in QuickSight
   reads "Account Reconciliation" (no prefix). Demo presets
   use `"Demo"` to name analyses "Demo — Account
   Reconciliation". Pick what fits your environment — the
   prefix shows in the QuickSight authoring UI's analysis
   list, not in the embedded dashboard the end user sees.
3. **Roll out per-app.** Both apps share one theme today (one
   `theme.json` is generated per build). If your bank wants
   visually distinct PR vs AR (the way the demo does — see
   `sasquatch-bank` vs `sasquatch-bank-ar`), register two
   presets and run `generate` per-app with the matching
   `--theme-preset` flag. Each `generate` call writes its own
   `theme.json`; deploy uses whichever was last written.

## Related walkthroughs

- [How do I configure the deploy for my AWS account?](how-do-i-configure-the-deploy.md) —
  covers the `theme_preset` field in `config.yaml` alongside
  the other deploy-config knobs.
