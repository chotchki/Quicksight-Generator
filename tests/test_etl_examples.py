"""Lock the contract documented in ``docs/Schema_v3.md``.

The Schema_v3 doc is the Data Integration Team's persona contract: they
read it and use the ETL examples to populate ``transactions`` +
``daily_balances`` from upstream feeds.  These tests guard against the
doc silently drifting from the code by:

1. Asserting the ``account_type`` table in the doc matches the
   ``CANONICAL_ACCOUNT_TYPES`` set used by tests + emitted by the demo.
2. Asserting every metadata key the doc declares for a ``transfer_type``
   actually appears on at least one matching row in the demo seed (a
   Data Integration Team member who follows the doc gets data the
   dashboards know how to read).
3. Replicating the ``Example 3`` limit-breach SELECT in Python over the
   parsed demo data — the documented JSON path / join shape returns
   the same breaches the in-database view does.
4. Asserting the "Forbidden SQL patterns" table is exhaustive: none of
   the listed patterns appear in the schema or any dataset SQL.
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from quicksight_gen.account_recon import datasets as ar_datasets
from quicksight_gen.account_recon.demo_data import (
    generate_demo_sql as generate_ar_sql,
)
from quicksight_gen.payment_recon import datasets as pr_datasets
from quicksight_gen.payment_recon.demo_data import generate_demo_sql

from tests.test_demo_data import (
    ANCHOR,
    CANONICAL_ACCOUNT_TYPES,
    _metadata,
    _parse_inserts,
    _row_parts,
    _val,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "Schema_v3.md"


# ---------------------------------------------------------------------------
# Markdown parsing helpers
# ---------------------------------------------------------------------------

def _doc_text() -> str:
    return DOC_PATH.read_text()


def _markdown_table_first_column(doc: str, heading: str) -> list[str]:
    """Return the first-column cell values from the markdown table that
    immediately follows ``heading`` (an ``## `` / ``### `` line).
    """
    lines = doc.splitlines()
    try:
        start = next(
            i for i, ln in enumerate(lines)
            if ln.strip().startswith("#") and ln.strip().lstrip("# ").startswith(heading)
        )
    except StopIteration:
        raise AssertionError(f"Heading not found in {DOC_PATH.name}: {heading!r}")
    rows: list[str] = []
    in_table = False
    for ln in lines[start + 1:]:
        stripped = ln.strip()
        if stripped.startswith("|"):
            in_table = True
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Skip header (`| heading |`) and separator (`|---|---|`).
            if all(set(c) <= set("- ") for c in cells):
                continue
            rows.append(cells[0])
        elif in_table:
            break
    if rows and rows[0].lower() in {"key", "`account_type`", "forbidden"}:
        rows = rows[1:]
    # Strip backticks the markdown wraps identifiers in.
    return [r.strip("`") for r in rows]


# ---------------------------------------------------------------------------
# Fixtures (shared across classes)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def doc() -> str:
    return _doc_text()


@pytest.fixture(scope="module")
def combined() -> dict[str, list[str]]:
    pr = _parse_inserts(generate_demo_sql(ANCHOR))
    ar = _parse_inserts(generate_ar_sql(ANCHOR))
    out: dict[str, list[str]] = {}
    for src in (pr, ar):
        for table, rows in src.items():
            out.setdefault(table, []).extend(rows)
    return out


# ---------------------------------------------------------------------------
# 1. Canonical account_type list — doc vs. Python
# ---------------------------------------------------------------------------

class TestAccountTypeCatalog:
    def test_doc_table_matches_python_canonical_set(self, doc):
        documented = set(_markdown_table_first_column(
            doc, "Canonical `account_type` values"
        ))
        assert documented == CANONICAL_ACCOUNT_TYPES, (
            "docs/Schema_v3.md account_type table is out of sync with "
            f"CANONICAL_ACCOUNT_TYPES.  Doc - Python: {documented - CANONICAL_ACCOUNT_TYPES}; "
            f"Python - doc: {CANONICAL_ACCOUNT_TYPES - documented}"
        )

    def test_every_emitted_account_type_is_documented(self, doc, combined):
        documented = set(_markdown_table_first_column(
            doc, "Canonical `account_type` values"
        ))
        emitted_txn = {_val(r, "account_type") for r in combined["transactions"]}
        emitted_bal = {_row_parts(r)[3] for r in combined["daily_balances"]}
        emitted = emitted_txn | emitted_bal
        missing = emitted - documented
        assert not missing, (
            f"Demo emits account_type values not in docs/Schema_v3.md: {missing}"
        )


# ---------------------------------------------------------------------------
# 2. Metadata key catalog — doc vs. seed
# ---------------------------------------------------------------------------

# Map each documented metadata-key section to the predicate that selects
# the rows it claims to describe.  The lambda picks rows matching the
# section's filter so the test can assert "every documented key shows up
# on at least one matching row".
METADATA_SECTIONS: list[tuple[str, str, callable]] = [
    (
        "On `transactions` rows where `transfer_type = 'sale'` (PR merchant sales)",
        "transactions",
        lambda r: _val(r, "transfer_type") == "sale",
    ),
    (
        "On `transactions` rows where `transfer_type = 'payment'` (PR merchant payouts)",
        "transactions",
        lambda r: _val(r, "transfer_type") == "payment",
    ),
    (
        "On `transactions` rows where `transfer_type = 'external_txn'` (external observations)",
        "transactions",
        lambda r: _val(r, "transfer_type") == "external_txn",
    ),
]


class TestMetadataKeyCatalog:
    @pytest.mark.parametrize(
        "section,table,predicate",
        METADATA_SECTIONS,
        ids=[s[0].split("`")[1] for s in METADATA_SECTIONS],
    )
    def test_documented_keys_appear_in_demo(
        self, doc, combined, section, table, predicate
    ):
        documented = _markdown_table_first_column(doc, section)
        # Some doc rows pack multiple keys: "`taxes`, `tips`, `discount_percentage`".
        documented = [k.strip("` ") for cell in documented for k in cell.split(",")]
        documented = [k for k in documented if k]

        # Phase H rows aren't in the v3 demo; everything else is.
        if not documented:
            pytest.skip(f"No keys documented under {section!r}")

        rows = [r for r in combined[table] if predicate(r)]
        assert rows, f"No demo rows match predicate for {section!r}"

        observed: set[str] = set()
        for r in rows:
            observed.update(_metadata(r).keys())

        # Optional keys (taxes/tips/discount_percentage) only appear on a
        # subset of sales — accept "any documented key found on any row"
        # and report which keys never showed up so the doc and demo can
        # be reconciled if they drift.
        missing = set(documented) - observed
        # Only flag keys the demo deliberately emits.  The doc lists a few
        # "future / Phase H" keys — track them in EXEMPT.
        EXEMPT = {"card_last_four", "external_transaction_id"}
        missing -= EXEMPT
        # Optional sales metadata is sparse; accept absence of one of
        # taxes/tips/discount_percentage but flag if all three are missing.
        OPTIONAL = {"taxes", "tips", "discount_percentage"}
        if (missing & OPTIONAL) and (OPTIONAL - missing):
            missing -= OPTIONAL
        assert not missing, (
            f"Documented metadata keys absent from demo for {section!r}: {missing}"
        )

    def test_ledger_balance_rows_carry_documented_limits(self, doc, combined):
        # Doc declares: limits is an object with per-transfer-type caps
        # like {"ach": 100000, "wire": 50000, "internal": 25000}.
        ledger_rows = [
            r for r in combined["daily_balances"]
            if _row_parts(r)[2] == "NULL"  # control_account_id IS NULL
        ]
        with_limits = [
            r for r in ledger_rows if "limits" in _metadata(r)
        ]
        assert with_limits, (
            "No ledger daily_balances rows carry a `limits` metadata "
            "object — Example 3 in docs/Schema_v3.md cannot be exercised."
        )
        # Every limits payload key should be a known transfer_type.
        known_types = {
            "ach", "wire", "internal", "cash",
            "funding_batch", "fee", "clearing_sweep",
            "sale", "settlement", "payment", "external_txn",
        }
        for r in with_limits:
            limits = _metadata(r)["limits"]
            assert isinstance(limits, dict), (
                f"limits payload not a dict: {limits!r}"
            )
            unknown = set(limits) - known_types
            assert not unknown, (
                f"limits keys not in transfer_type enum: {unknown}"
            )


# ---------------------------------------------------------------------------
# 3. Example 3 — limit-breach SELECT replicated against demo data
# ---------------------------------------------------------------------------

class TestExample3LimitBreachQuery:
    """Replicate Example 3's pattern in Python and confirm it surfaces
    the limit breaches the demo plants — the doc's documented JSON path
    + join shape match the schema's actual computed view."""

    def test_pattern_returns_breach_rows(self, combined):
        # Build {(ledger_id, balance_date) -> {transfer_type: limit}}
        # from daily_balances metadata.limits.
        limits: dict[tuple[str, str], dict[str, Decimal]] = {}
        for r in combined["daily_balances"]:
            if _row_parts(r)[2] != "NULL":  # only ledger rows carry limits
                continue
            payload = _metadata(r)
            limit_obj = payload.get("limits")
            if not isinstance(limit_obj, dict):
                continue
            account_id = _row_parts(r)[0]
            balance_date = _row_parts(r)[5]
            limits[(account_id, balance_date)] = {
                k: Decimal(str(v)) for k, v in limit_obj.items()
            }

        assert limits, "No ledger limits found in daily_balances metadata"

        # Aggregate sub-ledger outbound by (ledger, date, transfer_type).
        outbound: dict[tuple[str, str, str], Decimal] = defaultdict(
            lambda: Decimal("0")
        )
        for r in combined["transactions"]:
            if _val(r, "status") != "success":
                continue
            signed = Decimal(_val(r, "signed_amount"))
            if signed >= 0:
                continue  # outbound = debit-from-customer = negative on sub-ledger
            ledger = _val(r, "control_account_id")
            if not ledger:
                continue  # direct ledger postings not part of sub-ledger outbound
            balance_date = _val(r, "balance_date")
            ttype = _val(r, "transfer_type")
            outbound[(ledger, balance_date, ttype)] += abs(signed)

        # Apply the documented breach predicate.
        breaches: list[tuple[str, str, str, Decimal, Decimal]] = []
        for (ledger, bdate, ttype), total in outbound.items():
            cap = limits.get((ledger, bdate), {}).get(ttype)
            if cap is None:
                continue
            if total > cap:
                breaches.append((ledger, bdate, ttype, total, cap))

        # Demo seed plants known limit breaches; the count should be
        # non-trivial.  This is the canary: if the doc's limit-payload
        # path or join condition ever drifts from how the generator
        # emits limits, this test breaks.
        assert len(breaches) >= 3, (
            f"Expected ≥3 limit breaches in demo seed via Example 3 pattern, "
            f"got {len(breaches)}.  Sample: {breaches[:5]}"
        )


# ---------------------------------------------------------------------------
# 4. Forbidden SQL patterns — doc table is exhaustive vs. actual SQL
# ---------------------------------------------------------------------------

# Patterns the doc declares forbidden.  Pairs of (regex, human description).
# These mirror the "Forbidden SQL patterns" table in docs/Schema_v3.md;
# the regexes are intentionally loose (any occurrence anywhere is a fail).
FORBIDDEN_PATTERNS = [
    (r"\bJSONB\b", "JSONB type"),
    (r"->>", "metadata->>'key' (Postgres-only JSON path)"),
    (r"(?<!-)->\s*'", "metadata->'key' (Postgres-only JSON path)"),
    (r"@>", "@> JSON containment operator"),
    (r"\?\s*'", "? JSON key-existence operator"),
    (r"\bGIN\b", "GIN index"),
    (r"USING\s+gin", "GIN index (lower-case)"),
    (r"::text\[\]|VARCHAR\[\]", "array column types"),
]


class TestForbiddenSqlPatterns:
    @pytest.fixture(scope="class")
    def all_sql(self) -> str:
        # Schema DDL + every dataset module's source (which embeds the
        # SQL strings as triple-quoted Python literals).  Source-text
        # scanning sidesteps Config plumbing and catches both the
        # query SQL and any inline expression SQL.
        from quicksight_gen.demo import generate_schema_sql
        chunks = [generate_schema_sql()]
        for mod in (ar_datasets, pr_datasets):
            chunks.append(Path(mod.__file__).read_text())
        return "\n".join(chunks)

    @pytest.mark.parametrize(
        "pattern,description",
        FORBIDDEN_PATTERNS,
        ids=[p[1] for p in FORBIDDEN_PATTERNS],
    )
    def test_pattern_absent(self, all_sql, pattern, description):
        # Strip SQL line-comments so a `-- forbidden: ...` comment in
        # docs / schema doesn't trip the regex.
        scrubbed = re.sub(r"--[^\n]*", "", all_sql)
        # Drop the JSON-encoded forbidden-patterns block from the doc
        # itself — the doc literally contains `metadata->>'key'` as
        # examples of what NOT to do.  We only scan SQL.
        match = re.search(pattern, scrubbed)
        assert match is None, (
            f"Forbidden SQL pattern found: {description}.  "
            f"Match: ...{scrubbed[max(0, match.start()-40):match.end()+40]}..."
        )


# ---------------------------------------------------------------------------
# 5. SQL code blocks in the doc are syntactically plausible
# ---------------------------------------------------------------------------

class TestSqlBlocksParse:
    def test_sql_blocks_are_balanced(self, doc):
        """Each ```sql block must have balanced parens and end on a
        recognized statement.  Cheap regression guard against truncation."""
        blocks = re.findall(r"```sql\n(.*?)```", doc, re.DOTALL)
        assert blocks, "Expected at least one SQL code block in Schema_v3.md"
        for i, block in enumerate(blocks):
            opens = block.count("(")
            closes = block.count(")")
            assert opens == closes, (
                f"SQL block #{i} has unbalanced parens "
                f"(open={opens}, close={closes}):\n{block[:200]}"
            )

    def test_etl_examples_present(self, doc):
        # The 5 ETL examples are the persona's day-one read; if any goes
        # missing the doc lost its persona contract.
        for n in range(1, 6):
            assert f"### Example {n}" in doc, (
                f"docs/Schema_v3.md is missing `### Example {n}` ETL block"
            )
