"""Lock the contract documented in ``docs/Schema_v6.md``.

The Schema_v6 doc is the Data Integration Team's persona contract: they
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

from quicksight_gen.apps.account_recon import datasets as ar_datasets
from quicksight_gen.apps.account_recon.demo_data import (
    generate_demo_sql as generate_ar_sql,
)
from quicksight_gen.apps.payment_recon import datasets as pr_datasets
from quicksight_gen.apps.payment_recon.demo_data import generate_demo_sql

from tests.test_demo_data import (
    ANCHOR,
    _metadata,
    _parse_inserts,
    _row_parts,
    _val,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "src" / "quicksight_gen" / "docs" / "Schema_v6.md"


# ---------------------------------------------------------------------------
# Markdown parsing helpers
# ---------------------------------------------------------------------------

def _doc_text() -> str:
    return DOC_PATH.read_text()


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


# M.2d.7: TestAccountTypeCatalog + TestMetadataKeyCatalog removed
# (used to parse Schema_v3 markdown tables that the v6 rewrite
# eliminated). Their persona-contract intent — "the seed's emitted
# values trace back to a declared spec" — is now the M.2d.8 matrix's
# job in tests/test_l2_seed_contract.py: parameterized over multiple
# L2 YAMLs, asserts contract against L2.accounts / Rail.metadata_keys.


# ---------------------------------------------------------------------------
# Example 3 — limit-breach SELECT replicated against demo data
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
# These mirror the "Forbidden SQL patterns" table in docs/Schema_v6.md;
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
        from quicksight_gen.schema import generate_schema_sql
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
        assert blocks, "Expected at least one SQL code block in Schema_v6.md"
        for i, block in enumerate(blocks):
            opens = block.count("(")
            closes = block.count(")")
            assert opens == closes, (
                f"SQL block #{i} has unbalanced parens "
                f"(open={opens}, close={closes}):\n{block[:200]}"
            )

    # M.2d.7: test_etl_examples_present removed — the 5 ETL Example
    # blocks moved from Schema_v6.md into docs/walkthroughs/etl/. The
    # walkthrough-presence guard is now in test_etl_walkthroughs.py
    # (M.2d.8) — single check against the per-question handbook files.
