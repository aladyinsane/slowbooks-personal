# ADR 0001 — Local-first, single-user, one SQLite file

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decided by:** Lauren (product owner)

## Context

The strongest and angriest complaint against QuickBooks is data lock-in and forced
migration — Desktop discontinued, support cutoffs that disconnect bank feeds and freeze
payroll tables on a schedule the customer doesn't control, ~70% price increases, and
migrations users describe as "an absolute nightmare." Commentators name lock-in as the
explicit business rationale: once data is in the vendor's cloud, switching is hard.

Notably, Xero — the best-liked alternative — **also cannot create local backups**. The whole
field has this problem.

## Decision

SlowBooks is **local-first and single-user**. All data lives in **one SQLite file** on the
user's machine, which they can copy, back up, email, or open with any SQLite tool. No login,
no server, no subscription check. The app is a local FastAPI process serving a local React
UI, both bound to localhost.

## Consequences

**Good**

- Delivers the anti-lock-in promise literally rather than rhetorically. "Your books are the
  file at `C:\Users\you\Documents\slowbooks.db`" is a sentence no competitor can say.
- Eliminates an entire class of upfront work: auth, sessions, tenancy, hosting, GDPR
  surface, security review of a network perimeter. We spend that budget on accounting.
- Performance comes free. No network round-trip means our <100ms budget (principle 3) is
  easy rather than heroic. This directly attacks the 3–10s page-load complaint.
- SQLite is genuinely excellent here: transactional, single-file, zero-config, ubiquitous
  tooling, and comfortable well past any small business's transaction volume.
- Privacy is structural. Financial data never leaves the machine because there's nowhere for
  it to go.

**Bad / accepted costs**

- **No multi-device access.** Owner on a laptop and bookkeeper on a desktop cannot share
  live. Mitigation for now: the file is portable and the export is complete. Real
  mitigation is a future sync layer, which is a hard problem we're consciously postponing.
- **No collaboration.** No accountant-logs-in-and-fixes-it workflow. This is a real
  competitive gap, since the accountant is the gatekeeper.
- **Backup is the user's problem.** A local file can be lost to a dead disk. We must ship
  an obvious, nagging, one-click backup — otherwise our headline advantage becomes the
  mechanism by which someone loses their books. **This is the biggest risk in this ADR.**
- **Distribution is harder.** Users must install something. Web apps have no install step.
- **Support is harder.** We can't inspect a broken customer database, which cuts both ways
  (privacy win, support cost).

## Alternatives considered

**Cloud multi-tenant SaaS.** Rejected: it reproduces the exact structure we're criticizing,
and it front-loads months of non-accounting work (auth, tenancy, hosting) before the first
useful feature exists.

**Local-first with cloud-ready architecture.** Offered and not chosen. Worth recording *why
this is fine*: local-first with a clean API boundary is already most of the way there. We're
building a FastAPI HTTP API with a React client over it — the client/server split exists
from day one. The genuinely hard part of going cloud is multi-tenancy in the data model
(row-level `tenant_id` everywhere) and auth, and neither is meaningfully cheaper to
pre-build now than to add later. Speculative generality has its own cost.

**Postgres locally.** Rejected: requires the user to install and run a database server. That
alone would sink adoption, and it buys nothing at single-user scale.

## Revisit when

- Users are asking for accountant collaboration loudly enough that it's blocking sales.
- We've seen a real user lose data to a disk failure (or we're honest that we expect to).
- A sync layer (CRDT, or a hosted-replica model) becomes worth its complexity.
