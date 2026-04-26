"""Playwright-driven browser helpers + typed screenshot harness.

Promoted out of ``tests/e2e/`` in M.1.10 (per spike finding F7) so
production CLI code (M.6 deploy, M.7 docs render, M.8 training
render) can import the screenshot pipeline without reaching into
``tests/``.

The module pair:

- :mod:`quicksight_gen.common.browser.helpers` — Playwright
  page-driving primitives (URL gen, page setup, sheet-tab
  navigation, table/control probing, waits). Also re-exported
  here for convenience.
- :mod:`quicksight_gen.common.browser.screenshot` — typed
  ``ScreenshotHarness`` walker over an ``App`` tree.

Production callers typically only need ``ScreenshotHarness`` +
``generate_dashboard_embed_url`` + ``webkit_page``. The full
probe / assertion surface (``count_table_rows``,
``read_kpi_value``, etc.) is for e2e test code; it lives in the
same module today because splitting it cleanly will be more
obvious once M.6/M.7/M.8 surface what production really needs.
"""

from .helpers import (
    generate_dashboard_embed_url,
    get_user_arn,
    webkit_page,
)
from .screenshot import ScreenshotHarness

__all__ = [
    "ScreenshotHarness",
    "generate_dashboard_embed_url",
    "get_user_arn",
    "webkit_page",
]
