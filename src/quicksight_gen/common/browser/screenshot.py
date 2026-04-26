"""ScreenshotHarness: walk a deployed App's tree and capture
screenshots systematically.

Three capture modes:

- ``capture_all_sheets()`` — one full-page screenshot per sheet.
  Returns ``dict[Sheet, Path]`` keyed by the Sheet object ref so
  handbook templates can look up by Sheet, not by sheet_id string.
  Filenames remain ``{sheet_id}.png`` for stable on-disk names.
- ``capture_per_visual(sheet)`` — one screenshot per visual on the
  sheet, scroll-into-view + element crop. Returns
  ``dict[VisualLike, Path]`` keyed by the Visual object ref;
  filenames derive from each visual's resolved ``visual_id``.
- ``capture_with_state(parameter_values)`` — apply parameter values
  via URL hash, then capture every sheet. Returns
  ``dict[Sheet, Path]`` keyed by Sheet ref.

Sheet/Visual object keys (M.1.10 / F8) means callers can do
``paths[my_sheet]`` from the same App they constructed, instead
of carrying a parallel ``sheet_id`` string around. The on-disk
filenames stay sheet_id-derived so previously-generated images
overwrite cleanly across runs.

Why this matters for **Phase M**: when whitelabel-V2 swaps personas
(Sasquatch → Acme Bank), the docs need Acme-shaped screenshots.
Manual capture doesn't scale; ``capture_all_sheets()`` regenerates
the screenshot set against the new persona's deploy in one call.
The persona dataclass drives BOTH the seed generator AND the
screenshot pipeline in lockstep.

Same Page-based infra as ``TreeValidator``; different consumer —
they could share a ``DeployedTreeContext`` helper if patterns
crystallize. For now each tool has its own class.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from quicksight_gen.common.tree import (
    App,
    ParameterDeclLike,
    Sheet,
    VisualLike,
)

from .helpers import (
    click_sheet_tab,
    wait_for_dashboard_loaded,
    wait_for_visuals_present,
)


@dataclass
class ScreenshotHarness:
    """Walk an App + Page; produce a directory of named screenshots."""
    app: App
    page: Any  # Playwright Page; typed Any so module loads in unit tests.
    output_dir: Path
    embed_url: str | None = None  # Required for capture_with_state().
    timeout_ms: int = 30_000

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Capture modes
    # ------------------------------------------------------------------

    def capture_all_sheets(self) -> dict[Sheet, Path]:
        """One full-page screenshot per sheet on the App's analysis.

        Returns ``dict[Sheet, Path]`` keyed by the Sheet object ref.
        Filenames remain ``{sheet_id}.png`` so re-running overwrites
        the same on-disk file; only the in-memory key shape changed
        (M.1.10 / F8).
        """
        if self.app.analysis is None:
            raise ValueError(
                f"App {self.app.name!r} has no Analysis — nothing to capture."
            )
        results: dict[Sheet, Path] = {}
        for sheet in self.app.analysis.sheets:
            click_sheet_tab(self.page, sheet.name, self.timeout_ms)
            wait_for_visuals_present(
                self.page, min_count=1, timeout_ms=self.timeout_ms,
            )
            path = self.output_dir / f"{self._safe_id(sheet.sheet_id)}.png"
            self.page.screenshot(path=str(path), full_page=True)
            results[sheet] = path
        return results

    def capture_per_visual(self, sheet: Sheet) -> dict[VisualLike, Path]:
        """One screenshot per visual on ``sheet``, element-cropped.

        Returns ``dict[VisualLike, Path]`` keyed by the Visual object
        ref. Skips visuals without a resolved ``visual_id`` — the
        auto-ID walker hasn't run, or the visual is a factory wrapper
        without an explicit id. Caller should ``app.emit_analysis()``
        once before to resolve auto-IDs (the validator + this harness
        usually share a session-scoped fixture that already does
        that).
        """
        click_sheet_tab(self.page, sheet.name, self.timeout_ms)
        wait_for_visuals_present(
            self.page, min_count=len(sheet.visuals),
            timeout_ms=self.timeout_ms,
        )
        results: dict[VisualLike, Path] = {}
        for visual in sheet.visuals:
            visual_id = getattr(visual, "visual_id", None)
            if not visual_id:
                continue
            # Scroll into view + crop. Per the project memory,
            # below-the-fold visuals virtualize; a tall viewport is
            # sometimes needed. Caller manages viewport — the harness
            # just captures.
            element = self._find_visual_element(visual_id)
            path = self.output_dir / f"{self._safe_id(visual_id)}.png"
            if element is None:
                # Couldn't isolate the element — fall back to
                # full-page so the analyst can still see the result.
                self.page.screenshot(path=str(path), full_page=True)
            else:
                element.screenshot(path=str(path))
            results[visual] = path
        return results

    def capture_with_state(
        self,
        *,
        parameter_values: dict[ParameterDeclLike, Any],
        suffix: str = "state",
    ) -> dict[Sheet, Path]:
        """Re-load the dashboard with parameter values applied via URL
        hash (``#p.<name>=<value>``), then capture every sheet.

        Returns ``dict[Sheet, Path]`` keyed by Sheet object ref.
        Filenames suffix-tagged so multiple states don't overwrite each
        other: ``{sheet_id}-{suffix}.png``. Pass distinct ``suffix``
        values per state.

        Per the project memory ``project_qs_url_parameter_no_control_sync``,
        the on-screen control widget may not reflect the URL value
        even when the data is filtered. The screenshot captures what
        the analyst SEES, which is the rendered visual state — that's
        the right semantics for handbook screenshots.

        Requires ``embed_url`` set on construction.
        """
        if self.embed_url is None:
            raise ValueError(
                "capture_with_state needs embed_url set on the harness."
            )
        if self.app.analysis is None:
            raise ValueError(
                f"App {self.app.name!r} has no Analysis."
            )
        # Build the hash fragment from parameter object refs.
        fragments = [
            f"p.{p.name}={quote(str(v))}"
            for p, v in parameter_values.items()
        ]
        url = f"{self.embed_url}#{'&'.join(fragments)}"
        self.page.goto(url, timeout=self.timeout_ms)
        wait_for_dashboard_loaded(self.page, timeout_ms=self.timeout_ms)

        results: dict[Sheet, Path] = {}
        for sheet in self.app.analysis.sheets:
            click_sheet_tab(self.page, sheet.name, self.timeout_ms)
            wait_for_visuals_present(
                self.page, min_count=1, timeout_ms=self.timeout_ms,
            )
            sheet_safe = self._safe_id(sheet.sheet_id)
            path = self.output_dir / f"{sheet_safe}-{suffix}.png"
            self.page.screenshot(path=str(path), full_page=True)
            results[sheet] = path
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _safe_id(self, identifier: str) -> str:
        """Sanitize an ID into a filename-safe slug. QuickSight IDs
        are already mostly slug-safe (kebab-case + alphanumeric);
        this is belt-and-suspenders against future ID conventions."""
        return identifier.replace("/", "_").replace(":", "_")

    def _find_visual_element(self, visual_id: str):
        """Locate the DOM element for a specific visual.

        QuickSight's visual containers are tagged ``data-automation-id=
        "analysis_visual"`` generically — the visual_id isn't directly
        a DOM attribute. Until QS exposes a better selector, we walk
        the visual containers and match by title (which the title
        label IS in the DOM).

        Returns the Playwright Locator-or-element, or None when the
        match isn't found. Callers fall back to full-page capture.
        """
        # The browser_helpers' VISUAL_SELECTOR is the right anchor;
        # but matching back to a specific visual_id requires the
        # auto-ID's title or a structural index. For the MVP we
        # return None and let the caller fall back; a future
        # enhancement could thread the title through here.
        return None
