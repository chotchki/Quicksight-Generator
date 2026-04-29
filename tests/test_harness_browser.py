"""Unit tests for ``tests/e2e/_harness_browser.py`` (M.4.1.g).

The retry helper's two contracts:

1. ``AssertionError`` short-circuits — the operation raises real
   failures and the helper MUST NOT swallow them. Real planted-row
   misses are how the harness catches regressions.

2. ``playwright.sync_api.TimeoutError`` triggers retry-with-fresh-URL.
   On each retry the helper calls ``generate_dashboard_embed_url``
   again so the second attempt has a fresh single-use token.

Both behaviors are exercised here against a fake QS client (records
``generate_embed_url_for_registered_user`` calls) + a fake
``webkit_page`` substitute (monkeypatched in via
``quicksight_gen.common.browser.helpers``). No real Playwright,
no real boto3.

Lives at the project test root so it runs in default ``pytest``
(no ``QS_GEN_E2E`` gate needed — it's pure-data unit tests).
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Add tests/e2e to import path so the test can pull in the helper
# module directly without adding it to the package install.
sys.path.insert(0, str(Path(__file__).parent / "e2e"))


# Skip the entire module if Playwright isn't installed — the helper
# imports ``playwright.sync_api.TimeoutError`` lazily inside its
# function body, so it would fail in test envs without playwright.
playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="harness retry tests need playwright (install via "
    "`pip install -e '.[dev]'`)",
)

from _harness_browser import run_dashboard_check_with_retry  # noqa: E402


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def _fake_qs_client(url_prefix: str = "https://quicksight.aws/embed/") -> MagicMock:
    """psycopg2-style mock returning a unique embed URL each call.

    Every call to ``generate_embed_url_for_registered_user`` returns a
    monotonically-incrementing URL so the test can prove a retry
    actually called the API a second time.
    """
    client = MagicMock()
    counter = {"n": 0}

    def _gen(**kwargs):
        counter["n"] += 1
        return {"EmbedUrl": f"{url_prefix}{counter['n']}"}

    client.generate_embed_url_for_registered_user.side_effect = _gen
    return client


class _FakePage:
    """Playwright Page substitute — records ``goto`` calls + supports
    ``wait_for_load_state`` + ``wait_for_selector`` (no-ops by default).

    Tests that need to simulate a per-call timeout patch ``goto`` or
    install a side effect.
    """

    def __init__(self) -> None:
        self.gotos: list[str] = []
        self.load_state_calls: list[Any] = []
        self.selector_calls: list[Any] = []

    def goto(self, url: str, timeout: int) -> None:
        self.gotos.append(url)

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        self.load_state_calls.append((state, timeout))

    def wait_for_selector(self, selector: str, timeout: int, state: str) -> None:
        self.selector_calls.append((selector, timeout, state))


def _patch_webkit_page(monkeypatch: pytest.MonkeyPatch, page: _FakePage) -> None:
    """Replace ``common.browser.helpers.webkit_page`` with a context
    manager that yields the supplied fake page.

    Patch lives on the source module — the helper imports
    ``webkit_page`` lazily inside the function body, so we patch the
    attribute on ``quicksight_gen.common.browser.helpers``.
    """

    @contextmanager
    def _fake(headless: bool = True, viewport: tuple[int, int] = (1600, 1000)):
        yield page

    monkeypatch.setattr(
        "quicksight_gen.common.browser.helpers.webkit_page",
        _fake,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_first_attempt_success_calls_qs_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No retry on success — exactly one embed URL generated, exactly
    one operation call, one ``page.goto``."""
    qs = _fake_qs_client()
    page = _FakePage()
    _patch_webkit_page(monkeypatch, page)

    op_calls: list[Any] = []

    def operation(p: Any) -> None:
        op_calls.append(p)

    run_dashboard_check_with_retry(
        qs,
        account_id="111122223333",
        dashboard_id="dash-123",
        operation=operation,
        page_timeout_ms=30_000,
    )

    assert qs.generate_embed_url_for_registered_user.call_count == 1
    assert len(page.gotos) == 1
    assert len(op_calls) == 1


# ---------------------------------------------------------------------------
# AssertionError short-circuits — no retry
# ---------------------------------------------------------------------------


def test_assertion_error_propagates_no_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real test failure must NOT trigger the QS retry path —
    swallowing AssertionError would mask regressions."""
    qs = _fake_qs_client()
    page = _FakePage()
    _patch_webkit_page(monkeypatch, page)

    def operation(p: Any) -> None:
        raise AssertionError("planted row missing on Drift sheet")

    with pytest.raises(AssertionError, match="planted row missing"):
        run_dashboard_check_with_retry(
            qs,
            account_id="111122223333",
            dashboard_id="dash-x",
            operation=operation,
            page_timeout_ms=30_000,
        )

    # Only one URL ever generated — no retry happened.
    assert qs.generate_embed_url_for_registered_user.call_count == 1


# ---------------------------------------------------------------------------
# TimeoutError → retry once with fresh URL
# ---------------------------------------------------------------------------


def test_timeout_then_success_retries_once_with_fresh_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First attempt raises Playwright TimeoutError → helper retries.
    Second attempt succeeds. Two URLs generated; second call sees a
    different URL (proves the retry didn't reuse the spent one)."""
    from playwright.sync_api import TimeoutError as PWTimeout

    qs = _fake_qs_client()
    page = _FakePage()
    _patch_webkit_page(monkeypatch, page)

    op_attempts = {"n": 0}

    def operation(p: Any) -> None:
        op_attempts["n"] += 1
        if op_attempts["n"] == 1:
            raise PWTimeout("visual didn't render in 30s")
        # Second attempt: succeed.

    run_dashboard_check_with_retry(
        qs,
        account_id="111122223333",
        dashboard_id="dash-flake",
        operation=operation,
        page_timeout_ms=30_000,
    )

    # Two URLs generated, two pages opened, two op calls.
    assert qs.generate_embed_url_for_registered_user.call_count == 2
    assert len(page.gotos) == 2
    assert page.gotos[0] != page.gotos[1], (
        "second attempt should hit a fresh embed URL, not the spent one"
    )
    assert op_attempts["n"] == 2


def test_timeout_on_both_attempts_raises_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If every attempt times out, the helper exhausts retries and
    propagates the timeout — caller sees a real failure to triage."""
    from playwright.sync_api import TimeoutError as PWTimeout

    qs = _fake_qs_client()
    page = _FakePage()
    _patch_webkit_page(monkeypatch, page)

    def operation(p: Any) -> None:
        raise PWTimeout("permanently broken")

    with pytest.raises(PWTimeout, match="permanently broken"):
        run_dashboard_check_with_retry(
            qs,
            account_id="111122223333",
            dashboard_id="dash-broken",
            operation=operation,
            page_timeout_ms=30_000,
        )

    # Default max_attempts = 2 → exactly 2 URL generations.
    assert qs.generate_embed_url_for_registered_user.call_count == 2


def test_max_attempts_param_controls_retry_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``max_attempts=1`` disables the retry — first timeout
    propagates immediately."""
    from playwright.sync_api import TimeoutError as PWTimeout

    qs = _fake_qs_client()
    page = _FakePage()
    _patch_webkit_page(monkeypatch, page)

    def operation(p: Any) -> None:
        raise PWTimeout("flaky")

    with pytest.raises(PWTimeout):
        run_dashboard_check_with_retry(
            qs,
            account_id="111122223333",
            dashboard_id="dash-x",
            operation=operation,
            page_timeout_ms=30_000,
            max_attempts=1,
        )

    assert qs.generate_embed_url_for_registered_user.call_count == 1


# ---------------------------------------------------------------------------
# URL generation kwargs — wired through correctly
# ---------------------------------------------------------------------------


def test_user_arn_threaded_through_to_qs_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom ``user_arn`` reaches the QS embed-URL call — used by
    integrators with non-default user mappings."""
    qs = _fake_qs_client()
    page = _FakePage()
    _patch_webkit_page(monkeypatch, page)

    custom_arn = "arn:aws:quicksight:us-east-1:111122223333:user/default/test-user"

    run_dashboard_check_with_retry(
        qs,
        account_id="111122223333",
        dashboard_id="dash-u",
        operation=lambda _p: None,
        page_timeout_ms=30_000,
        user_arn=custom_arn,
    )

    call_kwargs = qs.generate_embed_url_for_registered_user.call_args.kwargs
    assert call_kwargs["UserArn"] == custom_arn
    assert call_kwargs["AwsAccountId"] == "111122223333"
    assert call_kwargs["ExperienceConfiguration"]["Dashboard"][
        "InitialDashboardId"
    ] == "dash-u"


def test_page_goto_uses_generated_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The URL returned by the QS client is what ``page.goto`` opens —
    no caching / mutation between generation and use."""
    qs = _fake_qs_client(url_prefix="https://test.aws/embed/")
    page = _FakePage()
    _patch_webkit_page(monkeypatch, page)

    run_dashboard_check_with_retry(
        qs,
        account_id="111122223333",
        dashboard_id="dash-x",
        operation=lambda _p: None,
        page_timeout_ms=30_000,
    )

    assert page.gotos == ["https://test.aws/embed/1"]
