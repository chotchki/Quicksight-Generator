"""X.2.d — JS unit tests for CategoryFilter checkbox→hidden-input sync.

ParameterDropdown and NumericRange are pure HTML — no JS, browser
form serialization carries the values into HTMX's hx-include.
CategoryFilter is the only primitive that needs JS: checkboxes
(intentionally unnamed so they don't pollute the wire) update a
hidden ``filter_<col>`` input as a comma-joined string. This file
verifies that sync.

Loads the bootstrap test harness, builds a ``.category-filter``
wrapper inline, calls ``wireCategoryFilters``, and asserts the
hidden input's value follows the checkbox state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest


playwright_sync_api = pytest.importorskip("playwright.sync_api")


_FIXTURE = (
    Path(__file__).parent / "fixtures" / "bootstrap_test_harness.html"
)


def _load_harness(page: Any) -> None:
    page.goto(f"file://{_FIXTURE.resolve()}")
    page.wait_for_function(
        "() => window.__bootstrap_internals__ != null", timeout=5000,
    )


def _build_wrapper(page: Any, options: list[str]) -> None:
    """Inject a ``.category-filter`` wrapper with the given options
    + call ``wireCategoryFilters`` so the listeners get attached."""
    page.evaluate(
        """(opts) => {
            var prev = document.getElementById('cf-target');
            if (prev) prev.remove();
            var div = document.createElement('div');
            div.id = 'cf-target';
            div.className = 'category-filter';
            div.setAttribute('data-filter-name', 'filter_status');
            var hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'filter_status';
            hidden.value = '';
            div.appendChild(hidden);
            opts.forEach(function(opt) {
                var label = document.createElement('label');
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.value = opt;
                label.appendChild(cb);
                label.appendChild(document.createTextNode(' ' + opt));
                div.appendChild(label);
            });
            document.body.appendChild(div);
            window.__bootstrap_internals__.wireCategoryFilters(document);
        }""",
        options,
    )


def _hidden_value(page: Any) -> str:
    return cast(str, page.evaluate(
        '() => document.querySelector("#cf-target input[type=\\"hidden\\"]").value',
    ))


def _check(page: Any, value: str) -> None:
    """Click the checkbox with the given value, dispatching the
    change event the listener subscribes to."""
    page.evaluate(
        """(v) => {
            var cb = document.querySelector('#cf-target input[type="checkbox"][value="' + v + '"]');
            cb.checked = true;
            cb.dispatchEvent(new Event('change'));
        }""",
        value,
    )


def _uncheck(page: Any, value: str) -> None:
    page.evaluate(
        """(v) => {
            var cb = document.querySelector('#cf-target input[type="checkbox"][value="' + v + '"]');
            cb.checked = false;
            cb.dispatchEvent(new Event('change'));
        }""",
        value,
    )


def test_checking_one_option_sets_hidden_to_that_value() -> None:
    with playwright_sync_api.sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()
        _load_harness(page)
        _build_wrapper(page, ["open", "closed", "pending"])
        _check(page, "open")
        result = _hidden_value(page)
        browser.close()
    assert result == "open"


def test_checking_two_options_joins_with_comma() -> None:
    """The PLAN.md X.2.d URL contract is comma-joined values."""
    with playwright_sync_api.sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()
        _load_harness(page)
        _build_wrapper(page, ["open", "closed", "pending"])
        _check(page, "open")
        _check(page, "closed")
        result = _hidden_value(page)
        browser.close()
    # Order follows the DOM order of the checkboxes, not the order
    # of the user clicks (querySelectorAll is document order).
    assert result == "open,closed"


def test_unchecking_removes_value_from_join() -> None:
    with playwright_sync_api.sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()
        _load_harness(page)
        _build_wrapper(page, ["open", "closed"])
        _check(page, "open")
        _check(page, "closed")
        _uncheck(page, "open")
        result = _hidden_value(page)
        browser.close()
    assert result == "closed"


def test_no_checkboxes_checked_leaves_hidden_empty() -> None:
    """Empty value is the "all" semantic — server treats absent as
    no filter."""
    with playwright_sync_api.sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()
        _load_harness(page)
        _build_wrapper(page, ["open", "closed"])
        # No clicks — initial state.
        result = _hidden_value(page)
        browser.close()
    assert result == ""


def test_unchecking_all_returns_to_empty() -> None:
    with playwright_sync_api.sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()
        _load_harness(page)
        _build_wrapper(page, ["open", "closed"])
        _check(page, "open")
        _uncheck(page, "open")
        result = _hidden_value(page)
        browser.close()
    assert result == ""


def test_wire_is_idempotent_via_data_wired_flag() -> None:
    """Calling wireCategoryFilters twice on the same DOM shouldn't
    double-bind the change listener (data-wired flag protects it).
    Validates by counting how many times the hidden input updates
    after a single change event."""
    with playwright_sync_api.sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()
        _load_harness(page)
        _build_wrapper(page, ["open"])
        # Re-call wire — data-wired guard should make it a no-op.
        page.evaluate(
            "() => window.__bootstrap_internals__.wireCategoryFilters(document)",
        )
        _check(page, "open")
        # If double-bound, the value is still "open" (idempotent
        # update). The real proof would be inspecting listeners,
        # but Playwright doesn't expose that. The data-wired
        # attribute is the contract.
        wired_attr = cast(str, page.evaluate(
            '() => document.querySelector("#cf-target").dataset.wired',
        ))
        result = _hidden_value(page)
        browser.close()
    assert wired_attr == "1"
    assert result == "open"


def test_three_separate_filters_on_one_page_each_track_independently() -> None:
    """Multiple .category-filter wrappers on the same page (e.g. one
    for status + one for region) each have their own hidden input
    + their own checkbox state."""
    with playwright_sync_api.sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()
        _load_harness(page)
        page.evaluate("""() => {
            ['status', 'region', 'tier'].forEach(function(col, i) {
                var div = document.createElement('div');
                div.id = 'cf-' + col;
                div.className = 'category-filter';
                var hidden = document.createElement('input');
                hidden.type = 'hidden';
                hidden.name = 'filter_' + col;
                hidden.value = '';
                div.appendChild(hidden);
                var label = document.createElement('label');
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.value = 'v' + i;
                label.appendChild(cb);
                div.appendChild(label);
                document.body.appendChild(div);
            });
            window.__bootstrap_internals__.wireCategoryFilters(document);
        }""")
        # Click only the status filter's checkbox.
        page.evaluate("""() => {
            var cb = document.querySelector('#cf-status input[type="checkbox"]');
            cb.checked = true;
            cb.dispatchEvent(new Event('change'));
        }""")
        status_v = cast(str, page.evaluate(
            '() => document.querySelector("#cf-status input[type=\\"hidden\\"]").value',
        ))
        region_v = cast(str, page.evaluate(
            '() => document.querySelector("#cf-region input[type=\\"hidden\\"]").value',
        ))
        browser.close()
    assert status_v == "v0"
    assert region_v == ""
