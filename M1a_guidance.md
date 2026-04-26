# M.1a — SPEC change summary for planning

This document summarizes the SPEC.md changes accumulated during the L2-design pass and groups them into implementation work clusters for planning M.1a. Source spec: `./SPEC.md`.

The intent is to bring the existing generic-tool implementation (post-spike) into alignment with the updated spec without re-litigating the design decisions captured in this folder.

---

## What's new or changed since the prior spec

### Layer 1 (universal model)

| Change | Detail |
|---|---|
| **New enum member** | `Status ⊇ {Pending, Posted}` — Pending was implicit before, now named |
| **New enum** | `SupersedeReason ⊇ {Inflight, BundleAssignment, TechnicalCorrection}` |
| **New primitive** | `Duration` (used for aging windows) |
| **New `Transaction` field** | `BundleId?: ID` — populated by aggregating-rail bundlers |
| **New `Transaction` field** | `Supersedes?: SupersedeReason` — set on every higher-Entry row |
| **New `StoredBalance` field** | `Supersedes?: SupersedeReason` — same shape on the snapshot entity |
| **New subsection** | "Status lifecycle" — Pending → Posted via higher-Entry rows |
| **New subsection** | "Higher-Entry rows: inflight vs correction vs bundling" — categorization per entity |
| **Updated Design Principle** | "Three kinds of higher-Entry row" — Inflight, BundleAssignment, TechnicalCorrection (with which apply to which entity) |

### Layer 2 (institutional model) — new primitives

| Primitive | What it does |
|---|---|
| **Transfer Templates** | Multi-leg shared-Transfer grouping. Has `TransferKey`, `Completion`, `ExpectedNet`, `LegRails`. |
| **Aggregating Rails** | Rail variant (`aggregating: true`) that sweeps activity. Has `Cadence`, `BundlesActivity`. Not chained. |
| **PostedRequirements** | Field set required for `Status = Posted`. Auto-derives from TransferKey + required-true chain `parent_transfer_id`; integrator adds Rail-specific. |
| **MaxPendingAge** | Aging watch on Pending rows that haven't transitioned. |
| **MaxUnbundledAge** | Aging watch on Posted-but-unbundled rows. |
| **Per-leg Origin** | `SourceOrigin` / `DestinationOrigin` overrides on 2-leg Rails (rail-level `Origin` becomes optional shorthand). |
| **XOR groups** | `xor_group:` field on ChainEntry — "exactly one of" chain semantics. |
| **Union roles** | `(RoleA \| RoleB)` syntax in Rail role expressions. |

### Layer 2 — existing primitives, modified

| Change | Detail |
|---|---|
| **Instance Prefix** | Format pinned: `^[a-z][a-z0-9_]*$`, max 30 chars |
| **AccountTemplate.ParentRole** | MUST resolve to a singleton Account (no template-under-template) |
| **Rails — explicit shape** | Two-leg (`source_role` + `destination_role` + `expected_net`) vs single-leg (`leg_role` + `leg_direction`); was implicit before |
| **LegDirection Variable** | New value — leg amount and direction set by Transfer's net-zero requirement; must be the LAST leg posted on its Transfer |
| **Reversals** | Documented as Rails in XOR groups with their success counterparts (NOT a separate primitive) |

### Vocabularies (new, fixed v1)

| Vocab | Forms |
|---|---|
| `CadenceExpression` | `intraday-Nh`, `daily-eod`, `daily-bod`, `weekly-<weekday>`, `monthly-eom`, `monthly-bom`, `monthly-<day>` |
| `CompletionExpression` | `business_day_end`, `business_day_end+Nd`, `month_end`, `metadata.<key>` |
| `BundleSelector` | `TransferType`, `RailName`, `TransferTemplateName`, `TransferTemplateName.LegRailName` |
| **YAML keys** | PascalCase types ↔ snake_case YAML keys (e.g., `SourceRole` → `source_role`) |

### Removed / deferred

- **Scope predicates** — dropped (Roles + typed Account fields cover the cases).
- **Per-leg Origin** was deferred in earlier drafts; now in v1.

### Validation rules (16, all load-time)

Listed verbatim in the SPEC's "Validation rules" subsection — each is one test case and one error path.

---

## Suggested M.1a work clusters

Grouped so each cluster is roughly one PR / one implementer's chunk.

**A. L1 schema migration**
- New columns: `transactions.bundle_id`, `transactions.supersedes`, `stored_balances.supersedes`
- Default-value migration for existing rows (`Status = Posted`, others NULL)
- Index on `(rail_name, status, bundle_id)` for bundler queries

**B. Status lifecycle + Higher-Entry semantics**
- Append-only superseding logic with `Supersedes` field enforcement
- Pending → Posted transition validation (uses Cluster D's PostedRequirements)
- Audit-view rendering that distinguishes Inflight/BundleAssignment/TechnicalCorrection

**C. Per-leg Origin resolution**
- Resolution rules from `Origin` / `SourceOrigin` / `DestinationOrigin`
- Posting-time application to each leg's Transaction.Origin
- Validation: every leg of every rail resolves

**D. PostedRequirements check (posting-time)**
- Auto-derivation from TransferTemplate.TransferKey
- Auto-derivation from chain `Required: true` → parent_transfer_id
- Integrator-declared additions
- Refusal to mark `Status = Posted` if any required field NULL

**E. TransferTemplate machinery**
- Lookup-or-create Transfer ID with uniqueness constraint on `(template_name, transfer_key_values)`
- Multi-leg Conservation evaluation (sum across legs vs ExpectedNet)
- Variable-direction leg ordering enforcement (must be last; sibling legs MUST be Posted)
- Variable amount derivation from sibling legs

**F. Aggregating Rail machinery**
- BundleSelector parser + matching (4 forms)
- Eligible-but-not-bundled query
- Bundle assignment append (higher-Entry with `Supersedes = BundleAssignment`)
- Cadence scheduler (7 vocabulary literals)

**G. Aging watches**
- MaxPendingAge surface as exception view
- MaxUnbundledAge surface as exception view
- Both rendered as dashboard rows with row-level detail (the whole point — escape today's aggregate-text-report problem)

**H. Chain enforcement**
- Orphan check for `Required: true` (with timing relative to parent's Completion)
- XOR group enforcement (missing AND multiple cases)
- Chain `parent` accepts both Rail and TransferTemplate

**I. Vocabulary parsers**
- `CadenceExpression` parser
- `CompletionExpression` parser
- `BundleSelector` parser
- Instance prefix format validator
- All reject unknown literals at load time

**J. L2 load-time validation suite**
- 16 rules from the spec, each as a test case
- One discoverable error message per rule

**K. YAML loader conventions**
- snake_case ↔ PascalCase transliteration
- Block-style enforcement (catch the inline-comma-syntax footgun encountered)

---

## Suggested ordering for M.1a

1. **A** (schema) — foundational, blocks everything else
2. **C, D, I, K** (resolution, validation, parsers, loader) — load-time correctness; can mostly be done in parallel
3. **J** (validation suite) — pulls in A + C + D + I results
4. **B** (higher-Entry semantics) — needed before E and F can append correctly
5. **E** (TransferTemplate) and **F** (Aggregating) — the meatiest runtime work; can be parallel-ish
6. **G** (aging watches) — sits on top of B / D / F
7. **H** (chain enforcement) — sits on top of E

Two PRs minimum (foundational + parsers, then runtime mechanics); three if aging watches land separately.
