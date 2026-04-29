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
"""

from __future__ import annotations

import sys
from typing import Any, Callable


def run_dashboard_check_with_retry(
    qs_identity_client: Any,
    *,
    account_id: str,
    dashboard_id: str,
    operation: Callable[[Any], None],
    page_timeout_ms: int,
    viewport: tuple[int, int] = (1600, 4000),
    headless: bool = True,
    max_attempts: int = 2,
    user_arn: str | None = None,
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
        qs_identity_client: boto3 QS client in the identity region
            (us-east-1) — embed URLs ALWAYS come from the identity
            region, never the dashboard region.
        account_id: AWS account id for the embed URL signing call.
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
            qs_identity_client,
            account_id,
            dashboard_id,
            user_arn=user_arn,
        )
        try:
            with webkit_page(headless=headless, viewport=viewport) as page:
                page.goto(embed_url, timeout=page_timeout_ms)
                wait_for_dashboard_loaded(page, timeout_ms=page_timeout_ms)
                operation(page)
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
