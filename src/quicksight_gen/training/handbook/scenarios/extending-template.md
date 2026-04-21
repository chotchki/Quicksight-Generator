# Adding a new scenario

*How to grow this handbook when a team asks a question that isn't
covered yet.*

A scenario is a single operator question, wrapped around one or
more upstream walkthroughs in `docs/walkthroughs/` at the repo
root.
The format is deliberately thin — most of the mechanical detail
lives in the upstream walkthrough, and your scenario frames the
question, points the reader at the right tab, and tells them what
to do with the answer.

## When to add a scenario

Add one when a team asks a question that:

- Is a question a user actually phrases this way (keep the title
  in their voice — "Where's this money?" not "Balance
  drift investigation").
- Has at least one existing upstream walkthrough that answers it.
  If no upstream walkthrough covers the question, open an issue
  for the tool itself *first* — the scenario doesn't help if the
  dashboard doesn't support the trace.
- Comes up often enough that writing it down saves time on
  repeat.

Don't add a scenario for a one-off question; use an ad-hoc email
thread for those.

## File location and naming

- File: `handbook/scenarios/NN-short-slug.md` where `NN` is the
  next unused sequence number (zero-padded two digits). Seed
  scenarios are 01–03; the next you add is 04.
- Slug: kebab-case, short, takes the shape of the question
  ("dollars-in-the-pool", "vouchers-dont-match-sales").
- Register in `handbook/README.md` under the **Seed scenarios**
  list.
- Register in the relevant track's `00-why-this-exists.md` if the
  scenario is specific to one team; otherwise leave it
  cross-linked from the scenarios directory alone.

## The template

Copy this into a new file and fill it in. Delete any section that
isn't load-bearing for this particular question.

```markdown
# [Scenario title — the operator's question, verbatim]

*Seed scenario — [AR | PR] dashboard. [Team or "cross-team"].*

## The story

[2-3 paragraphs framing when this question comes up, what the
current process looks like, why the dashboard answers it faster.
Should feel like a colleague describing the pain in their own
words, not a marketing pitch.]

## The question

"[The question in one sentence, in the operator's voice.]"

[Optional: note on vocabulary — if the SNB demo uses a different
word than the reader's real workflow (e.g., "payment" vs.
"voucher"), call it out here and point at translation-notes.md.]

## Where to look

1. [Open the right dashboard in the demo environment first.]
2. [Which tab(s). Usually Exceptions is the starting point.]
3. [Which KPI / detail table owns this question.]
4. [Relevant filters to apply.]

## What you'll see in the demo

[Short description of the planted data — how many rows, what the
dollar ranges are. Link to the upstream walkthrough for
screenshots and exact values; don't duplicate them here.]

For mechanical details:
- [Upstream walkthrough 1](../../../docs/walkthroughs/...)
- [Upstream walkthrough 2 if applicable](../../../docs/walkthroughs/...)

## What it means

[Interpretation — what are the typical shapes this exception
takes, and what does each shape indicate? Keep it to 3-5 shapes
max; if there are more, cross-link to the upstream walkthrough
which usually has a fuller catalogue.]

## Drilling in

[The specific click-through the operator follows from the
exception row to the underlying answer. Usually 2-4 drill steps.]

## Next step

[What the operator does with the answer. Who they escalate to,
what they tell the customer, etc. Include aging-bucket
guidance if the exception has an aging dimension.]

## Related scenarios & walkthroughs

- [Other scenarios this one is adjacent to]
- [The upstream walkthrough(s) this scenario wraps]
- Background: [relevant concept page(s)]
```

## Checklist before merging a new scenario

- [ ] Title phrased as the operator's question, in their voice
- [ ] Walks the demo environment first, then points at production
- [ ] Uses existing upstream walkthroughs rather than duplicating
      the mechanical detail
- [ ] Aging-bucket guidance included if the exception has one
- [ ] "Next step" names a specific team / action — not a vague
      "investigate further"
- [ ] Registered in `handbook/README.md`
- [ ] Registered in the relevant track's `00-why-this-exists.md`
      if team-specific
- [ ] Any new SNB-specific strings that will need mapping on the
      wiki side are added to `translation-notes.md`
- [ ] Tested end-to-end on the demo QuickSight environment

## Scenarios that might be worth adding later

Based on the team conversations so far, these are candidates if
the questions start coming up:

- "Did we miss a sweep?" — maps to **ACH Origination Non-Zero
  EOD** and **Sweep Target Non-Zero EOD**.
- "Is the Fed seeing something we didn't post?" — maps to
  **Fed Activity Without Internal Post** and **GL vs Fed Master
  Drift**.
- "Why is this customer over their daily limit?" — maps to
  **Sub-Ledger Limit Breach**.
- "Which accounts ended the day negative?" — maps to
  **Sub-Ledger Overdraft**.
- "A merchant's been marked as unpaid for a week — is that
  normal?" — maps to **Did all merchants get paid yesterday?**
  + the merchant's cadence.
