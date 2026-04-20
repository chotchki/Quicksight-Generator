# How to present this

*Audience — the Product Owner running the cross-training.
One person, presenting to four teams across SNB. Draft; revisit
after the first team session.*

You already know this tool. This page is about landing it with
the people who don't — making sure each team walks away from
their first session believing the dashboard answers their
everyday questions faster than what they do today.

## The premise to hold onto

The teams are not waiting for a training. They are waiting for
**proof**. Everyone has been told, at some point in their career,
that a new tool will replace an escalation they're tired of
running. Most of those promises didn't carry.

The evidence is the **demo environment** — same shape, stable,
already populated with the exception patterns each team cares
about. If the first fifteen minutes of a session walk the team
through their own scenario and produce a specific dollar answer,
the training is done. The rest is reinforcement.

Keep the signal/noise ratio high. Don't explain the AR dashboard
to customer service; don't explain the PR dashboard to
accounting. Each team gets their own track; each track is short.

## Order of presentation, per team

Both operator tracks are structured the same way. Walk it in
order:

1. **Pain framing** (`00-why-this-exists.md` for their track).
   2 minutes, verbal. "Here's what you do today, here's why it's
   slow." You want them nodding before any dashboard comes up.
2. **Dashboard literacy** (`for-accounting/01-dashboard-
   literacy.md`, shared with customer service). 10–15 minutes.
   Filters, drills, saved views, accent-color convention for
   clickable cells. This is the only abstract piece; get through
   it and get to a scenario.
3. **Their scenario** on the demo. 10–15 minutes. Let them drive
   — take the keyboard, walk them through the filter, the
   exception row, the drill. Do not narrate every click; let
   them ask.
4. **Production walk.** Same dashboard, real data. "Now find the
   same shape on yours." Often there is no exception in
   production on the day you present, which is a *good* outcome:
   "this is what a clean dashboard looks like" is a valid
   takeaway.
5. **One follow-up.** Pick a recent escalation they sent to the
   dev team and re-run it on the dashboard in front of them. If
   the answer comes out matching what the devs eventually
   returned, that's the proof.

Total: ~30–45 minutes per team session. Shorter is better.

## Team-specific notes

### Accounting (4 people, AR dashboard)

The team with the highest pain today. They get the longest
single scenario (Scenario 1 — dollars-in-the-pool) because it
covers the broadest class of their questions. Scenario 2 is a
natural follow-up when they ask "but what about specific
transactions, not just balances?"

Expect pushback on *drift* terminology if anyone uses "variance"
or "break" at SNB — it's the same idea, different word. Point at
the translation notes you keep privately if this keeps
surfacing.

### Customer Service (2 people, PR dashboard)

These two will probably pick it up fastest because their
questions are small and concrete. The hook: *next time a
merchant calls, pull up the dashboard while they're on the line
and give them a specific dollar answer before hanging up.* That
single behavior change is the acceptance bar.

Skip the AR dashboard entirely with this team unless someone
asks.

### Developers (~10 people)

Don't present this track the same way. The developers already
know the code — what they need is the framing that their role is
shifting from "run traces on demand" to "keep the feed correct."
Walk them through [for-developers/00-why-this-exists.md](../for-developers/00-why-this-exists.md)
verbally, then point at the upstream [ETL handbook](../../../docs/handbook/etl.md)
for the mechanical detail. Spend the remaining time on the
operator scenarios so they see what the teams will bring to them
going forward ("this question, which used to be a ticket, now
the team can resolve themselves — you'll still get the hard
ones, but they'll come to you already narrowed").

A lunch, not a formal session, usually works better for this
team.

### Your own track (product owner)

The hardest call you'll make is when to *stop* walking a team
through and hand them the keyboard. Err on the side of earlier —
the team that drives the dashboard themselves in the first
session is the team that comes back to it on their own.

## Common objections and the answer

- *"This is just another dashboard — we've had dashboards
  before."* → It isn't a reporting dashboard; it's a *trace*
  tool. Every visible number has a drill to the rows behind it.
  Show the drill, don't describe it.
- *"The data won't be right in production."* → Probably true
  for week one. That's why we built the demo first — learn the
  shape on clean data, find the feed bugs on real data, fix
  them, then run. The ETL team expects this sequence.
- *"I don't have time to learn another tool."* → It replaces a
  workflow that already takes them time (escalating to devs,
  waiting, re-running). The first session is the only overhead;
  after that, each use is faster than the current path.
- *"What if the tool doesn't cover question X?"* → Then we add a
  scenario. [extending-template.md](../scenarios/extending-template.md)
  is the path. Most "not covered" answers turn out to be
  "covered but not yet documented from this angle," which is a
  ten-minute fix.

## What to watch for in the first session

Signals that the training is landing:

- The team member drives the keyboard unprompted.
- They ask about a real production case within the session.
- They notice a scenario their own workflow would benefit from
  that isn't yet written down.
- They escalate the next ticket with a specific `payment_id`
  or `subledger_account_id` instead of a narrative description.

Signals that it isn't:

- They nod through the whole session without taking the
  keyboard.
- They ask for a written SOP / step-by-step handout (a sign
  they don't yet trust the dashboard to be stable enough to
  learn by exploration).
- They say "great, I'll try it next time" — which usually means
  they won't.

If you see the "isn't landing" signals, the fix is usually
*more* dashboard time, not more slides. Schedule a shadow
session for the next real ticket that comes in.

## Follow-up after each session

- Leave them with the link to [handbook/README.md](../README.md)
  and the specific track page for their team.
- Tell them: when a question comes up that the handbook doesn't
  cover, send it to you. A *question the team phrased in their
  own voice* is the input to a new scenario. Track those; the
  handbook grows by listening.
- Check back after a week. One call or one ticket that went
  through the dashboard instead of the escalation path is proof
  the training held.

## What "good" looks like across the program

The cross-training has worked when:

- The developer ticket queue for reconciliation questions is
  measurably smaller.
- Accounting is closing their daily walk without an escalation
  path to the dev team for small-dollar residuals.
- Customer service is resolving most merchant calls on the
  first call.
- New questions the teams raise are being added to the
  handbook as scenarios, not reverting to the escalation path.

You are the one in the loop best positioned to notice those
signals. The teams will not tell you when they've adopted the
tool — they'll tell you when it stops working. Absence of
complaint is a meaningful signal here.
