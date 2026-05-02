# How do I brand my handbook prose?

*Customization walkthrough — Developer / Product Owner. Reskinning + extending.*

## The story

You've pointed the rendered mkdocs site at your own L2 instance
(see [How do I publish docs against my L2?](how-do-i-publish-docs-against-my-l2.md))
and the handbook now reads against your accounts, your rails,
your chains. But the prose still says "Your Institution"
in places where the bundled `sasquatch_pr` fixture would say
"Sasquatch National Bank — SNB" — and where the bundled fixture
would name the Federal Reserve Bank as a stakeholder, your
handbook says nothing. The neutral fallback works, but the
result is colorless.

The fix is one optional YAML block. Add a `persona:` block to
your L2 instance YAML with your institution name + acronym,
upstream stakeholders, GL account display labels, merchant names,
and free-form flavor strings. The handbook templates substitute
those at render time via Jinja `vocab` references — no code
changes, no docs site fork, and skipping the block keeps the
neutral fallback for any L2 that hasn't filled it in yet.

The substitution surface is deliberately small: five typed
fields on one block. The same constraint that keeps the docs
mkdocs build re-renderable per L2 (no hardcoded persona strings
in the generated content) is what makes this walkthrough this
short.

## The question

"My handbook prose says generic placeholder language where
{{ vocab.fixture_name }} would name an actual institution.
Where do I drop in my institution's name, my stakeholders, my
GL account labels?"

## Where to look

Three reference points:

- **Your L2 institution YAML's `persona:` block** — the per-instance
  flavor declaration. See `tests/l2/sasquatch_pr.yaml` for a full
  worked example; `tests/l2/spec_example.yaml` deliberately omits
  the block to exercise the neutral fallback.
- **`src/quicksight_gen/common/persona.py`** — the `DemoPersona` +
  `GLAccount` dataclasses. The field list there is the contract
  for the YAML block.
- **`src/quicksight_gen/common/handbook/vocabulary.py`** — where
  the loaded `DemoPersona` flows into the handbook's
  `HandbookVocabulary` (institution name + stakeholders + GL
  accounts + merchants + flavor literals).

The persona block is OPTIONAL. Omit it and the handbook templates
fall back to neutral prose derived from your L2 primitives
(institution name from `description`, account labels from the
account roster, etc.). Add it when you want the handbook to read
in your institution's voice.

## What you'll see in the demo

`tests/l2/sasquatch_pr.yaml` carries the canonical worked example:

```yaml
persona:
  institution:
    - "Sasquatch National Bank"
    - "SNB"
    # Optional 3rd / 4th elements: region, legacy_entity
  stakeholders:
    - "Federal Reserve Bank"
    - "Fed"
    - "Payment Gateway Processor"
  gl_accounts:
    - code: "gl-1010"
      name: "Cash & Due From FRB"
      note: "Cash & Due From FRB → (e.g., Open Loop Funds Pool)"
    - code: "gl-1810"
      name: "ACH Origination Settlement"
      note: "ACH Origination Settlement → (e.g., Sweep Account for ACH)"
    # ... one entry per GL account you want named in handbook prose
  merchants:
    - "Big Meadow Dairy"
    - "Bigfoot Brews"
    - "Cascade Timber Mill"
    # ... display names for the merchant DDAs the seed plants
  flavor:
    - "Margaret Hollowcreek"
    - "Pacific Northwest"
    - "Farmers Exchange Bank"
    # Free-form: sample customer name, region descriptor, legacy entity
```

Each of the five sub-keys is independently optional and defaults
to an empty tuple. A partial block (just `institution:` filled
in) is valid; the missing keys render as the neutral fallback.

The loader in `common/l2/loader.py::_load_persona` parses the
block into `L2Instance.persona` (a typed `DemoPersona | None`).
`vocabulary_for(l2_instance)` reads it into the handbook's
`HandbookVocabulary` and the templates substitute via
`{{ vocab.institution.name }}`, `{{ vocab.gl_accounts }}`,
`{{ vocab.stakeholders }}`, etc.

## What it means

Each field maps to a concrete handbook surface:

1. **`institution`** — `(name, acronym)` minimum, with optional
   `region` and `legacy_entity` follow-ons. Rendered as
   `{{ vocab.institution.name }}` / `.acronym` / `.region` /
   `.legacy_entity` on every handbook hub page (etl, l1,
   investigation, executives, l2_flow_tracing, customization)
   and the integrator role page. The most-used field by far —
   omit it and the handbook reads "Your Institution" everywhere
   the templates would otherwise name you.
2. **`stakeholders`** — flat list of upstream-counterparty
   display strings. Rendered in handbook prose that talks about
   "settlement authority for ACH, wire, and daily sweep flows"
   etc. Two-element pairs (`["Federal Reserve Bank", "Fed"]`)
   read as full-name + short-name; the handbook prefers the
   short form in body text and falls back to the long form on
   first mention.
3. **`gl_accounts`** — typed `{code, name, note}` entries. Each
   maps to a row in the handbook's chart-of-accounts table; the
   `note` becomes the one-line hint surfaced in the GL account
   description. Omit GL accounts your institution doesn't carry
   — only entries in this list get named in handbook prose.
4. **`merchants`** — display names for merchant DDAs the seed
   plants. Used in handbook prose discussing the
   merchant-acquiring surface (executives + l2 flow tracing).
   Match the names to the merchant accounts in your L2's
   account roster so the handbook + dashboard agree.
5. **`flavor`** — three free-form strings: sample customer
   name (`flavor[0]`), region descriptor (`flavor[1]`), legacy
   entity name (`flavor[2]`). Surfaced as
   `{{ vocab.institution.region }}` and
   `{{ vocab.institution.legacy_entity }}` on the institution
   block. The `flavor[0]` sample customer is reserved for
   future Investigation persona expansion.

Three properties of the substitution to internalize:

- **The block is optional, partial, and additive.** Skip it
  entirely → neutral fallback. Fill in just `institution:` →
  handbook says your name where it would otherwise say "Your
  Institution"; everything else stays neutral. No required
  fields; no validation against your L2's account roster (the
  handbook's job is to read the L2; the persona block is just
  display flavor).
- **It's display-only, not load-bearing.** Nothing in the L1
  invariants, the dashboards, the seed, or the e2e harness
  depends on the persona block. Renaming "Sasquatch National
  Bank" → "ACME Treasury" doesn't change a single SQL query
  or QuickSight visual.
- **Multi-instance friendly.** Each L2 carries its own block.
  Render the docs once against `acme_treasury.yaml`, again
  against `acme_demo.yaml`, and the published sites will read
  in their respective voices without sharing any global state.

## Drilling in

A few patterns to know:

### What the persona block does NOT cover (yet)

The handbook's **Investigation** worked-example admonitions
(`??? example "Worked example: <fixture>"` blocks on the four
question-shaped Investigation walkthroughs) read from a separate
hand-curated `InvestigationPersonaVocabulary` tuple in
`common/handbook/vocabulary.py::_sasquatch_pr_vocabulary`. That's
the named-account narrative — Juniper Ridge LLC + Cascadia Trust
Bank + Shell A/B/C — which is wired by *role* (`convergence_anchor`
/ `counterparty_bank` / `operations_account` / `shell_entity`),
not by display string.

If your L2 plants Investigation scenarios (`inv_fanout_plants`)
and you want a worked-example admonition naming your accounts,
the path today is to add a built-in vocabulary entry alongside
`_sasquatch_pr_vocabulary` (small Python edit). A future
extension will likely lift those role-keyed personas into the
YAML block; for now they live as code.

### Adding the block to your L2 YAML

Pick a top-level location in your YAML — anywhere works, but
right after `description:` reads naturally (it's prose-like
metadata):

```yaml
# acme_treasury.yaml
instance: acme_treasury
description: |
  ACME Treasury — internal cash concentration + customer DDA reconciliation.

persona:
  institution:
    - "ACME Treasury Bank"
    - "ACME"
  stakeholders:
    - "Federal Reserve Bank"
    - "Fed"
  gl_accounts:
    - code: "gl-1000"
      name: "Operating Cash"
      note: "Daily operational cash position"
    - code: "gl-2000"
      name: "Customer Deposits"
      note: "Aggregate customer DDA liability"
  merchants:
    - "Mountain View Coffee"
    - "Riverside Hardware"
  flavor:
    - "Pat Williams"
    - "Mountain West"
    - "Northwest Banking Group"

# accounts: / account_templates: / rails: / etc. follow as usual.
```

### Re-rendering the handbook

After editing your YAML, point `mkdocs build` at it via the
`QS_DOCS_L2_INSTANCE` env var:

```bash
QS_DOCS_L2_INSTANCE=tests/l2/acme_treasury.yaml \
    .venv/bin/mkdocs build --strict
```

The persona-neutral CI gate (`tests/test_docs_persona_neutral.py`)
verifies `spec_example` builds with zero unintentional Sasquatch
tokens — a regression guard you inherit by default. Your own
`acme_treasury` build is unconstrained: whatever you put in the
block gets rendered.

### Verifying your block loaded

Smoke-test the loader in a Python REPL:

```python
from quicksight_gen.common.l2.loader import load_instance
inst = load_instance("acme_treasury.yaml")
print(inst.persona.institution)
# ('ACME Treasury Bank', 'ACME')
```

Or rely on the handbook's own rendering — every page that uses
`{{ vocab.institution.name }}` (the L1 / Executives / Investigation
hubs all do) will name your institution after a successful build.

### Skipping the block entirely

The neutral fallback is a deliberate first-class shape — every
field on `DemoPersona` defaults to an empty tuple, and the
handbook templates' `vocab` Jinja substitutions fall through
to L2-primitive-derived prose ("the bank", "your institution",
account labels from `account.description`). If you're testing a
new L2 and just want the docs to render without flavor, leaving
the block off is the right move.

## Next step

Once your persona block is declared and the rendered docs name
your institution:

1. **Spot-check the three load-bearing surfaces.** Open the
   rendered `handbook/l1/`, `handbook/etl/`, and
   `for-your-role/integrator/` pages. The institution name
   should appear on each; the GL accounts table should match
   your block; the stakeholders should be named in the upstream-
   counterparty prose. These are where a missing or partial
   persona block surfaces most visibly.
2. **Wire the docs build into your CI.** The
   `tests/test_docs_persona_neutral.py` gate is the regression
   surface. Adapt the per-page allowlist if your `acme_treasury`
   handbook intentionally cites another bundled fixture (rare —
   most integrators don't).
3. **Decide whether you want an Investigation worked-example.**
   If your L2 plants `inv_fanout_plants`, the four Investigation
   walkthroughs render their admonitions against the
   `_sasquatch_pr_vocabulary`'s curated personas. To get your
   own narrative there, add a vocabulary entry alongside that
   function in `common/handbook/vocabulary.py`. A future YAML
   extension will probably lift this into the persona block.

## Related walkthroughs

- [How do I publish docs against my L2?](how-do-i-publish-docs-against-my-l2.md) —
  the upstream prerequisite. The persona block is one optional
  enhancement on top of the L2-driven docs render.
- [How do I reskin the dashboards for my brand?](how-do-i-reskin-the-dashboards.md) —
  the sibling theme block that controls dashboard color tokens
  + brand assets. Theme + persona together cover both visual
  + textual rebrand.
- [How do I map my production database to the two base tables?](how-do-i-map-my-database.md) —
  the foundational prerequisite. Persona flavor only matters
  once the docs are rendering against your real data.
