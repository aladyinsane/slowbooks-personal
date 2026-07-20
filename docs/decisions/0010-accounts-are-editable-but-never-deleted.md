# ADR 0010 — The chart of accounts is editable, but accounts are never deleted

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decided by:** Lauren (product owner)

## Context

We ship a default chart of 36 accounts ([accounts.py](../../backend/slowbooks/accounts.py)).
It's a guess about a business we haven't met — the same objection [ADR 0006](0006-starter-rules-announce-themselves.md)
raised about the starter rule pack, one level up: those rules guess *which* account, this
guesses *what the accounts are*.

Our research is direct about it: a flexible chart of accounts is what lets the software
keep up with a growing business. And the failure of an inflexible one is specific and
familiar — a user whose business needs a category we didn't ship lumps it into a
wrong-but-close bucket, which is exactly the plausible-but-wrong problem ADR 0006 exists
to fight. "Studio rent" filed under "Rent & Lease" is fine. "Studio rent" filed under
"Office Supplies" because there was nowhere better is a number nobody can explain later.

So the chart must be editable. The question is how far.

## Decision

**Rename, add, and hide. Never delete, never renumber.**

| Operation | Allowed | Why |
|---|---|---|
| **Rename** | Yes, freely | A name is a label, not a fact. "Vehicle & Fuel" → "Truck costs" changes nothing about the ledger. |
| **Edit guidance** | Yes | The user knows their business better than our sentence does. |
| **Add** | Yes, type fixed by number range | 1000s asset, 2000s liability, and so on. The range *is* the type — a new expense cannot accidentally become an asset. |
| **Hide (deactivate)** | Yes | A dropdown of 12 relevant accounts beats 36 mostly-irrelevant ones. |
| **Unhide** | Yes | Symmetry: nothing here is a one-way door. |
| **Delete an unused account** | Yes | It has no history, so nothing can break. |
| **Delete a used account** | **No** | It would tear a hole in posted, immutable history. |
| **Renumber** | **No** | The numbering convention is how an accountant reads the chart at a glance. |
| **Change an account's type** | **No** | Its posted balance means something under its current type. |

## Rationale

**"Hide" is the honest verb.** A user who wants an account gone usually means "stop showing
me this," not "erase the six months of history attached to it." Offering Delete and then
refusing it for used accounts would be a worse experience than never offering it — the
button that only sometimes works is the one people learn to distrust. Deleting genuinely
unused accounts *is* allowed, because there's nothing to protect.

**The number range enforcing the type is the good kind of constraint.** It's not us being
strict; it's that `6800` *means* expense. The existing `accounts.create()` already
validates this, and it's the mechanism that makes "add your own category" safe to hand to
someone who has never heard the word "equity."

**Renaming is safe precisely because we store ids, not names.** Every journal line
references `account_id`. Rename freely and history is untouched — which is a property we
get for free from having modeled it properly, and worth noticing.

**Renumbering is where we say no to a real request.** A bookkeeper may well want their own
numbering. But the 1000s/2000s convention is the thing that makes our export legible to a
CPA who has never seen SlowBooks, and legibility to the accountant is the gate we've said
repeatedly we must pass. Renumbering trades a shared language for personal preference.

**Type changes are the subtle one.** Changing 6100 from expense to asset doesn't just
relabel it — it silently moves every historical transaction from the P&L to the Balance
Sheet. Both statements change, retroactively, and nothing warns anyone. Refuse.

## Consequences

**Good**

- The default chart stops being a bet. A user who doesn't recognise our vocabulary can
  make it theirs, which is principle 2 applied to the chart itself.
- Hiding directly improves the categorization screen: fewer, more relevant options in the
  picker means less scanning and fewer wrong-but-close choices.
- Nothing here can break the ledger. Every allowed operation is either cosmetic (rename,
  guidance) or additive (create), and the one destructive operation is gated on having no
  history.
- Rename-safety is free because we reference accounts by id.

**Bad / accepted costs**

- **"Why can't I delete this?" is a real question**, and our answer ("because your books
  reference it") is correct but unsatisfying in the moment. Mitigated by *saying* that,
  specifically, rather than greying a button out.
- **Hidden accounts still appear in reports** if they have a balance — as they must. A user
  may reasonably expect hiding to remove them from the P&L. It doesn't, and can't.
- **We're refusing renumbering**, which some users will want and which is defensible for
  them. We're choosing the accountant's legibility over their preference, and that's a real
  trade rather than an obvious one.
- **More surface on a screen principle 4 says must earn its place.** Accepted because the
  alternative is a chart that fits nobody exactly.
- **The starter guidance is ours, and now editable.** A user who rewrites it can make it
  wrong. That's their right, and it's still better than being stuck with our guess.

## Alternatives considered

**Rename + hide only, no adding.** Safest, and keeps every book on a structure a CPA
recognises instantly. Rejected: the moment a business needs a category we didn't ship,
they're forced into a wrong-but-close bucket — the failure this decision exists to prevent.

**Full control, including delete and renumber.** What a bookkeeper might expect, and what
desktop accounting software offers. Rejected: deleting an account referenced by posted
entries breaks the ledger's integrity, and renumbering breaks the convention the export
relies on. This trades a real safety property for a freedom most owners won't use.

**A "merge accounts" operation** — move all of B's history into A, then retire B. This is
what people actually want when they reach for Delete on a used account, and it's the honest
version of the request. It's also a rewrite of posted history, which ADR 0004 forbids;
doing it properly means reversing and re-posting every affected entry. Real, and deferred.

## Revisit when

- Someone asks to merge two accounts. That's the request hiding behind "delete", and the
  parking lot entry should grow teeth at that point.
- A CPA tells us our numbering convention is wrong, or that renumbering matters more than
  we think.
- Hidden-but-nonzero accounts confuse someone in practice.
