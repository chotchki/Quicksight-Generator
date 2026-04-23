"""Tree-based builder for the Investigation App (L.2 port).

Replaces the constant-heavy + manually-cross-referenced builders in
``apps/investigation/{analysis,filters,visuals}.py`` with the typed
tree primitives from ``common/tree/``. Sheets land one per L.2 sub-step:

- L.2.1 — Getting Started (text boxes only, app-level skeleton)
- L.2.2 — Recipient Fanout
- L.2.3 — Volume Anomalies
- L.2.4 — Money Trail
- L.2.5 — Account Network (already validated through L.0 + L.1.15)
- L.2.6 — App-level wiring: dashboard + dataset declarations
- L.2.7 — Drop ALL_FG_INV_IDS / ALL_P_INV from constants.py

Per-sub-step contract: byte-identical SheetDefinition output compared
to the imperative builder's per-sheet output. The byte-identity tests
live in ``tests/test_l2_investigation_port.py``.
"""

from __future__ import annotations

from quicksight_gen.apps.investigation.constants import (
    SHEET_INV_GETTING_STARTED,
)
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.models import SheetTextBox
from quicksight_gen.common.theme import get_preset
from quicksight_gen.common.tree import (
    Analysis,
    App,
    Sheet,
)


# Layout constants mirror apps/investigation/analysis.py.
_FULL = 36


def _build_getting_started_sheet(cfg: Config, analysis: Analysis) -> Sheet:
    """Getting Started — landing page with welcome + roadmap text boxes.

    Two full-width text boxes stacked top-to-bottom. No visuals,
    no controls, no filters. The simplest sheet on Investigation —
    its job in L.2.1 is to land the app-level skeleton (App + Analysis +
    text-box layout slot support) so subsequent sheet ports snap in.
    """
    accent = get_preset(cfg.theme_preset).accent

    sheet = analysis.add_sheet(Sheet(
        sheet_id=SHEET_INV_GETTING_STARTED,
        name="Getting Started",
        title="Getting Started",
        description=(
            "Landing page — summarises each tab in this dashboard. "
            "No filters or visuals."
        ),
    ))

    welcome = sheet.add_text_box(SheetTextBox(
        SheetTextBoxId="inv-gs-welcome",
        Content=rt.text_box(
            rt.inline(
                "Investigation Dashboard",
                font_size="36px",
                color=accent,
            ),
            rt.BR,
            rt.BR,
            rt.body(
                "Compliance / AML triage surface for the Sasquatch "
                "National Bank shared base ledger. Three question-shaped "
                "sheets — recipient fanout, volume anomalies, and money "
                "trail — each one drilling back into Account "
                "Reconciliation or Payment Reconciliation for the row "
                "evidence."
            ),
        ),
    ))
    roadmap = sheet.add_text_box(SheetTextBox(
        SheetTextBoxId="inv-gs-roadmap",
        Content=rt.text_box(
            rt.heading("Sheets in this dashboard", color=accent),
            rt.BR,
            rt.BR,
            rt.bullets([
                "Recipient Fanout — who is receiving money from too many "
                "distinct senders? (live)",
                "Volume Anomalies — which sender → recipient pair just "
                "spiked above the rolling baseline? (live)",
                "Money Trail — where did this transfer originate and "
                "where does it go? (live)",
                "Account Network — who does this account exchange money "
                "with, on either side? (live)",
            ]),
        ),
    ))

    sheet.place_text_box(welcome, col_span=_FULL, row_span=5, col_index=0)
    sheet.place_text_box(roadmap, col_span=_FULL, row_span=6, col_index=0)

    return sheet


def build_investigation_app(cfg: Config) -> App:
    """Build the Investigation App tree.

    L.2.1 ships only the Getting Started sheet. Subsequent sub-steps
    add the remaining four sheets, dataset registrations, parameter
    declarations, calc fields, and filter groups. L.2.6 attaches the
    Dashboard and swaps the CLI's analysis/dashboard build path to this
    function.
    """
    app = App(name="investigation", cfg=cfg)
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="investigation-analysis",
        name="Investigation",
    ))
    _build_getting_started_sheet(cfg, analysis)
    return app
