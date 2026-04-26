"""L.1.10.5 — TreeValidator: typed walker that asserts a deployed
dashboard matches the source tree.

Walk ``(App, Page)``; for every Sheet → Visual / FilterControl /
ParameterControl in the tree, assert the expected element is in the
DOM. Per-kind dispatch extends naturally: adding a new typed Visual
subtype means adding one ``_validate_<kind>`` method — every existing
test automatically gets the new check.

Replaces the per-app structural e2e boilerplate. Today's
``test_inv_dashboard_structure.py`` (and AR / PR siblings) hand-lists
every visual title + filter group ID + parameter name; under
``TreeValidator.validate_structure()`` the same coverage collapses to
one call because the tree IS the source of truth.

Usage:

    from tests.e2e.tree_validator import TreeValidator

    def test_investigation_dashboard_matches_tree(inv_app, page):
        TreeValidator(inv_app, page).validate_structure()

Lives in ``tests/e2e/`` — depends on Playwright (``Page``), which
we don't want in ``common/``. Authors who don't run e2e never see
the validator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from quicksight_gen.common.tree import (
    App,
    Sheet,
    VisualLike,
)
from quicksight_gen.common.tree.actions import Drill

if TYPE_CHECKING:
    from playwright.sync_api import Page

from quicksight_gen.common.browser.helpers import (
    click_sheet_tab,
    get_visual_titles,
    sheet_control_titles,
    wait_for_sheet_controls_present,
    wait_for_visual_titles_present,
    wait_for_visuals_present,
)


def enumerate_cross_sheet_left_click_drills(
    app: App,
) -> list[tuple[Sheet, VisualLike, Sheet]]:
    """Walk every visual's actions; yield each cross-sheet, left-click
    `Drill` as a `(source_sheet, source_visual, target_sheet)` tuple.

    "Cross-sheet" = `target_sheet is not source_sheet`. Same-sheet
    drills (the mutual-filter pattern on PR Payment Reconciliation)
    are filtered out — clicking doesn't change the sheet, so the
    "wait for tab to switch" witness wouldn't apply.

    "Left-click" = `trigger == "DATA_POINT_CLICK"`. Right-click menu
    drills (`DATA_POINT_MENU`) need a different DOM driver and are
    skipped here.

    Returns a list (not a generator) so `pytest.mark.parametrize` can
    consume it directly without exhausting on first call.
    """
    out: list[tuple[Sheet, VisualLike, Sheet]] = []
    if app.analysis is None:
        return out
    for sheet in app.analysis.sheets:
        for visual in sheet.visuals:
            for action in getattr(visual, "actions", []) or []:
                if not isinstance(action, Drill):
                    continue
                if action.trigger != "DATA_POINT_CLICK":
                    continue
                target = action.target_sheet
                if not isinstance(target, Sheet) or target is sheet:
                    continue
                out.append((sheet, visual, target))
    return out


def _control_title(control) -> str | None:
    """Resolve the visible title of a tree filter / parameter control.

    Direct controls (`FilterDropdown`, `FilterDateTimePicker`,
    `FilterSlider`, `ParameterDropdown`, `ParameterSlider`,
    `ParameterDateTimePicker`) carry their own `.title`. Cross-sheet
    filter controls (`FilterCrossSheet`) inherit the title from the
    referenced filter's `default_control` (multi-sheet filters set this
    in `FilterGroup.with_*` factories so the per-sheet cross-sheet
    widget shows the same label across sheets).
    """
    title = getattr(control, "title", None)
    if title:
        return str(title)
    # Cross-sheet control: walk to filter.default_control.title
    inner_filter = getattr(control, "filter", None)
    if inner_filter is None:
        return None
    default_control = getattr(inner_filter, "default_control", None)
    if default_control is None:
        return None
    return getattr(default_control, "title", None)


@dataclass
class ValidationFailure:
    """One mismatch between tree and DOM."""
    where: str            # e.g. "Sheet 'Account Network' / Visual 'Flagged'"
    message: str          # human-readable description of the mismatch


@dataclass
class TreeValidator:
    """Walk a tree and a deployed dashboard Page; assert they match.

    All assertion methods collect into ``self.failures`` so a single
    validation run surfaces every mismatch at once, not just the first.
    Call ``.raise_if_failed()`` at the end to convert accumulated
    failures into an exception with the full list.
    """
    app: App
    page: Any  # Playwright Page; typed as Any so the module loads
               # without playwright installed (unit tests use a mock).
    timeout_ms: int = 30_000
    failures: list[ValidationFailure] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Top-level entry points
    # ------------------------------------------------------------------

    def validate_structure(self) -> None:
        """Persona-agnostic structural check. Every sheet's visuals +
        controls are present in the DOM.

        This is the one-call replacement for per-app
        ``test_*_dashboard_structure.py`` boilerplate.
        """
        if self.app.analysis is None:
            self._fail("App", "App has no Analysis — nothing to validate.")
            self.raise_if_failed()
            return
        for sheet in self.app.analysis.sheets:
            self.validate_sheet(sheet)
        self.raise_if_failed()

    def validate_sheet(self, sheet: Sheet) -> None:
        """Navigate to ``sheet`` and assert its contents are in the DOM."""
        try:
            click_sheet_tab(self.page, sheet.name, self.timeout_ms)
        except Exception as e:
            self._fail(
                f"Sheet {sheet.name!r}",
                f"Couldn't navigate to sheet tab: {e!r}",
            )
            return

        # Visual count — use len of visuals that actually expose a title
        # (factory-wrapper visuals may not).
        titled_visuals = [
            v for v in sheet.visuals if getattr(v, "title", None)
        ]
        expected_titles = {v.title for v in titled_visuals}
        if expected_titles:
            try:
                wait_for_visual_titles_present(
                    self.page, expected_titles, self.timeout_ms,
                )
            except Exception:
                rendered = set(get_visual_titles(self.page))
                missing = expected_titles - rendered
                self._fail(
                    f"Sheet {sheet.name!r}",
                    f"Missing visual titles: {sorted(missing)} "
                    f"(rendered: {sorted(rendered)})",
                )

        if sheet.visuals:
            try:
                wait_for_visuals_present(
                    self.page, len(sheet.visuals), self.timeout_ms,
                )
            except Exception:
                self._fail(
                    f"Sheet {sheet.name!r}",
                    f"Expected at least {len(sheet.visuals)} visuals "
                    "rendered; timed out waiting.",
                )

        # Per-visual dispatch — each typed Visual subtype's check.
        for visual in sheet.visuals:
            self.validate_visual(sheet, visual)

        # Sheet controls — each filter / parameter control declared on
        # the sheet must be present in the DOM. Asserted as a positive
        # set check; an unexpected stale control in the DOM doesn't
        # fail here (the explicit regression guards in `test_filters.py`
        # cover those).
        self.validate_sheet_controls(sheet)

    def validate_sheet_controls(self, sheet: Sheet) -> None:
        """Walk this sheet's `filter_controls` + `parameter_controls`
        and assert each control's title is in the rendered DOM.
        Cross-sheet filter controls inherit their title from the bound
        filter's `default_control`."""
        filter_ctrls = getattr(sheet, "filter_controls", None) or []
        param_ctrls = getattr(sheet, "parameter_controls", None) or []
        expected_titles = {
            t for t in (_control_title(c) for c in filter_ctrls + param_ctrls)
            if t
        }
        if not expected_titles:
            return
        try:
            wait_for_sheet_controls_present(self.page, self.timeout_ms)
        except Exception:
            self._fail(
                f"Sheet {sheet.name!r}",
                "Expected sheet controls but none rendered.",
            )
            return
        rendered = set(sheet_control_titles(self.page))
        missing = expected_titles - rendered
        if missing:
            self._fail(
                f"Sheet {sheet.name!r}",
                f"Missing sheet control titles: {sorted(missing)} "
                f"(rendered: {sorted(rendered)})",
            )

    def validate_visual(self, sheet: Sheet, visual: VisualLike) -> None:
        """Per-kind dispatch. Each typed Visual subtype has a
        corresponding ``_validate_<kind>`` method; unknown kinds fall
        back to the generic title-present check."""
        kind = getattr(visual, "_AUTO_KIND", None)
        if kind is None:
            # No typed subtype shape to validate. Title-present check
            # already ran at the sheet level; nothing more to do here.
            return
        method = getattr(self, f"_validate_{kind}", None)
        if method is not None:
            method(sheet, visual)

    # ------------------------------------------------------------------
    # Per-kind checks. Minimal MVP — each asserts "the visual rendered"
    # and leaves kind-specific DOM shape verification (e.g. Sankey ribbon
    # counts, Table column headers, KPI numeric text) as follow-up work
    # when a specific regression motivates it.
    # ------------------------------------------------------------------

    def _validate_kpi(self, sheet: Sheet, kpi) -> None:
        # Title presence is the sheet-level check's responsibility;
        # per-kind hook left as an extension point for "KPI shows a
        # parseable number" when a bug calls for it.
        pass

    def _validate_table(self, sheet: Sheet, table) -> None:
        pass

    def _validate_bar(self, sheet: Sheet, bar) -> None:
        pass

    def _validate_sankey(self, sheet: Sheet, sankey) -> None:
        pass

    # ------------------------------------------------------------------
    # Failure handling
    # ------------------------------------------------------------------

    def _fail(self, where: str, message: str) -> None:
        """Record a validation failure without raising. Use this
        throughout the walker; ``raise_if_failed`` converts the list
        into an AssertionError at the end."""
        self.failures.append(ValidationFailure(where=where, message=message))

    def raise_if_failed(self) -> None:
        """If any failures accumulated, raise a single AssertionError
        listing them all. No-op if the run was clean."""
        if not self.failures:
            return
        lines = ["TreeValidator found mismatches:"]
        for f in self.failures:
            lines.append(f"  [{f.where}] {f.message}")
        raise AssertionError("\n".join(lines))
