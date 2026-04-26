# QuickSight Analysis Generator — Spec - Starting Phase M Delivery

## Overall Goal

Help integrators generate AWS QuickSight dashboards that help non-technical financial users find and triage problems in their unique institution. This consists of a shared common library that wraps the QuickSight JSON and a series of example applications built on top that are easily customizable to the situation.

## The Problem with the Application as of Today
The users described below can understand in the abstract the value this application provides. However they cannot make the mental leap to understand how it applies to their scenario because all the training material AND test data is oriented around the demo scenario. 

## Architecture Layers

The SPEC is organized in two layers:

- **LAYER 1 — Universal model**: The Domain Model v2 below. Money, accounts, transfers, transactions, balances, and the invariants they obey. Same for every institution. Shipped as library code. Integrators do not modify.
- **LAYER 2 — Institutional model**: Per-integrator description of this institution's account roles, transfer rails, business processes, and reconciliation expectations. Defined by the integrator as data (the graph YAML). The library reads it to scope LAYER 1 constraints to the institution's specifics, generate seed data, and render handbook prose.

LAYER 1 SHAPES are rigid (Conservation is Conservation); LAYER 1 SCOPES (which TransferTypes have `ExpectedNet=0`, which accounts have `ExpectedEODBalance` set, etc.) are filled in by LAYER 2. LAYER 2 itself is fully defined by the integrator — the library has no opinion beyond providing the LAYER 1 building blocks to express it.

Today's apps map roughly: AR is the showcase of LAYER 1 (most checks are direct L1 invariants); PR is the showcase of LAYER 2 (the sale → settlement → payment → external_txn pipeline IS the institution's specific business process); Investigation is almost entirely LAYER 2; Executives aggregates over both.

## Notation Conventions

- **Type definition**: `TypeName: (Field: Type, OptionalField?: Type)` — both field names and types are PascalCase. A bare type name in a tuple is shorthand for a same-named field: `(ID, Name?)` ≡ `(ID: ID, Name?: Name)`.
- **Type as set of values**: `TypeName ⊇ {member, …}` for open sets (the system uses at least these; more may exist); `TypeName = {member, …}` for closed sets (the universe is fixed).
- **Set filter**: `TypeName(Field = value, …)` denotes the subset of `TypeName` instances where each named field equals the given value. The set name is the type name (no plural).
- **Field access**: `instance.Field`. When a parameter would shadow a type name, prefix with `in` (e.g. `inAccount: Account`).
- **Operators** (all binary operators take surrounding spaces):
  - **Comparison**: `=`, `≠`, `≤`, `≥`, `<`, `>` — standard numeric / value comparison.
  - **Set notation**: `x ∈ S` ("x is in S"); `A ⊆ B` ("A is a subset of B"); `A ⊇ B` ("A contains B" — used for open enums: "at least these members").
  - **Logic**: `¬P` ("not P"); `∃ x ∈ S where P` ("some x in S satisfies P").
  - **Aggregation**: `Σ S.Field` (sum of `.Field` across every element of S); `max S.Field` (largest such value); `|x|` (absolute value of x); `x between A and B` (shorthand for `A ≤ x ≤ B`).
  - **Definition**: `Foo := expression` defines `Foo` as the named expression (used by theorems).
- **Constraint strength**: MUST and SHOULD per RFC 2119. MUST = a hard invariant the system relies on; SHOULD = an expected condition whose violation surfaces as a dashboard exception.
- **Implementation entity composition**: `EntityA + EntityB` denotes a denormalized merge — every row of the implementation entity physically carries all fields of both component entities on a single row, no JOIN required at query time.

## Domain Model v2 - Layer 1

### Primitives (Axioms)

Identity & labels:
- `Entry`: ordered sequence
- `ID`: opaque identifier
- `Name`: human-readable label
- `Value`: human-readable string
- `Scope` = {Internal, External}

Money:
- `Currency`: ISO 4217 code; the system is pinned to a single `Currency`
- `Money`: signed Decimal to 2dp in `Currency`
- `Direction` = {Debit, Credit}
- `Amount`: (Money, Direction)
  - INVARIANT: `Money ≥ 0` if `Direction = Credit`; `Money ≤ 0` if `Direction = Debit`

Time:
- `Timestamp`: instant in UTC (integrators convert at the boundary)
- `BusinessDay`: (StartTime: Timestamp, EndTime: Timestamp)

Transfer machinery:
- `Status` ⊇ {Posted}
- `TransferType` ⊇ {Sale}
- `Origin` ⊇ {InternalInitiated, ExternalForcePosted}
- `Metadata`: `Map[Name, Value]`

Entities:
- `Account`: (ID, Name?, Parent?: Account, Scope, ExpectedEODBalance?: Money)
- `Transfer`: (ID, Completion: Timestamp, TransferType, Parent?: Transfer, ExpectedNet?: Money)
- `Transaction`: (Entry, ID, Account, Amount, Status, Posting: Timestamp, Transfer, Origin, Metadata)
- `StoredBalance`: (Entry, Account, BusinessDay, Money, Limits?: Map[TransferType, Money])

Expected Implementation Entities:
- `DailyBalance`: `StoredBalance` + `Account`
- `StoredTransaction`: `Transaction` + `Transfer`

### Derivatives (Theorems)
- `CurrentTransaction` := `{ tx ∈ Transaction : tx.Entry = max(Transaction(ID = tx.ID).Entry) }`
- `CurrentStoredBalance` := `{ sb ∈ StoredBalance : sb.Entry = max(StoredBalance(Account = sb.Account, BusinessDay = sb.BusinessDay).Entry) }`
- `ComputedBalance(inAccount: Account, inBusinessDay: BusinessDay)` := `Σ CurrentTransaction(Account = inAccount, Status = Posted, Posting ≤ inBusinessDay.EndTime).Amount.Money`
- `Drift(inAccount: Account, inBusinessDay: BusinessDay)` := `CurrentStoredBalance(Account = inAccount, BusinessDay = inBusinessDay).Money − ComputedBalance(inAccount, inBusinessDay)`
- `LedgerDrift(inAccount: Account, inBusinessDay: BusinessDay)` := `CurrentStoredBalance(Account = inAccount, BusinessDay = inBusinessDay).Money − ( Σ CurrentTransaction(Account = inAccount, Status = Posted, Posting ≤ inBusinessDay.EndTime).Amount.Money + Σ CurrentStoredBalance(Account.Parent = inAccount, BusinessDay = inBusinessDay).Money )`
- `NetOfTransfer(inTransfer: Transfer)` := `Σ CurrentTransaction(Transfer = inTransfer, Status = Posted).Amount.Money`
- `IsParent(inAccount: Account)` := `∃ child ∈ Account where child.Parent = inAccount`
- `OutboundFlow(inAccount: Account, inTransferType: TransferType, inBusinessDay: BusinessDay)` := `Σ |CurrentTransaction(Account = inAccount, Transfer.TransferType = inTransferType, Amount.Direction = Debit, Status = Posted, Posting between inBusinessDay.StartTime and inBusinessDay.EndTime).Amount.Money|`


### System Constraints

- **Conservation**: For every `t: Transfer` where `t.ExpectedNet` is set, `Σ CurrentTransaction(Transfer = t, Status = Posted).Amount.Money` SHOULD equal `t.ExpectedNet`. (Single-leg transfers leave `ExpectedNet` unset and are exempt; standard double-entry transfers set `ExpectedNet = 0`.)
- **Timeliness**: For every `tx: CurrentTransaction`, `tx.Posting ≤ tx.Transfer.Completion` SHOULD hold. Remediation is append-only — a violation (or any other Conservation-breaking condition) is corrected by posting a new Transaction against the same Transfer, not by amending the offending one.
- **BusinessDay enclosure**: For every `tx: CurrentTransaction` where `tx.Account.Scope = Internal`, there MUST exist `sb: CurrentStoredBalance(Account = tx.Account)` such that `sb.BusinessDay.StartTime ≤ tx.Posting ≤ sb.BusinessDay.EndTime`.
- **Non-negative stored balance**: For every `sb: CurrentStoredBalance`, `sb.Money` SHOULD be `≥ 0`.
- **Sub-ledger drift**: For every `sb: CurrentStoredBalance` where `sb.Account.Scope = Internal` and `¬IsParent(sb.Account)`, `Drift(sb.Account, sb.BusinessDay)` SHOULD equal `0`.
- **Ledger drift**: For every `sb: CurrentStoredBalance` where `sb.Account.Scope = Internal` and `IsParent(sb.Account)`, `LedgerDrift(sb.Account, sb.BusinessDay)` SHOULD equal `0`.
- **Parent balance existence**: For every `sb: CurrentStoredBalance` where `sb.Account.Parent` is set, there MUST exist `CurrentStoredBalance(Account = sb.Account.Parent, BusinessDay = sb.BusinessDay)`.
- **Expected EOD balance**: For every `sb: CurrentStoredBalance` where `sb.Account.ExpectedEODBalance` is set, `sb.Money` SHOULD equal `sb.Account.ExpectedEODBalance`.
- **Limit breach**: For every `sb: CurrentStoredBalance` where `sb.Limits` is set, for every `(t, limit) ∈ sb.Limits`, for every child `c ∈ Account(Parent = sb.Account)`, `OutboundFlow(c, t, sb.BusinessDay)` SHOULD be `≤ limit`. (Limits live on the parent's `StoredBalance` and apply to each child individually — not aggregated across children.)
- **Immutability**: Every `Transaction` and `StoredBalance` entity is immutable. Violations of constraints should be repaired by posting additional transactions. System errors may be corrected (but not hidden) by entering a higher entry.

### Design Principles

- **Metadata promotion**: `Metadata` is opaque to System Constraints and Theorems — it carries values for display and integrator-defined filtering only. If a rule (a constraint, theorem, invariant, or scenario predicate) needs to read a value to evaluate, that value MUST be promoted out of `Metadata` into a typed field on the bearing entity. The set of typed fields is the set of load-bearing values; everything in `Metadata` is observational.
- **Technical vs business correction**:                                                                                            
  - **Technical errors** (upstream wrote the wrong row — wrong amount, wrong Account reference, wrong Parent, wrong StoredBalance number) are corrected by appending a higher-Entry row that supersedes the offending one. The superseded row stays visible for audit.                                                                                        
  - **Business-process failures** (a real-world event went wrong — a wrong transfer was actually executed, a leg never posted, a balance ended overdrawn) are corrected by posting additional Transactions against the same Transfer. The original Transaction(s) stay as-is — they record what actually happened in the business.    
- **Account dimension is read-only**: This system reads accounts from upstream and uses their typed structural attributes (`Scope`, `Parent`, `ExpectedEODBalance`) to evaluate constraints. It does not provide tools to create, modify, or audit accounts. `Account.Name` is a human-convenience display label and is not load-bearing for any constraint or theorem.
- **Implementation**: Entities are stored in an append-only format with an automatically-incrementing `Entry` id. Technical-error remediation MUST insert a new entity with a higher `Entry` id than the error's.

# Domain Model — Layer 2 (Institutional Model)

## Purpose

LAYER 2 captures the integrator's institution: which accounts exist, what kinds of money movement the institution operates, how those movements relate, and what constraints apply. The library reads it to:
- Scope LAYER 1 invariants to the institution's specifics.
- Drive deterministic seed-data generation that exercises every declared rail.
- Render handbook prose against the institution's vocabulary.

LAYER 2 is fully defined by the integrator. The library has no opinion on its content beyond providing the LAYER 1 building blocks (`Account`, `Transfer`, `Transaction`, `StoredBalance`, `ExpectedNet`, etc.) the integrator's L2 expresses against.

## Notation

Conventions match LAYER 1:
- `TypeName: (Field: Type, OptionalField?: Type)` — both field names and types are PascalCase.
- `TypeName ⊇ {a, b}` — open enum (system uses at least these; integrators may extend).
- MUST and SHOULD per RFC 2119.
- **YAML key convention.** SPEC type and field names are PascalCase; the YAML representation transliterates them to snake_case (`SourceRole` → `source_role`, `TransferKey` → `transfer_key`, `LegRails` → `leg_rails`). Role / Rail / Template *names* themselves stay PascalCase as identifiers — they're values, not keys.

## How L2 plugs into L1

L2 declares the integrator's institution against L1's primitives. The L1 hooks L2 reaches for:

| L1 element | L2 contribution |
|---|---|
| `Account` | Declared per-instance and per-template by L2. |
| `TransferType` (open enum) | L2 contributes members. |
| `Transfer.ExpectedNet` | Set by L2 — per-Rail (standalone Transfers) or per-TransferTemplate (shared multi-leg Transfers). |
| `Transfer.Completion` | Set by L2 — per-Rail or per-TransferTemplate. |
| `Transaction.Account` | Resolved per leg from the firing Rail's `SourceRole` / `DestinationRole` / `LegRole`. When the role comes from an AccountTemplate, the concrete account instance is selected at posting time from the leg's Metadata. |
| `Transaction.Origin` | Declared per-Rail. |
| `Transaction.Metadata` | L2 declares the key set per Rail; values remain opaque runtime data. |
| `Transaction.Status` (open enum) | L2 does NOT contribute. Status is runtime/upstream-determined (Posted, Pending, Cancelled, etc.) and reflects state, not structure. |
| `StoredBalance.Limits` | Populated from L2's Limit Schedules. |

L2 contributes no invariants of its own. All checks reduce to L1 invariants firing on data L2 has shaped.

## Primitives

### Instance Prefix *(required)*

A short SQL-identifier-safe string declared once at the top of the L2 instance. Applied to every generated database object and dashboard resource ID.

```
InstancePrefix: Identifier
```

**Format**: MUST match `^[a-z][a-z0-9_]*$` (lowercase start, alphanumeric or underscore thereafter), max 30 characters. The lowercase-only constraint avoids Postgres' quoted-vs-unquoted-identifier hazard; the 30-character cap leaves room for the longest table-name suffix within Postgres' 63-character identifier limit.

Two L2 instances coexist in one database by using distinct prefixes; cross-instance JOINs are not supported.

Prefix-based isolation (over Postgres schemas) is the default because not all deployment environments grant `CREATE SCHEMA` rights to the library's runtime; bare table/view name prefixing works everywhere.

---

### Roles *(open vocabulary)*

```
Role: Identifier
```

An integrator-defined label for an Account or class of Accounts. Roles serve two purposes:

1. **Stable handle for Rails to reference accounts.** A Rail that says `SourceRole: ConcentrationMaster` is more portable than `SourceAccount: gl-1850`, particularly when the referenced account comes from an AccountTemplate (many runtime instances of the same role).
2. **Class label for templates.** `Role: CustomerSubledger` lets thousands of customer-instance accounts share one declared shape.

Roles are open: the integrator declares whichever labels are useful. The library has no built-in roles.

---

### Accounts *(required: list of L1 `Account`)*

1-of-1 accounts that exist exactly once in the institution. Each entry MUST populate the L1 required fields and SHOULD populate optional fields where they apply.

```
Account: (
  ID,
  Name?,
  Role?: Role,
  Scope,
  ParentRole?: Role,
  ExpectedEODBalance?: Money,
)
```

Notes:
- `ParentRole` references the parent by Role rather than by ID, so parent accounts that come from AccountTemplates are expressible. The library resolves `ParentRole` to a concrete L1 `Account.Parent` reference at materialization time.
- An Account whose `Role` is unique resolves any Rail reference to that role unambiguously.

---

### Account Templates *(optional: list)*

A class of accounts that exists in many instances at runtime — one per customer, one per location, one per merchant. Declares the shape; concrete instances are materialized by the integrator's seed/ETL process.

```
AccountTemplate: (
  Role,
  Scope,
  ParentRole?: Role,
  ExpectedEODBalance?: Money,
)
```

When a Rail references a Role provided by an AccountTemplate, the Rail describes the SHAPE; the specific account instance for a given posting is selected at posting time, typically from the Transaction's Metadata (e.g., `customer_id`).

#### Constraints

- **Singleton parent only.** `ParentRole` MUST resolve to a singleton `Account`, never to another `AccountTemplate`. Template-under-template nesting is forbidden because the per-instance parent assignment becomes ambiguous (which of N parent-template instances does a given child-template instance roll up to?). If per-customer subledger nesting is needed, model it by carrying `customer_id` as Metadata on a singleton-parented subledger rather than nesting accounts.
- **Name handling.** Concrete-instance `Name` is integrator-supplied at materialization time (typically by the ETL/seed process). If not provided, the materialized `ID` is used as the display Name. AccountTemplate itself doesn't declare a name pattern — the library doesn't synthesize names from metadata.

---

### Rails *(required: list)*

A canonical leg-pattern the institution operates. Each Rail produces one or two `Transaction` legs per firing.

```
Rail: (
  Name,
  TransferType,                          # extends L1 TransferType
  Origin,                                # extends L1 Origin
  MetadataKeys: [Identifier, …],         # which Metadata keys legs populate

  # Shape — exactly one of the two groups below:

  # (a) Two-leg
  SourceRole?: RoleExpression,           # debit leg's account
  DestinationRole?: RoleExpression,      # credit leg's account
  ExpectedNet?: Money,                   # required when this rail fires standalone Transfers

  # (b) Single-leg
  LegRole?: RoleExpression,
  LegDirection?: {Debit, Credit, Variable},

  # Optional flags
  Aggregating?: Boolean,                 # see Aggregating Rails below
  BundlesActivity?: [TransferType | Name, …],
  Cadence?: CadenceExpression,
)

RoleExpression: Role | (Role | Role | …)   # union role; see below
```

#### Two-leg rails
Declare both `SourceRole` (debit leg) and `DestinationRole` (credit leg). When fired as a standalone Transfer, `ExpectedNet` MUST be set (typically `0`); L1 Conservation enforces `Σ legs = ExpectedNet`. When the rail is a leg-pattern of a TransferTemplate, `ExpectedNet` lives on the template, not the rail.

#### Single-leg rails
Declare `LegRole` and `LegDirection`. Per L1, the resulting Transfer leaves `ExpectedNet` unset and is exempt from Conservation in isolation. Single-leg rails (with `Aggregating: false`) MUST be reconciled by EITHER:
- A `TransferTemplate` whose `LegRails` includes this rail (the shared Transfer's `ExpectedNet` provides closure via Conservation + Timeliness), OR
- An `AggregatingRail` whose `BundlesActivity` includes this rail's `TransferType` (periodic reconciliation closes the drift).

A non-aggregating single-leg rail that is neither a leg-pattern of a TransferTemplate nor reconciled by an AggregatingRail is a configuration error — the drift it introduces would persist forever.

**Single-leg aggregating rails are exempt from this rule** — they ARE the reconciliation mechanism (sweeping their drift into an External counterparty by design, per the Aggregating Rails section). They do not themselves appear in another rail's `BundlesActivity`.

#### `LegDirection = Variable`
Both the leg's amount AND direction are determined at posting time by surrounding context — specifically, by the requirement that a containing TransferTemplate's `ExpectedNet` hold given the other legs already posted. A "settlement" leg that posts whatever amount/direction closes the bundle is the canonical case.

A TransferTemplate MUST contain at most one Variable-direction leg per shared Transfer. Two or more Variable legs leave the closure under-determined; the library detects this at load-time validation, not at posting.

#### Union roles
`(RoleA | RoleB)` — a Role field MAY express that the rail can target accounts of more than one role. Each firing still resolves to one concrete role per leg; the union is about which roles are admissible, not about firing multiple legs at once.

---

### Aggregating Rails *(Rail variant)*

A Rail with `Aggregating: true` sweeps activity from many other Transfers over a period without being chain-related to any one of them. Pool-to-pool balancing, periodic clearing settlements, EOM interest sweeps.

```
# Same Rail shape as above, plus:
Aggregating: true
BundlesActivity: [TransferType | RailName | TransferTemplateName, …]
Cadence: CadenceExpression
```

`BundlesActivity` is the aggregating-rail equivalent of `Chain` — it expresses which activity the rail rolls up over, in lieu of explicit parent-child chain entries.

#### `BundlesActivity` semantics

A list-element matches activity by union (OR):
- A `TransferType` matches every Transfer of that type.
- A `RailName` or `TransferTemplateName` matches Transfers produced by that specific rail/template.
Both kinds may coexist in one list. A single Transfer that matches multiple list-elements still counts once toward the bundle.

#### `CadenceExpression` vocabulary *(v1)*

| Literal | Meaning |
|---|---|
| `intraday-Nh` | Every N hours during the business day (e.g., `intraday-2h`). |
| `daily-eod` | Once at end of business day. |
| `daily-bod` | Once at start of business day. |
| `weekly-<weekday>` | Once per week on the named weekday (e.g., `weekly-fri`). |
| `monthly-eom` | Once at end of calendar month. |
| `monthly-bom` | Once at start of calendar month. |
| `monthly-<day>` | Once per month on the named day (e.g., `monthly-15`). |

Cadences outside this vocabulary are not recognized in v1; the library rejects unknown literals at load time. Extending the vocabulary is a SPEC change, not an integrator-supplied resolver.

#### Constraints

- An Aggregating rail MUST NOT appear as `Child` in any Chain entry. It runs on the declared cadence, sweeping up activity matching `BundlesActivity` that is eligible but not yet bundled.
- Aggregating rails are typically two-leg, but single-leg aggregating rails are permitted (e.g., a single-leg sweep that lands in an external counterparty).

The library uses `Aggregating: true` to render these rails distinctly from the per-transfer chain DAG and to skip them in chain-validity checks.

---

### Transfer Templates *(optional: list)*

Most Rails fire 1:1 with Transfers (one Rail firing produces one Transfer). Some flows are inherently multi-leg: many Rails firing accumulate as legs into ONE shared Transfer, whose `ExpectedNet` and `Completion` close the bundle.

```
TransferTemplate: (
  Name,
  TransferType,                          # the shared Transfer's TransferType
  ExpectedNet: Money,                    # MUST be set
  TransferKey: [MetadataKey, …],         # values whose equality groups legs onto one Transfer
  Completion: CompletionExpression,      # how Transfer.Completion is derived
  LegRails: [RailName, …],               # which Rails fire as legs into this Transfer
)
```

Semantics: every firing of a `LegRails` rail with the same `TransferKey` values posts to the same shared Transfer.
- L1 Conservation flags the Transfer if its legs don't sum to `ExpectedNet` (catches missing legs, including a missing closing leg).
- L1 Timeliness flags the Transfer if any leg posts after `Completion` (catches late closure).

This is the L2 mechanism that bridges single-leg Rails to L1 enforcement: a single-leg posting that's individually exempt from Conservation IS subject to it as a leg of a TransferTemplate that requires net-zero closure by deadline.

A Rail listed in `LegRails` of a TransferTemplate MUST NOT also fire standalone Transfers — its firings always join the shared Transfer for the matching `TransferKey`.

#### `TransferKey` semantics

`TransferKey` declares which Metadata KEYS participate in the grouping rule (schema-level). The runtime VALUES under those keys remain opaque integrator-supplied data — consistent with L1's Metadata Promotion principle, which governs values, not key declarations.

Behavior with missing/NULL key values: a leg whose Metadata is missing one or more declared `TransferKey` keys (or whose value is NULL) is a posting-time error — the leg cannot be assigned to a shared Transfer. The library reports this as a posting failure, not as silent grouping. Real ETL boundary problems should be caught at load, not absorbed by the L2 model.

#### `CompletionExpression` vocabulary *(v1)*

| Literal | Meaning |
|---|---|
| `business_day_end` | End of the BusinessDay the Transfer was opened. |
| `business_day_end+Nd` | End of the BusinessDay N business days after open (e.g., `business_day_end+3d`). |
| `month_end` | End of the calendar month the Transfer was opened. |
| `metadata.<key>` | Resolves to the Timestamp value at Metadata key `<key>` on any leg of the Transfer. ETL is responsible for pre-computing this value and posting it on at least one leg. |

Expressions outside this vocabulary are not recognized in v1; the library rejects unknown literals at load time.

---

### Chains *(optional: list)*

Parent → child relationships between Rails or Transfer Templates. Used to:
- Validate that a Transfer's L1 `Parent` reference matches an allowed pattern.
- Render multi-stage pipelines.
- Generate orphan checks (every required parent must have a corresponding child).

```
ChainEntry: (
  Parent: RailName | TransferTemplateName,
  Child:  RailName | TransferTemplateName,
  Required: Boolean,
  XorGroup?: Identifier,
)
```

Resolution:
- When `Parent` is a Rail, child Transfers' L1 `Parent` reference points to the parent Rail's Transfer.
- When `Parent` is a TransferTemplate, child Transfers' L1 `Parent` reference points to the shared Transfer (not to any one of its component leg postings).

`Required: true` — every parent Transfer firing SHOULD eventually have at least one matching child Transfer firing. A missing child surfaces as an orphan exception (RFC 2119 SHOULD: violation surfaces as a dashboard exception, not a hard failure).

#### XOR groups

When several chain entries share the same `Parent` AND the same `XorGroup`, exactly one of them SHOULD fire per parent Transfer instance. Without `XorGroup`, multiple `Required: false` children allow any combination including none.

XOR groups capture flows like:
- "Exactly one of {success path, reversal path} happens for an escrow transfer."
- "Exactly one of {ACH payout, voucher payout, internal payout} fires per settlement cycle."

The library evaluates XOR-group membership: missing-firings AND multiple-firings both surface as exceptions when at least one chain entry in the group has `Required: true`. (If all `Required: false` and `XorGroup` is set, it means "at most one" rather than "exactly one.")

#### Reversals

Reversals are not a separate L2 primitive. A reversal is a Rail (typically with the same shape as the original but opposite-direction leg) participating in an XOR group with the success Rail — the success-vs-reversal example above is the canonical pattern.

---

### Limit Schedules *(optional: list)*

Daily caps on outbound flow per `(parent role, transfer type)`. Time-invariant in v1.

```
LimitSchedule: (
  ParentRole: Role,
  TransferType,
  Cap: Money,
)
```

The library projects each LimitSchedule entry into the relevant `StoredBalance.Limits` map; L1's Limit Breach invariant then evaluates per child individually (the cap is per-child, not aggregated across siblings of the parent).

---

### Implementation notes

- Each L2 instance is fully isolated by its `InstancePrefix`. Every generated database object and every dashboard resource ID is prefixed.
- Production integrators typically run one L2 instance under a stable production prefix. Demo and test runs use ephemeral or fixture-specific prefixes so they never collide.
- The library validates the L2 instance at load time:
  - Every `Role` referenced by a Rail or AccountTemplate resolves to either a declared `Account` or an `AccountTemplate`.
  - Every `RailName` in a `TransferTemplate.LegRails` or `ChainEntry` exists.
  - Every `AccountTemplate.ParentRole` resolves to a singleton `Account` (NOT another `AccountTemplate`).
  - Every single-leg Rail is reconciled (TransferTemplate leg or AggregatingRail target).
  - Every TransferTemplate contains at most one `LegDirection: Variable` leg.
  - Every `TransferTemplate.LegRails` entry references a non-Aggregating Rail. (Aggregating rails sweep on a cadence and don't carry the per-instance identity a TransferKey-grouped template needs.)
  - Every `Aggregating: true` Rail is absent from `Child` positions in chains.
  - Every `XorGroup` membership is consistent (all members share `Parent`).
  - Every `Completion` and `Cadence` literal is in the v1 vocabulary.

Configuration errors are reported at load, not at posting time.

---

### Worked example shapes

The shapes below are illustrative, deliberately abstracted. Each demonstrates one primitive in isolation; none describe a real institution.

#### Singleton account
```yaml
- id: clearing-suspense
  name: Clearing Suspense
  role: ClearingSuspense
  scope: internal
  expected_eod_balance: 0
```

#### Account template
```yaml
- role: CustomerSubledger
  scope: internal
  parent_role: CustomerLedger
# Assumes a singleton Account with role: CustomerLedger declared
# elsewhere in the same instance — AccountTemplate.ParentRole MUST
# resolve to a singleton, never to another template.
```

#### Two-leg standalone rail
```yaml
- name: ExternalRailInbound
  transfer_type: ach
  source_role: ExternalCounterparty
  destination_role: ClearingSuspense
  expected_net: 0
  origin: ExternalForcePosted
  metadata_keys: [external_reference, originator_id]
```

#### Single-leg rail (reconciled by a TransferTemplate)
```yaml
- name: SubledgerCharge
  transfer_type: charge
  leg_role: CustomerSubledger
  leg_direction: Debit
  origin: InternalInitiated
  metadata_keys: [merchant_id, customer_id, settlement_period]
  # Reconciled as a leg of MerchantSettlementCycle (TransferTemplate below).
```

#### Single-leg variable-direction rail
```yaml
- name: SettlementClose
  transfer_type: settlement
  leg_role: MerchantLedger
  leg_direction: Variable
  origin: InternalInitiated
  metadata_keys: [merchant_id, settlement_period]
  # Direction determined by the TransferTemplate's net-zero requirement.
```

#### Transfer template
```yaml
- name: MerchantSettlementCycle
  transfer_type: settlement_cycle
  expected_net: 0
  transfer_key: [merchant_id, settlement_period]
  completion: settlement_period_deadline
  leg_rails:
    - SubledgerCharge
    - SubledgerRefund
    - SettlementClose
```

#### Aggregating rail (two-leg, intraday)
```yaml
- name: PoolBalancingNorthToSouth
  transfer_type: pool_balancing
  source_role: NorthPool
  destination_role: SouthPool
  expected_net: 0
  origin: InternalInitiated
  metadata_keys: [bundled_transfer_type, business_day]
  aggregating: true
  bundles_activity: [SubledgerCharge, SubledgerRefund, SettlementClose]
  cadence: intraday-2h
```

#### Chain — XOR group with TransferTemplate parent
```yaml
- parent: MerchantSettlementCycle
  child: MerchantPayoutACH
  required: false
  xor_group: PayoutVehicle
- parent: MerchantSettlementCycle
  child: MerchantPayoutVoucher
  required: false
  xor_group: PayoutVehicle
- parent: MerchantSettlementCycle
  child: MerchantPayoutInternal
  required: false
  xor_group: PayoutVehicle
# Exactly one of the three vehicles fires per settlement cycle.
```

#### Chain — fan-out (one parent, many children)
```yaml
- parent: BatchInbound
  child: PerRecipientCredit
  required: true
# The required-true on a one-to-many fan-out means at least one child
# must fire (typical: many fire, one per item in the batch).
```

#### Limit schedule
```yaml
- parent_role: NorthPool
  transfer_type: ach
  cap: 5000.00
```

#### End-to-end: a complete merchant-acquiring instance

The fragment below shows every primitive composed into one coherent declaration — an abstract "merchant acquiring" pipeline where customers charge against subledgers, refunds and settlements net per merchant period, and a single payout vehicle drains each settled merchant.

```yaml
instance: example_acquirer

# ---- Singleton accounts -----------------------------------------------------
accounts:
  - id: north-pool
    role: NorthPool
    scope: internal

  - id: south-pool
    role: SouthPool
    scope: internal

  - id: clearing-suspense
    role: ClearingSuspense
    scope: internal
    expected_eod_balance: 0

  - id: ext-counter
    role: ExternalCounterparty
    scope: external

# ---- Account templates (multi-instance) -------------------------------------
account_templates:
  - role: CustomerSubledger
    scope: internal
    parent_role: SouthPool

  - role: MerchantLedger
    scope: internal
    parent_role: NorthPool

# ---- Rails ------------------------------------------------------------------
rails:
  # Leg patterns of MerchantSettlementCycle (single-leg)
  - name: SubledgerCharge
    transfer_type: charge
    leg_role: CustomerSubledger
    leg_direction: Debit
    origin: InternalInitiated
    metadata_keys: [merchant_id, customer_id, settlement_period, settlement_period_end]

  - name: SubledgerRefund
    transfer_type: refund
    leg_role: CustomerSubledger
    leg_direction: Credit
    origin: InternalInitiated
    metadata_keys: [merchant_id, customer_id, settlement_period, settlement_period_end]

  - name: SettlementClose
    transfer_type: settlement
    leg_role: MerchantLedger
    leg_direction: Variable
    origin: InternalInitiated
    metadata_keys: [merchant_id, settlement_period, settlement_period_end]

  # Standalone two-leg rails (vehicles)
  - name: MerchantPayoutACH
    transfer_type: ach
    source_role: MerchantLedger
    destination_role: ExternalCounterparty
    expected_net: 0
    origin: InternalInitiated
    metadata_keys: [merchant_id, settlement_period]

  # Aggregating rail (closes pool drift caused by single-leg activity)
  - name: PoolBalancingSouthToNorth
    transfer_type: pool_balancing
    source_role: SouthPool
    destination_role: NorthPool
    expected_net: 0
    origin: InternalInitiated
    metadata_keys: [bundled_transfer_type, business_day]
    aggregating: true
    bundles_activity: [SubledgerCharge, SubledgerRefund, SettlementClose]
    cadence: intraday-2h

# ---- Transfer template ------------------------------------------------------
transfer_templates:
  - name: MerchantSettlementCycle
    transfer_type: settlement_cycle
    expected_net: 0
    transfer_key: [merchant_id, settlement_period]
    completion: metadata.settlement_period_end
    leg_rails:
      - SubledgerCharge
      - SubledgerRefund
      - SettlementClose

# ---- Chains -----------------------------------------------------------------
chains:
  - parent: MerchantSettlementCycle
    child:  MerchantPayoutACH
    required: true

# ---- Limit schedules --------------------------------------------------------
limit_schedules:
  - parent_role: SouthPool
    transfer_type: charge
    cap: 5000.00
```

What this composes:
- **Charges** debit individual customer subledgers as they happen; **refunds** credit them. Both fire as legs of the per-(merchant, settlement_period) shared Transfer.
- At period end, **SettlementClose** fires once per merchant with the net amount and direction needed to bring the shared Transfer to `ExpectedNet=0`. L1 Conservation flags the Transfer if SettlementClose never fires; Timeliness flags it if any leg posts after the period's `settlement_period_end`.
- **PoolBalancingSouthToNorth** runs every 2 hours, sweeping the pool drift the single-leg charges/refunds/settlements have created.
- After SettlementClose, the **MerchantPayoutACH** Transfer (chained to the MerchantSettlementCycle Transfer) drains the merchant's accumulated balance to the external counterparty.

---

### Deliberately not in v1

- **Scope predicates.** Earlier drafts considered named groups of accounts/types for scoping L1 constraints. With Roles + per-account typed L1 fields (ExpectedEODBalance, etc.), scope predicates aren't needed in v1. Revisit if a real integrator needs to express something the typed fields can't (e.g., "limit applies only on business days").
- **Failure category catalogue.** Failure shapes (Stuck, Drift, OutOfBounds, etc.) are scenario-declaration concerns, not L2 primitive concerns; they live in a sibling document.
- **Per-leg `Origin`.** The current Rail shape carries `Origin` at the rail level. If real flows surface that need per-leg Origin (e.g., the customer-facing leg is `InternalInitiated` but the funding leg is `ExternalForcePosted`), extend the Rail with an optional per-leg-Origin override. Not needed in v1.
- **Time-varying limits.** Limit Schedules are time-invariant in v1. Per-day or per-window caps await a real integrator requirement.
- **Cross-instance JOINs.** Two L2 instances coexist via prefixing but cannot be queried together. If federated analytics across instances is needed, that's a higher-layer concern.

## Users
Four main audiences, with different needs:

- **Business Analyst / Product Owner (PO)** customizing the apps onto their backends:
  - Need to describe the institution's structure and relationships to other financial partners to the tool so that business relavant training data is generated
  - Need to train the other audiences, a stable business relevant demo system plus a version connected to real data is ideal
- **Integration Engineers**
  - Need to understand the two data source tables that drive this application
  - Have to write ETL processes to regularly populate the tables with data
  - May need to create additional custom applications building upon, extending or transforming the default applications
  - Edit each behavior in one place (DRY)
  - Trust a comprehensive test suite to catch regressions
  - Iterate fast — regenerate + redeploy in one command
  - Reskin via theme presets so the dashboards land inside the host system
- **Non-technical accountants** consuming the dashboards:
  - Job is to find problems and route them to the team that fixes them
  - These dashboards are unfamiliar — plain-English labels, hint text, and Getting Started rich text are critical
  - Strong accounting background; not programmers
  - Need to recognize *when* something needs investigation, not how to fix the broken upstream system
- **Third party stakeholders** consuming the dashboards:
  - Want data for metrics or to support compliance needs
  - They will not be the primary users but the system should be extensible to meet the changing requirements they will bring

## Workflow Ideas
- PO installs `quicksight-gen`, runs `quicksight-gen --help`, sees guideance to start with a demo config.
- PO next runs `quicksight-gen generate config demo > demo.yaml` and a demo config is output.
-  PO is told the demo.yaml needs updates for their environment.
- PO edits the `demo.yaml` and fills in the AWS/postgres connection details from the placeholders at the top.
- PO next runs `quicksight-gen generate dashboards --config demo.yaml --output demo_dir/` and the json/schema/test data are created.
- PO next runs `quicksight-gen apply schema --config demo.yaml --input demo_dir/` and the database schema is (re)populated.
- PO next runs `quicksight-gen apply data --config demo.yaml --input demo_dir/` and the database is (re)populated with test data.
- PO next runs `quicksight-gen apply dashboards --config demo.yaml --input demo_dir/` and quicksight is (re)created.
- PO next runs `quicksight-gen generate training --config demo.yaml` and a demo training site is output with screenshots inserted.
- PO reads the site, understands what the tool can do and next wants to start iterating on their own version.
- PO next runs `quicksight-gen generate config template > my_site.yaml` and an example config is output. PO is told they need to replace placeholders for their environment, relationships and any other needed data.
- Rest of the steps mirror the demo generation/apply steps.

## Current State as of v5.0.2
See README.md, CLAUDE.md and RELEASE_NOTES.md for the current extensive state. To be very clear, the core tool works and is flexible enough to handle almost any business scenario however as is described in the current challenges it is the test and training side that is problematic.

## Current Challenges of v5.0.2
The default application, demo scenarios and test data are tightly coupled and very fragile. The ability to retheme is based on a simple string replacement process but does not enable an implementation team to shape the data and scenarios to their exact business situation while still producing stable training scenarios for the end user.

