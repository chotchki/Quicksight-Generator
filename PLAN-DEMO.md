# Demo Data Plan

Create a demo datasource with sample data so the QuickSight analyses can be deployed against a real database and actually show charts, filters, and numbers. The demo is fully optional — the existing `generate` command keeps working with placeholder SQL. A new `demo` CLI command produces SQL scripts (and optionally executes them) to stand up and populate the schema.

In demo mode, the theme and analyses are branded as **Sasquatch National Bank** — a fictional bank serving sasquatch-run coffee shops around Seattle. The default `generate` output keeps the current generic blue/grey professional theme.

Theme: **sasquatches who run coffee shops around Seattle**.

---

## Open questions (none — all answered inline)

- **Database engine**: PostgreSQL (most common QuickSight datasource; SQL kept ANSI-compatible where possible).
- **Data volume**: ~200 sales across 6 merchants over 90 days — enough to look real in every chart without being slow to load.
- **How "optional" works**: The `demo` command is a separate CLI subcommand. The core `generate` command never touches a database. If `demo_database_url` is absent from config, the `demo` command just writes `.sql` files to disk.

---

## Step 1 — Schema DDL

Create `demo/schema.sql` with `CREATE TABLE`, `CREATE INDEX`, and `CREATE VIEW` statements for PostgreSQL.

### Tables

| Table | Purpose | Key columns to note |
|---|---|---|
| `merchants` | Coffee shop operators | `merchant_id` PK, `merchant_type` (franchise / independent / cart) |
| `sales` | Individual transactions | `settlement_id` FK nullable (NULL = unsettled), `external_transaction_id` FK nullable |
| `settlements` | Bundled payouts | `external_transaction_id` FK nullable |
| `payments` | Merchant payments | `settlement_id` FK, `is_returned` boolean, `external_transaction_id` FK nullable |
| `external_transactions` | Aggregated records from external systems | `transaction_type` (sales/settlements/payments), `merchant_id`, `external_system` |
| `late_thresholds` | Static config: how many days until "late" | `transaction_type` PK, `threshold_days`, `description` |

### Views (used by recon-exceptions dataset SQL)

- `sales_recon_view` — mirrors the sales-recon dataset SQL query
- `settlement_recon_view` — mirrors the settlement-recon dataset SQL query
- `payment_recon_view` — mirrors the payment-recon dataset SQL query

### Schema changes vs. current dataset SQL

The current placeholder SQL in `datasets.py` has several join conditions that won't work against a real schema:

| Dataset | Issue | Fix |
|---|---|---|
| Settlement exceptions | `LEFT JOIN settlements st ON st.settlement_id = s.sale_id` — joins on wrong column | Change to `WHERE s.settlement_id IS NULL` (unsettled sales have null FK) |
| Sales recon | `LEFT JOIN sales s ON s.transaction_id = et.transaction_id` — `sales` has no `transaction_id` | Join on `s.external_transaction_id = et.transaction_id` |
| Settlement recon | Same issue | Join on `st.external_transaction_id = et.transaction_id` |
| Payment recon | Same issue | Join on `p.external_transaction_id = et.transaction_id` |

These fixes are part of Step 2.

**Depends on**: nothing
**Output**: `demo/schema.sql`

---

## Step 2 — Fix dataset SQL queries

Update the SQL strings in `src/quicksight_gen/datasets.py` so they run against the schema from Step 1. Also add the `external_transaction_id` column to the financial dataset column lists where needed (sales, settlements, payments) so that QuickSight can display it if desired.

Changes:
1. **Sales dataset** — add `external_transaction_id` to columns and SQL.
2. **Settlements dataset** — add `external_transaction_id` to columns and SQL.
3. **Payments dataset** — add `external_transaction_id` to columns and SQL.
4. **Settlement exceptions** — rewrite JOIN to use `s.settlement_id IS NULL`.
5. **Sales recon** — change JOIN to `s.external_transaction_id = et.transaction_id`.
6. **Settlement recon** — change JOIN to `st.external_transaction_id = et.transaction_id`.
7. **Payment recon** — change JOIN to `p.external_transaction_id = et.transaction_id`.
8. **Recon exceptions** — verify view references match the views created in Step 1.

Run existing tests after — the JSON structure tests must still pass (they validate structure, not SQL correctness).

**Depends on**: Step 1 (need the schema to know the right column names)
**Output**: updated `datasets.py`, all 71 tests green

---

## Step 3 — Theme preset system + Sasquatch National Bank theme

Refactor `theme.py` so the colour palette, name, and description are driven by a selectable preset rather than hard-coded. The current blue/grey palette becomes the `default` preset. A new `sasquatch-bank` preset brands everything for the demo.

### Preset dataclass

Add a `ThemePreset` dataclass (or similar structure) that captures everything that varies between themes:

- Name ("Financial Reporting Theme" vs "Sasquatch National Bank Theme")
- Version description
- Data colour palette (chart series colours, gradient, empty fill)
- UI colour palette (backgrounds, foregrounds, accent, semantic colours)
- The analysis names reference the theme implicitly through the ARN — no change needed there, but `build_analysis` and `build_recon_analysis` should accept an optional `name_prefix` so demo mode can produce "Sasquatch National Bank — Financial Reporting" instead of "Financial Reporting Analysis"

### Default preset (unchanged look)

Keep all current colour constants — navy, blues, greys, the existing 8 chart colours. This is what `generate` uses when no preset is specified.

### Sasquatch National Bank preset

A Pacific Northwest bank: forest greens and earthy tones with a gold accent. Professional enough for a bank, woodsy enough for sasquatches.

| Role | Colour | Hex |
|---|---|---|
| Deep Forest (primary dark) | dark green | `#1B4332` |
| Forest Green (accent) | mid green | `#2D6A4F` |
| Sage (secondary) | muted teal | `#52796F` |
| Moss (light accent) | soft green | `#74A892` |
| Pale Sage (light fill) | pastel green | `#C5DDD3` |
| Bark Brown (dimension) | warm brown | `#5C4033` |
| Bank Gold (measure / highlight) | warm gold | `#C49A2A` |
| Parchment (secondary bg) | warm off-white | `#FAF6F1` |

Chart data colours (8, ordered for contrast):

```
Forest Green, Bank Gold, Bark Brown, Sage, Rust (#B85C38), Moss, Plum (#6B4C8A), Warm Grey (#7A7A72)
```

Semantic colours stay close to universal conventions (red danger, amber warning, green success) but shifted slightly warmer to match the palette.

### Config integration

Add `theme_preset: str = "default"` to `Config`. The `generate` command passes it through to `build_theme()`. In demo mode the CLI sets it to `"sasquatch-bank"`.

Optionally, the analysis builders accept a display name prefix so demo output reads:
- Theme: "Sasquatch National Bank Theme"
- Financial analysis: "Sasquatch National Bank — Financial Reporting"
- Recon analysis: "Sasquatch National Bank — Reconciliation"

### What doesn't change

- The QuickSight JSON structure is identical regardless of preset — only colours and display names differ
- All existing tests pass (they don't assert specific colour values or theme names)
- `build_theme(cfg)` still returns a `Theme`; callers don't change

**Depends on**: nothing (independent of schema work)
**Output**: refactored `theme.py`, updated `config.py`, updated `analysis.py` and `recon_analysis.py` (optional name prefix)

---

## Step 4 — Demo data generation module

Create `src/quicksight_gen/demo_data.py` — a Python module that produces deterministic INSERT statements for all tables.

### Merchants (sasquatch coffee shops)

| merchant_id | merchant_name | merchant_type | location_id | location name |
|---|---|---|---|---|
| `merch-bigfoot` | Bigfoot Brews | franchise | `loc-capitol-hill` | Capitol Hill |
| `merch-sasquatch` | Sasquatch Sips | franchise | `loc-pike-place` | Pike Place |
| `merch-yeti` | Yeti Espresso | independent | `loc-ballard` | Ballard |
| `merch-skookum` | Skookum Coffee Co. | independent | `loc-fremont` | Fremont |
| `merch-cryptid` | Cryptid Coffee Cart | cart | `loc-u-district` | University District |
| `merch-wildman` | Wildman's Roastery | independent | `loc-queen-anne` | Queen Anne |

### Sales (~200 transactions, last 90 days)

- Amounts range from $3.50 (single latte) to $48.00 (large catering order)
- Card brands: Visa, Mastercard, Amex, Discover
- Some sales have metadata (loyalty program, promo codes like "SQUATCH10")
- Some `card_last_four` / `reference_id` are NULL (cash-like transactions)
- Distribution weighted toward Bigfoot Brews (franchise, high-volume) and Sasquatch Sips (tourist area)

### Settlements (~30 settlements)

- **Franchise** merchants: daily settlements
- **Independent** merchants: weekly settlements
- **Cart** merchants: monthly settlements
- Statuses: `completed` (most), `pending` (a few recent), `failed` (1-2)
- ~10 sales deliberately left **unsettled** (NULL `settlement_id`) spread across Yeti Espresso and Cryptid Coffee Cart — these power the Exceptions tab

### Payments (~25 payments)

- Most settlements have a corresponding payment with `is_returned = false`
- 5 returned payments (negative scenarios):
  - Sasquatch Sips: 2 returns — "insufficient_funds", "bank_rejected"
  - Yeti Espresso: 1 return — "disputed"
  - Cryptid Coffee Cart: 2 returns — "account_closed", "invalid_account"

### External systems and transactions

Three external systems that aggregate internal records:

| System | Description |
|---|---|
| `SquarePay` | POS aggregator — bundles sales |
| `BankSync` | Bank reconciliation — bundles settlements and payments |
| `TaxCloud` | Tax reporting — bundles sales and settlements |

~60 external transactions across all three types (sales/settlements/payments).

### Reconciliation scenarios

| Scenario | % of external txns | How it looks in the data |
|---|---|---|
| **Matched** | ~60% | `external_amount` exactly equals SUM of linked internal records |
| **Not yet matched** | ~25% | Recent (within late threshold), amounts don't match or no internal records linked yet |
| **Late** | ~15% | Past the threshold, still unmatched — real mismatches or missing records |

Specific negative examples:
- SquarePay sales txn for Cryptid Coffee Cart: external says $1,200 but internal sales sum to $1,150 (a $50 discrepancy, late at 15 days)
- BankSync settlement txn for Yeti Espresso: $0 internal total, external says $3,400 (completely missing internal records, late at 22 days)
- TaxCloud sales txn for Sasquatch Sips: amounts match but records were linked late (resolved within threshold — shows a "just-in-time" match)

### Late thresholds

| transaction_type | threshold_days | description |
|---|---|---|
| `sales` | 7 | Sales older than 7 days without a matching external record are considered late |
| `settlements` | 14 | Settlements older than 14 days without a matching external record are considered late |
| `payments` | 30 | Payments older than 30 days without a matching external record are considered late |

### Implementation notes

- Use `random.Random(seed=42)` for deterministic generation — same data every run
- Generate dates relative to "today" so the data always looks fresh (configurable anchor date with default of today)
- Output a single function `generate_demo_sql() -> str` that returns the full INSERT script
- Also expose `generate_demo_sql_to_file(path)` for the CLI

**Depends on**: Step 1 (schema defines the target tables)
**Output**: `src/quicksight_gen/demo_data.py`

---

## Step 5 — CLI `demo` subcommand

Add a `demo` command group to the Click CLI:

```
quicksight-gen demo schema [-o demo/schema.sql]       # Emit DDL
quicksight-gen demo seed   [-o demo/seed.sql]          # Emit INSERT data
quicksight-gen demo apply  [-c config.yaml]            # Run both against a database
```

### Config changes

Add an optional `demo_database_url` field to `Config` and `config.yaml`:

```yaml
# Optional: PostgreSQL connection URL for demo data (only used by `demo apply`)
demo_database_url: "postgresql://user:pass@localhost:5432/quicksight_demo"
```

- `demo schema` and `demo seed` always work (just write SQL files)
- `demo apply` requires `demo_database_url` in config or `QS_GEN_DEMO_DATABASE_URL` env var; it connects via `psycopg2` (new optional dependency) and runs both scripts in a transaction
- `demo apply` is idempotent: uses `DROP TABLE IF EXISTS ... CASCADE` before CREATE
- `demo apply` also runs `quicksight-gen generate` with `theme_preset=sasquatch-bank` so the full demo output (SQL + QuickSight JSON) is produced in one command

### New dependency

Add `psycopg2-binary` as an optional dependency in `pyproject.toml`:

```toml
[project.optional-dependencies]
demo = ["psycopg2-binary>=2.9"]
dev = [
    "pytest>=7.0",
    "boto3-stubs[quicksight]>=1.34",
    "psycopg2-binary>=2.9",
]
```

**Depends on**: Steps 1 + 3 + 4 (needs schema DDL, theme presets, and seed data)
**Output**: updated `cli.py`, updated `config.py`, updated `pyproject.toml`

---

## Step 6 — Tests

### Unit tests (`tests/test_demo_data.py`)

- **Referential integrity**: every `settlement_id` in sales exists in settlements; every `merchant_id` in sales exists in merchants; every `external_transaction_id` FK points to a real external_transactions row
- **Scenario coverage**: at least 1 unsettled sale, at least 1 returned payment, at least 1 late recon, at least 1 matched recon, at least 1 not_yet_matched recon
- **Deterministic**: calling `generate_demo_sql()` twice produces identical output
- **Merchant names**: all 6 sasquatch merchants present
- **Volume**: sales count between 180-220, settlements 25-35, payments 20-30
- **Late thresholds**: all 3 types present with expected values

### Integration test (`tests/test_demo_sql.py`)

- Parse the generated SQL and verify it's syntactically valid (at minimum, no unclosed quotes or missing semicolons)
- Verify the schema SQL creates all expected tables and views
- Verify the seed SQL references only tables from the schema

### Theme preset tests (in `tests/test_theme_presets.py`)

- Default preset produces the existing blue/grey palette (spot-check a few key colours)
- Sasquatch-bank preset produces forest green / gold palette
- Both presets produce valid `Theme` objects that serialize without error
- Theme name and version description change per preset
- Unknown preset name raises a clear error

### CLI tests

- `demo schema` writes a `.sql` file to the output path
- `demo seed` writes a `.sql` file to the output path
- `demo apply` without `demo_database_url` exits with a clear error message
- `generate --theme-preset sasquatch-bank` produces a theme with the sasquatch palette and analysis names with "Sasquatch National Bank" prefix

**Depends on**: Steps 3 + 4 + 5
**Output**: `tests/test_demo_data.py`, `tests/test_demo_sql.py`, `tests/test_theme_presets.py`

---

## Step 7 — Update deploy.sh

The deploy script still references `out/analysis.json` (the old filename). Update it to deploy both analyses:

- Loop over `financial-analysis.json` and `recon-analysis.json`
- Same create-or-update pattern as datasets

**Depends on**: nothing (can be done anytime)
**Output**: updated `deploy.sh`

---

## Step 8 — Documentation

- Update `README.md`: add "Demo data" section explaining the `demo` command, the sasquatch theme, and how to connect to QuickSight
- Update `CLAUDE.md`: add demo module to project structure, note the optional psycopg2 dependency
- Update `config.example.yaml`: add commented-out `demo_database_url`

**Depends on**: Steps 5 + 7
**Output**: updated `README.md`, `CLAUDE.md`, `config.example.yaml`

---

## Dependency graph

```
Step 1 (schema DDL) ──┬──> Step 2 (fix dataset SQL)
                      │
                      └──> Step 4 (demo data) ──┐
                                                 ├──> Step 5 (CLI) ──> Step 6 (tests)
Step 3 (theme presets) ─────────────────────────┘                  └──> Step 8 (docs)
Step 7 (deploy.sh) ────────────────────────────────────────────────────> Step 8 (docs)
```

---

## Recommended chunks

| Chunk | Steps | What it does | Why together |
|---|---|---|---|
| **1** | 1 + 2 | Schema DDL + fix dataset SQL | Can't design the schema without knowing the queries, can't fix queries without the schema |
| **2** | 3 + 4 | Theme presets + demo data generation | Building the sasquatch world — the bank branding and the coffee shop data are one creative unit. Both are independent of the schema/SQL fixes. |
| **3** | 5 + 6 + 7 | CLI commands, tests, deploy.sh fix | Integration layer — wires everything together, validates it, and fixes the stale deploy script |
| **4** | 8 | Documentation | Polish pass once everything works |
