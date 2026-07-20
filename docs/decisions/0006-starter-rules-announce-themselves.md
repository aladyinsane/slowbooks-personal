# ADR 0006 — Starter rules announce themselves

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decided by:** Lauren (product owner)
- **Extends:** [ADR 0005](0005-deterministic-rules-categorization.md) (does not supersede it)

## Context

[ADR 0005](0005-deterministic-rules-categorization.md) ships a **starter rule pack** — about
60 merchant patterns (`STAPLES → Office Supplies`, `SHELL → Vehicle & Fuel`, `STRIPE` credit
→ Sales Revenue, `STRIPE` debit → Merchant Fees) — to fix the cold-start problem. Rules have
a genuinely worse cold start than a model: an empty ruleset categorizes nothing, so import #1
would be entirely manual.

The pack was flagged in review with an objection: **it is a guess about someone else's
business.** `SHELL → Vehicle & Fuel` is right for a contractor and wrong for a chemical
supplier where "Shell" is a customer. And the failure mode is nasty in a specific way:

> Guessing wrong is arguably worse than not guessing, because a plausible-but-wrong category
> is easy to click past.

An uncategorized row *demands* attention. A wrong-but-plausible row **receives** attention
and passes. The pack's whole value is saving clicks — which is exactly the mechanism by which
a bad guess slips through unexamined.

The question raised in review was "what industry is the first user in?", i.e. *how do we make
the guesses better?* That framing was wrong. Any answer is still a guess about a user we
haven't met.

## Decision

**Keep the starter pack, and make it declare itself.** Specifically:

1. **Provenance is tracked.** Every suggestion records *which rule* produced it, so the
   system always knows whether a category came from a starter guess or from something the
   user taught it.
2. **Starter-rule suggestions are visually distinct** from user-rule suggestions, on every
   row, always — not just on first run.
3. **The first time starter rules fire, say so prominently**, in plain language, including
   the warning that a plausible-but-wrong category is easy to miss. Acknowledgement persists.
4. **"Accept all" exists, and carries the warning.** Bulk acceptance is offered because
   principle 5 says never make a human repeat themselves — but it is offered *with* the risk
   stated, not quietly.

## Rationale

The reframing is the point: **we cannot make the guesses reliably right, so we make them
visibly guesses.** That converts an accuracy problem, which we cannot solve for a user we
have not met, into a transparency problem, which we can solve completely and today.

This is principle 8 (*show the work*) doing real work rather than decorating. We already
require every suggestion to explain *why* it fired; this extends it to *how much that
explanation is worth*. "I matched a rule you wrote" and "I matched a guess we shipped" have
very different standing, and collapsing them is what makes a bad guess invisible.

It also keeps the pack's actual value. The objection was never that the pack is useless — it
saves real work on import #1. The objection was that its cost is *silent*. Making it loud
keeps the benefit and removes the trap.

Finally, it degrades correctly. Because user rules already outrank builtins (priority 100 vs.
500 in ADR 0005), a correction permanently retires the guess for that merchant. The badge
disappears on its own as the user teaches the system. **The scaffolding is designed to come
down.**

## Consequences

**Good**

- The dangerous failure mode — plausible, wrong, unexamined — is directly addressed rather
  than mitigated.
- No guess about the user's industry is required, so no wrong bet is possible.
- Provenance is generally useful beyond this: "which rule did this?" is exactly what you want
  when a category looks off, and it's a prerequisite for editing the offending rule in place.
- Honest by construction. We're telling the user how confident to be, which is the thing
  accounting software usually gets wrong in the other direction.

**Bad / accepted costs**

- **More UI on the busiest screen.** Badges and a banner on the grid, which principle 4 says
  must earn their place. Accepted because the alternative is a silent wrong number.
- **A first-run interruption**, which is the moment users are least patient. Mitigated by
  making it one dismissible banner with an "accept all" escape, not a modal wall.
- **Extra schema and plumbing** — `suggested_rule_id`, a `settings` table, a migration —
  where the naive version stored only the resulting account.
- **Badge fatigue.** If most rows are starter guesses on import #1, the badge is on almost
  every row and stops being a signal. Partly self-correcting (badges vanish as rules are
  taught), but worth watching. If it becomes noise, the honest fix is to make the *banner*
  carry the weight and quiet the per-row badge — not to remove the distinction. Tracked
  with mitigation options in
  [future-features.md](../product/future-features.md#known-risks-in-shipped-features).
- **We are choosing to slow the user down** on first import. That is the intended effect, and
  it will read as friction to someone who just wants their books done.

## Alternatives considered

**Drop the starter pack.** Removes the wrong-guess risk entirely and restores the bad cold
start ADR 0005 explicitly accepted the pack to fix. Trades a visible, fixable problem for an
invisible abandonment problem.

**Tune the pack to the user's industry.** The instinct behind the original question. Rejected:
it makes the guess *more* confident without making it *more* checkable, which pushes in
precisely the wrong direction. A better-targeted silent guess is more dangerous, not less.

**Ask the user to opt in to the pack at setup.** Front-loads a decision they lack the context
to make — they haven't seen a transaction yet. Better to show the guesses at the moment
they're applied to real data they recognize.

## Revisit when

- We can measure how often starter suggestions are overridden. A high override rate means the
  pack is miscalibrated for real users; a near-zero rate might mean the badge is being ignored
  and users are rubber-stamping — **and the second is more dangerous than the first.**
