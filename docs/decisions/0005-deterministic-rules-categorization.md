# ADR 0005 — Categorization is deterministic rules first, not a model

- **Status:** Accepted
- **Date:** 2026-07-16

## Context

Categorizing transactions is the core daily work. Research shows the expected behavior is:
auto-categorize, learn from corrections ("when you fix a merchant name, remember it so
future imports get faster"), and flag transfers/refunds/duplicates.

The obvious 2026 instinct is to reach for an LLM or a classifier. Several products do
exactly this.

## Decision

Categorization is a **deterministic rule engine**, evaluated in priority order, where every
suggestion carries a human-readable reason. Rules are created by the user, or proposed by
the system from an observed correction, and are always visible and editable in one place.

No statistical model in v1.

## Rationale

**Explainability is not negotiable here.** Principle 8 says every auto-categorization must
say *why*. `matched rule: description contains "STAPLES" → Office Supplies` is auditable.
"The model was 87% confident" is not — and an accountant cannot defend it in an audit.

**Determinism protects trust.** The same transaction must categorize the same way today and
next March. A model that silently drifts as it retrains makes prior periods irreproducible —
which fights directly with ADR 0004.

**It's genuinely enough.** Bank transactions are highly repetitive. A small business has
maybe 40 distinct merchants. After one month of corrections, rule-based coverage is very
high — and the *shape* of the value ("month two is 4× faster than month one") comes from
memory, which rules provide completely.

**Speed.** Principle 3's <100ms budget. Rules are a regex scan over a few hundred rows —
microseconds. An LLM call is a network round-trip we'd be reintroducing after ADR 0001
deliberately removed the network.

**Privacy.** ADR 0001 promises financial data never leaves the machine. Sending transaction
descriptions to an API silently breaks that promise, which is our whole market position.

**Cost.** A local-first app with no subscription cannot absorb per-transaction API costs.

## Consequences

**Good**

- Fast, free, private, explainable, deterministic, testable. Rules are trivially unit
  tested; a model needs an eval harness.
- The user can read and edit the entire logic. Full ownership of behavior, matching our
  ownership-of-data stance.

**Bad / accepted costs**

- **Cold start is worse.** A fresh user with no rules gets less magic on import #1 than a
  model-based competitor would. Mitigated by shipping a starter rule pack for common
  merchants (Amazon, Shell, Staples, USPS, Square, Stripe…) and by ranking uncategorized
  rows by frequency so fixing the top 10 covers most of the file.
- **Won't generalize.** A model might infer that an unseen coffee shop is Meals &
  Entertainment. Rules won't.
- **Rules can conflict**, and priority ordering is a concept the user must eventually meet.
  Mitigation: highest-priority match wins, and the UI always shows which rule fired.
- **Ambiguous descriptors are hard.** `SQ *` prefixes cover wildly different businesses.

## The door we're leaving open

This is "not now," not "never." A defensible later position: a **local** model (or an
optional, explicitly opt-in cloud call) that *proposes a rule* rather than categorizing a
transaction directly. The output stays a deterministic, inspectable, editable rule — so the
ledger's explainability is preserved and the model is a suggestion engine at the edge, not
an oracle in the core.

That framing keeps every principle intact. If we ever add ML, it should be through that
door.

## Revisit when

- We have real usage data showing what fraction of transactions rules actually cover.
- Cold-start friction is a measured complaint rather than a hypothesis.
