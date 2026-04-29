"""Browser-side retry helper for the M.4.1 end-to-end harness (M.4.1.g).

One surface: ``run_dashboard_check_with_retry`` — opens a deployed
QuickSight dashboard via a freshly-generated single-use embed URL,
waits for the dashboard chrome, runs an arbitrary ``operation(page)``
callable, and retries ONCE on QuickSight-side flake symptoms (page
``goto`` timeout, dashboard-loaded wait timeout, Playwright timeout
during the operation). ``AssertionError`` short-circuits — real test
failures don't get retried.

**Why retry**: the CLAUDE.md operational footgun documents the
"spinner forever" failure mode where every visual on every sheet sits
on the loading spinner with no error banner — observed once during
M.2b L1 dashboard review and confirmed not to be a code bug. The
recommended diagnostic ladder is "wait it out OR force a fresh
deploy"; the retry-with-fresh-embed-URL is the in-test version of
"wait it out" — give QuickSight one more chance before declaring a
hard failure.

**Why fresh URL**: embed URLs are single-use. The first attempt
consumes the URL even on timeout, so retry without a fresh URL would
hit ``ExpiredEmbedUrlException``. ``generate_dashboard_embed_url``
costs ~200ms — cheap to re-issue.

**What's NOT retried**: ``AssertionError`` (real planted-row missing
from the dashboard — this is the harness catching a regression, not
a flake). Subclassing AssertionError into a retryable variant would
be heavier than the gain; keep the rule simple.

**Failure semantics**: on the second-attempt failure, the original
exception propagates. A debug breadcrumb (``[harness] retry…``) goes
to stderr on every retry attempt so the failure dump's ``Exception``
section + the retry log together explain what happened.

**JS console capture (M.4.4.11)**: every page-load attempt registers
``page.on("console", ...)`` + ``page.on("pageerror", ...)`` handlers
that accumulate into a per-attempt list. On failure (timeout OR
assertion), the list is written next to the screenshot as
``<dashboard_id>_attempt<n>_console.txt`` so the human triaging can
pair the failure screenshot with the JS console output. Flushed-out
the M.4.4.10d-class bug (``epochMilliseconds must be a number, you
gave: null``) — that error never surfaced in the QS UI but printed
to the JS console. Capturing it as part of the failure manifest
turns the next bug of that shape from "spent hours on dead-end
diagnostics" into "look at the console output".
"""

from __future__ import annotations

import sys
from typing import Any, Callable


def run_dashboard_check_with_retry(
    *,
    aws_account_id: str,
    aws_region: str,
    dashboard_id: str,
    operation: Callable[[Any], None],
    page_timeout_ms: int,
    viewport: tuple[int, int] = (1600, 4000),
    headless: bool = True,
    max_attempts: int = 2,
    user_arn: str | None = None,
    screenshot_dir: Any | None = None,
) -> None:
    """Open a dashboard + run ``operation(page)``; retry once on flake.

    ``operation`` is a single-arg callable that takes a Playwright Page
    and runs whatever assertions the test needs. It MUST raise
    ``AssertionError`` for real failures (which propagate immediately,
    no retry) and ``playwright.sync_api.TimeoutError`` for QS-side
    waits that timed out (which trigger the retry).

    Generates a fresh embed URL per attempt — embed URLs are single-use,
    so the first attempt consumes it whether the test passed or
    timed out.

    Args:
        aws_account_id: AWS account id for the embed URL signing call.
        aws_region: dashboard region — passed through to
            ``generate_dashboard_embed_url`` which builds the boto3
            QS client in that region. Embed URLs MUST be signed by a
            dashboard-region client; using us-east-1 (identity region)
            for a dashboard deployed elsewhere returns a URL
            QuickSight rejects with the cryptic "We can't open that
            dashboard, another Quick account or it was deleted" page
            (M.4.1.i bug history). The helper signature takes the
            region string instead of a pre-built client so the
            wrong-client bug is unrepresentable.
        dashboard_id: QS dashboard id to open.
        operation: callable(page) -> None; runs the actual checks.
        page_timeout_ms: timeout for ``page.goto`` + dashboard-loaded
            wait (passed through to both).
        viewport: WebKit viewport (width, height). Default (1600, 4000)
            matches the L1/L2FT smoke tests so stacked tables don't
            sit below the fold.
        headless: WebKit headless mode (default True).
        max_attempts: total attempt count incl. the original (default
            2 = one retry).
        user_arn: optional override for the embed URL's UserArn; falls
            back to the env-var / project default.
        screenshot_dir: optional path where ``<dashboard_id>_attempt<n>.png``
            screenshots get written before re-raising on timeout. Lets
            the failure-dump fixture surface "what was actually on the
            page when we timed out" — usually the difference between
            a real spinner-forever vs an auth/perm error page vs a
            dashboard with zero sheets is one glance at the image.

    Raises:
        AssertionError: from ``operation`` — real test failure, no retry.
        playwright.sync_api.TimeoutError: after ``max_attempts`` retries
            of QS-side timeouts.
    """
    # Lazy imports — playwright may not be installed in test envs that
    # only run the unit tests in `tests/test_harness_browser.py`.
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    from quicksight_gen.common.browser.helpers import (
        generate_dashboard_embed_url,
        wait_for_dashboard_loaded,
        webkit_page,
    )

    last_timeout: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        embed_url = generate_dashboard_embed_url(
            aws_account_id=aws_account_id,
            aws_region=aws_region,
            dashboard_id=dashboard_id,
            user_arn=user_arn,
        )
        try:
            with webkit_page(headless=headless, viewport=viewport) as page:
                # Per-attempt JS console + pageerror capture (M.4.4.11).
                # Listeners stay live for the full attempt; on failure
                # the list is dumped next to the screenshot.
                console_messages: list[str] = []
                _attach_console_capture(page, console_messages)
                try:
                    page.goto(embed_url, timeout=page_timeout_ms)
                    wait_for_dashboard_loaded(page, timeout_ms=page_timeout_ms)
                    operation(page)
                except (PlaywrightTimeoutError, AssertionError):
                    # Capture the screenshot WHILE the page is still
                    # live (still inside the webkit_page context).
                    # AssertionError captures help diagnose "data is in
                    # the matview but the sheet doesn't show it" — the
                    # screenshot reveals whether it's a date filter,
                    # virtualization, column-visibility, or actual data
                    # absence problem. TimeoutError captures help with
                    # the QS spinner-forever footgun.
                    if screenshot_dir is not None:
                        _dump_failure_artifacts(
                            page=page,
                            screenshot_dir=screenshot_dir,
                            dashboard_id=dashboard_id,
                            attempt=attempt,
                            console_messages=console_messages,
                        )
                    raise
            return
        except PlaywrightTimeoutError as exc:
            last_timeout = exc
            if attempt >= max_attempts:
                raise
            print(
                f"[harness] dashboard {dashboard_id!r} timed out on attempt "
                f"{attempt}/{max_attempts}; regenerating embed URL + retrying "
                f"(QS spinner-forever footgun? exc={type(exc).__name__})",
                file=sys.stderr,
            )
    # Loop must either return or raise. Defensive only — keeps
    # static analyzers happy about the function having an exit path.
    raise RuntimeError(
        f"unreachable: retry loop exhausted without return; "
        f"last={last_timeout!r}"
    )


def _attach_console_capture(page: Any, sink: list[str]) -> None:
    """Register ``page.on("console")`` + ``page.on("pageerror")`` so
    every JS console message + uncaught error during the attempt
    accumulates into ``sink``.

    Format mirrors what a human sees in the browser devtools:
    ``[<type>] <text>`` for console events, ``[pageerror] <text>`` for
    uncaught exceptions. Each handler is wrapped in a broad ``except``
    because a misbehaving listener that raises would otherwise abort
    the page lifecycle — the failure-dump path needs this best-effort
    semantic so a console-handler bug never masks the real test
    failure.
    """
    def _on_console(msg: Any) -> None:
        try:
            msg_type = getattr(msg, "type", "log")
            text = getattr(msg, "text", "")
            sink.append(f"[{msg_type}] {text}")
        except Exception:  # noqa: BLE001 — best-effort
            pass

    def _on_pageerror(exc: Any) -> None:
        try:
            sink.append(f"[pageerror] {exc}")
        except Exception:  # noqa: BLE001 — best-effort
            pass

    page.on("console", _on_console)
    page.on("pageerror", _on_pageerror)


def _dump_failure_artifacts(
    *,
    page: Any,
    screenshot_dir: Any,
    dashboard_id: str,
    attempt: int,
    console_messages: list[str],
) -> None:
    """Write screenshot + console-log sidecar inside the still-live
    page context.

    Both writes are best-effort — a failure here MUST NOT mask the
    real exception that triggered the dump. Each artifact has its
    own try/except so a screenshot failure doesn't suppress the
    console dump (or vice versa).

    Filenames pair 1:1: ``<dashboard_id>_attempt<n>.png`` +
    ``<dashboard_id>_attempt<n>_console.txt`` so the human triaging
    can ``ls -la`` and immediately see "screenshot + console-log
    sidecar" for the same attempt.
    """
    from pathlib import Path

    try:
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001 — best-effort
        return

    shot_path = Path(screenshot_dir) / f"{dashboard_id}_attempt{attempt}.png"
    try:
        page.screenshot(path=str(shot_path), full_page=True)
        print(f"[harness] screenshot: {shot_path}", file=sys.stderr)
    except Exception:  # noqa: BLE001 — best-effort
        pass

    # Always write the console file — the empty case is itself a
    # diagnostic ("page never logged anything; failure is purely
    # network / render-side").
    console_path = (
        Path(screenshot_dir) / f"{dashboard_id}_attempt{attempt}_console.txt"
    )
    try:
        body = (
            "\n".join(console_messages)
            if console_messages
            else "<no console output captured>"
        )
        console_path.write_text(body + "\n", encoding="utf-8")
        print(
            f"[harness] console log: {console_path} "
            f"({len(console_messages)} message(s))",
            file=sys.stderr,
        )
    except Exception:  # noqa: BLE001 — best-effort
        pass
