# Plan: End-to-End Dashboard Testing

## Problem

The current test suite validates JSON structure, cross-references, and data generation but cannot verify that the deployed dashboard actually works in QuickSight. Filters might not bind, visuals might not render, drill-downs might silently fail. The only way to catch these issues today is manual testing after every deploy.

## Strategy: Two Layers

### Layer 1: AWS API Validation (no browser)

Use `boto3` to call `describe-dashboard-definition` and `describe-analysis` after deployment. Compare the deployed resource structure against what we generated. This catches:
- Resources that failed to create (status != CREATION_SUCCESSFUL)
- Missing sheets, visuals, filters, or parameters
- Dataset binding mismatches
- Structural drift between generated JSON and what QuickSight actually accepted

This layer is fast, reliable, and doesn't need a browser.

### Layer 2: Browser UI Testing (Playwright + WebKit)

Use Playwright's WebKit engine to load the dashboard via an embed URL, verify visuals render, and exercise interactive features (filters, drill-downs, mutual table filtering). This catches:
- Visuals that fail to render due to SQL errors or column mismatches
- Filters that don't bind to visuals correctly
- Drill-down actions that navigate to the wrong sheet or fail silently
- Layout issues (overlapping visuals, missing titles)

**Why Playwright over Selenium+Safari:**
- Playwright WebKit runs headless (Selenium Safari does not)
- Simpler setup — no `safaridriver --enable` needed
- Python-native async API with sync wrapper
- Better for CI/CD if we add it later
- Close enough to Safari for dashboard rendering validation

**Auth approach:** Use `generate_embed_url_for_registered_user` to get a pre-authenticated, time-limited URL. No login form automation needed.

## Implementation Steps

### Phase 1: API Validation Tests

- [x] 1.1 — Add `boto3` to `[project.optional-dependencies]` as `test-e2e` extra
- [x] 1.2 — Create `tests/e2e/conftest.py` with fixtures: boto3 QuickSight client, account ID, region (from config.yaml or env vars). Skip all tests if `QS_GEN_E2E` env var is not set (so `pytest` alone still works without AWS credentials)
- [x] 1.3 — Create `tests/e2e/test_deployed_resources.py`:
  - Test that the dashboard exists and status is CREATION_SUCCESSFUL
  - Test that the analysis exists and status is CREATION_SUCCESSFUL
  - Test that all 8 datasets exist and are importable
  - Test that the theme exists
- [x] 1.4 — Create `tests/e2e/test_dashboard_structure.py`:
  - Call `describe_dashboard_definition` and validate:
  - Dashboard has 5 sheets with expected names/IDs
  - Each sheet has the expected number of visuals
  - All visual IDs match what we generated
  - All filter group IDs and filter IDs are present
  - Both parameters (pSettlementId, pExternalTransactionId) are declared
  - All dataset identifier declarations reference existing datasets
- [x] 1.5 — Create `tests/e2e/test_dataset_health.py`:
  - Call `describe_data_set` for each dataset
  - Verify import status is COMPLETED (not FAILED)
  - Verify row counts are > 0 (confirms the SQL actually ran)
  - Verify column names match our InputColumns definitions
- [x] 1.6 — Run the API tests against the deployed dashboard, fix any issues

### Phase 2: Browser Test Infrastructure

- [x] 2.1 — Add `playwright` to `[project.optional-dependencies]` as `test-e2e` extra
- [x] 2.2 — Create `tests/e2e/browser_helpers.py` (embed URL, webkit_page ctx, wait helpers, screenshot, get_sheet_tab_names)
- [x] 2.3 — Create `tests/e2e/test_dashboard_renders.py` (loads URL, asserts page title, asserts 5 sheet tabs)
- [x] 2.4 — Browser render test passes; key learnings:
  - Embed URL must be generated against the **dashboard's region**, not identity region
  - Embed URLs are **single-use** — fixture must be function-scoped
  - Sheet tabs use `[role="tab"]` selector (5 tabs found by name)
  - `networkidle` fires before tabs are hydrated; we wait on `[role="tab"]` (state=attached) after networkidle

### Phase 3: Visual Rendering Tests

- [x] 3.1 — Create `tests/e2e/test_sheet_visuals.py`:
  - Navigate to each sheet tab
  - For each sheet, verify the expected visuals are present (KPIs show numbers, tables have rows, charts render)
  - Verify KPI values are > 0 (confirms data flows through)
  - Verify detail tables have the expected column headers
  - Verify bar charts and pie charts have rendered SVG/canvas elements
- [x] 3.2 — Add visual-specific checks:
  - Sales Overview: 2 KPIs, 2 bar charts, 1 detail table
  - Settlements: 2 KPIs, 1 bar chart, 1 detail table
  - Payments: 2 KPIs, 1 pie chart, 1 detail table
  - Exceptions: 2 KPIs, 2 detail tables
  - Payment Recon: 3 KPIs, 1 bar chart, 2 detail tables

### Phase 4: Interactive Feature Tests

- [x] 4.1 — Create `tests/e2e/test_filters.py` (date-range only — other filters skipped per user):
  - On Sales tab: change date range filter, verify detail table updates
  - On Sales tab: select a merchant filter value, verify table filters
  - On Payment Recon tab: select a match status, verify tables filter
  - On Payment Recon tab: move the days-outstanding slider, verify tables update
- [x] 4.2 — Create `tests/e2e/test_drilldown.py`:
  - On Settlements tab: click a detail row, verify navigation to Sales tab with pSettlementId filter applied
  - On Payments tab: click a detail row, verify navigation to Settlements tab with pSettlementId filter applied
- [x] 4.3 — Create `tests/e2e/test_recon_mutual_filter.py` (external→payments verified):
  - On Payment Recon tab: click an external transaction row, verify payments table filters to show linked payments
  - Click a payment row, verify external transactions table filters back
  - Click the bar chart, verify both tables filter by the clicked system/status
- [x] 4.4 — All interactive tests run together (drill-down x2, mutual filter, date-range filter); 33 e2e pass in ~78s

### Phase 5: Test Runner Integration

- [x] 5.1 — Add pytest markers: `@pytest.mark.e2e` for all e2e tests, `@pytest.mark.browser` for browser tests, `@pytest.mark.api` for API-only tests
- [x] 5.2 — Update `pyproject.toml` with marker definitions and a separate test path config so `pytest` alone skips e2e tests
- [x] 5.3 — Add a test runner script or Makefile targets:
  - `pytest` — unit tests only (existing behavior, no AWS needed)
  - `pytest tests/e2e -m api` — API validation only (needs AWS credentials)
  - `pytest tests/e2e -m browser` — browser tests only (needs AWS + Playwright)
  - `pytest tests/e2e` — all e2e tests
- [x] 5.4 — Document the e2e test setup in README.md (prerequisites, env vars, how to run)
- [x] 5.5 — Add screenshot-on-failure to browser tests (save to `tests/e2e/screenshots/`)

## Resolved Questions

1. **Embed URL permissions** — Confirmed working. The root-linked IAM user has `GenerateEmbedUrlForRegisteredUser` permissions. QuickSight identity region is **us-east-1** (embed URL calls must use us-east-1 regardless of dashboard region). User ARN: `arn:aws:quicksight:us-east-1:470656905821:user/default/470656905821`.

2. **DOM selectors** — Will use robust selectors (ARIA labels, data attributes, visual titles) and discover them during Phase 2 implementation.

3. **Test data dependency** — Build a single `make e2e` or script that runs `demo apply` + `deploy.sh` + `pytest tests/e2e` so testing can be kicked off and iterated without manual steps.

4. **Flakiness** — 30s page load, 10s per-visual render, 1 retry on failure. All timeouts tunable via env vars (e.g. `QS_E2E_PAGE_TIMEOUT`, `QS_E2E_VISUAL_TIMEOUT`) to handle slow free-tier RDS.

## File Layout

```
tests/
  e2e/
    __init__.py
    conftest.py                  # Fixtures: boto3 client, config, skip logic
    browser_helpers.py           # Embed URL, browser launch, wait helpers
    test_deployed_resources.py   # API: resource existence and status
    test_dashboard_structure.py  # API: definition matches generated JSON
    test_dataset_health.py       # API: dataset import status and row counts
    test_dashboard_renders.py    # Browser: page loads, tabs visible
    test_sheet_visuals.py        # Browser: visuals render on each sheet
    test_filters.py              # Browser: filter interactions
    test_drilldown.py            # Browser: cross-sheet navigation
    test_recon_mutual_filter.py  # Browser: recon table mutual filtering
    screenshots/                 # Failure screenshots (gitignored)
```
