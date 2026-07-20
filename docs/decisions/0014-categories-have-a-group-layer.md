# ADR 0014 — Categories get a Group layer, backed by a table

- **Status:** Accepted
- **Date:** 2026-07-20
- **Decided by:** Lauren (product owner)

## Context

`docs/research/personal-finance-landscape.md` found that Mint, Monarch, and Copilot all
organize categories in the same three-layer shape: **Type** (Income/Expense/Transfer,
fixed) → **Group** (Housing, Food & Dining, Transportation — customizable) → **Category**
(Groceries, Restaurants, Coffee Shops). Our chart of accounts had Type → Category only —
a flat list of ~33 accounts ordered by code, with no grouping a user could browse by.

Three questions followed from that gap, all decided together:

1. Add the Group layer? Yes.
2. Does it change how "Profit and Loss"/"Balance Sheet" are named? No — that's a
   separate, unrelated decision (ADR 0015).
3. Where does a Group live: a hardcoded frontend map, or a first-class database table?

This ADR is about question 3, since 1 was already settled by the research and 2 is out
of scope here.

## Decision

**Groups are a table (`groups`: id, name, type), not a hardcoded map.** Every account
gets a nullable `group_id` foreign key. A trigger enforces that a group and its member
accounts share the same type, the same way `accounts.create()`/`update()` already refuse
a type-mismatched statement account.

## Rationale

**Everything else editable in this app is a table, not a constant.** Accounts, rules,
and reconciliations are all rows a user can rename, add to, or retire (ADR 0010, ADR
0005, ADR 0009). A hardcoded `{"Groceries": "Food & Dining"}` map in the frontend would
be the one piece of "your chart of accounts" that isn't actually the user's to change —
directly contradicting the premise of ADR 0010, which exists specifically so a chart
built as a guess about a life we haven't seen doesn't become a life sentence.

**A hardcoded map is also a second source of truth.** If the frontend owns the grouping
and the backend owns the accounts, they can drift the moment someone adds a category
through the API without also updating the frontend's map — a bug class this codebase
otherwise doesn't have, because the backend is the only place chart-of-accounts data
lives.

**The type-consistency trigger matches this codebase's established pattern**: the
balance trigger, the closed-period trigger, and the statement-account type check all
enforce an invariant in the database (or one layer above it) rather than trusting every
caller to remember it. A "Food & Dining" group silently acquiring a revenue account would
be exactly the kind of plausible-but-wrong state principle 6 exists to prevent.

## Consequences

**Good**

- A user can rename a group ("Food & Dining" → "Eating") or move an account to a
  different group the same way they already rename an account — no new mental model.
- Groups seed with sensible defaults (13 groups over 33 accounts) but are never a bet the
  user is stuck with.
- The type-consistency trigger makes an entire class of miscategorization structurally
  impossible rather than merely discouraged.

**Bad / accepted costs**

- **A new table to maintain**, including its own migration path for existing books
  (schema v5 → v6: create `groups`, seed defaults, add `accounts.group_id`, backfill by
  code). This is real, ongoing surface area — the same kind ADR 0009 and ADR 0011 each
  added when they shipped.
- **Ungrouped accounts are a real state to handle**, not an edge case: a user-invented
  account with no code match during migration, or one created without picking a group,
  has `group_id = NULL`. The UI has to render that as "Other," not crash or hide the
  account.
- **No group-management UI ships with this decision** — the backend CRUD (`groups.py`,
  `/groups` endpoints) exists and is tested, but renaming/creating/deleting a group
  through the UI is a deliberate fast-follow, not part of this change. Until then, the
  value is "your categories are visibly organized," not yet "you can reorganize them
  without an API client."

## Alternatives considered

**A hardcoded grouping map in the frontend.** Simplest to ship — no migration, no new
table, no trigger. Rejected: it's the one piece of chart-of-accounts data that wouldn't
be user-editable, and it duplicates information the backend already owns, which drifts.

**Infer groups from account code ranges** (e.g. 6000–6099 is "Housing"). Would need no
new table at all. Rejected: code ranges already carry the *type* invariant (ADR 0010);
overloading them to also carry *group* would mean a user who adds "Pet care" at 6810 has
no way to say which group it's in without us inventing a second numbering convention on
top of the first — worse than just having a `group_id` column.

## Revisit when

- A group-management UI (create/rename/delete/reassign through the screen, not just the
  API) gets built — the backend is ready for it now.
- Real usage shows the default 13 groups are the wrong shape (too coarse, too fine, wrong
  boundaries) — easy to fix since nothing about the decision depends on these specific
  defaults.
- Reports grow group-level subtotals (e.g. "Food & Dining: $412" above the individual
  Groceries/Dining & Takeout lines) — the data's in place for this now, but no report
  currently uses it.
