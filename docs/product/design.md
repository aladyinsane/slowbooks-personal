# Visual Design — Calm, document-like

Direction chosen 2026-07-16. This is the reasoning; `frontend/src/index.css` is the
implementation, and its tokens are the single source of truth for values.

## The thesis

QuickBooks is described as *cumbersome*, a *mish-mash of add-ons*, with *nested menus that
make no sense* and pages that take *3–10 seconds*. Strip away the specifics and the
feeling users describe is **anxiety**: a screen that is busy, uncertain, and vaguely
accusatory about work you haven't finished.

So the counter isn't "prettier." It's **calm**. The design goal is that someone opens
their books on a Sunday night and the screen doesn't make their shoulders rise.

The second thesis: **this is a document, not an app.** A ledger is one of the oldest
document forms we have, and it's legible without any chrome at all. We lean on that —
hairline rules, aligned columns, real typography — instead of cards, shadows, and
gradients. Financial records earn trust by looking like records.

## Principles, applied

| Principle | What it forces here |
|---|---|
| **4 — earn the screen** | No decoration. If an element isn't carrying information, it goes. No shadows, no gradients, no card borders around things that aren't cards. |
| **8 — show the work** | Every number traceable, every guess labelled. The badges are the loudest thing on a row *on purpose* ([ADR 0006](../decisions/0006-starter-rules-announce-themselves.md)). |
| **2 — plain language on top** | Type does the explaining. Labels are small and quiet; the values they describe are large and calm. |
| **3 — fast is a feature** | No animation on anything in the bulk path. A 200ms transition × 200 rows is 40 seconds of someone's life. |

## Colour

**Colour means something or it isn't there.** The palette is almost entirely ink on paper;
every hue that survives is doing semantic work.

| Token | Job |
|---|---|
| `--ink`, `--ink-soft`, `--ink-muted` | text hierarchy — three weights of the same idea |
| `--paper`, `--paper-sunk` | background, and the barely-there tint of a grouped row |
| `--rule`, `--rule-strong` | hairlines. The main structural device |
| `--accent` | links and the single primary action per view |
| `--positive` | money in, balanced, reconciled |
| `--negative` | money out, out-of-balance, errors |
| `--caution` | starter-rule guesses, unreconciled gaps, backdated warnings |

Notice `--positive` / `--negative` are **not** "good" and "bad". An expense isn't a
failure. They mean *direction of money*, and the same green means "balanced" only because
balance is also a fact, not a compliment.

`--caution` is amber and appears in exactly three places, all of which are us admitting
uncertainty: a shipped guess, a difference we can't explain, an entry that landed behind a
reconciliation. **Amber is the colour of "we're not sure."** That consistency is what makes
it readable.

## Type

System stack, because a webfont is a download that delays first paint on a *local* app —
which would be absurd given ADR 0001. The design does its work through scale and weight,
not through a typeface nobody consciously notices.

- **Money is always `tabular-nums` and right-aligned.** Non-negotiable. Columns of figures
  that don't align are hard to scan and easy to misread, and misreading is the failure mode
  this whole product exists to reduce.
- **Labels are small, uppercase, wide-tracked, muted.** Values are large and plain. The
  reader's eye should land on the number, not on the word describing it.
- **Line length is capped at ~42rem** for prose. Any explanation we write is worth reading;
  a 100-character measure means it won't be.

## Density

Two densities, deliberately:

- **Decisions get room.** The starter-rule warning, a reconciliation result, the export
  panel. These are moments where someone should slow down, and whitespace is what makes
  them slow down.
- **Data gets tight.** The transaction grid is scanning work. Rows are compact, aligned,
  and quiet.

This is the one place we consciously *don't* pick a single answer, because a grid and a
warning are different kinds of object and pretending otherwise serves neither.

## What we deliberately don't do

- **No shadows or elevation.** Paper doesn't float.
- **No rounded cards around everything.** A border is a claim that things inside belong
  together; most of the time that claim is false and the border is just noise.
- **No animation in the bulk path.** See principle 3.
- **No brand colour on chrome.** The header is not an advertisement. The user's data is the
  only thing worth colouring.
- **No empty-state illustrations.** A friendly cartoon where a number should be is a
  product apologising for having nothing to say.

## Accessibility, as a design constraint rather than an audit

- Colour is never the *only* signal. Every badge has text; every state has a word.
- Focus is always visible — this is a keyboard-heavy task and hiding focus rings to look
  tidier would be choosing our aesthetics over someone's ability to use the thing.
- Contrast meets WCAG AA against `--paper` in **both** schemes. Measured, not assumed:

  | | light | dark |
  |---|---|---|
  | `--ink` | 16.5 | 14.2 |
  | `--ink-muted` (labels) | 4.9 | 4.9 |
  | `--accent` (links) | 6.3 | 8.2 |
  | `--positive` | 6.2 | 8.8 |
  | `--negative` | 6.4 | 6.4 |
  | `--caution` on `--caution-soft` | 5.1 | 8.4 |

  `--ink-muted` is darker than it aesthetically wants to be. The prettier `#7d7970`
  measured **4.26 and failed** — labels are 11px, which counts as normal text, so 4.5 is
  the bar. Checking is the reason we know; it looked fine.
- The warnings are `role="alert"` because they are, in fact, alerts.

## Dark mode

Supported via `prefers-color-scheme`, because a lot of people do their books at night and
we're a desktop-shaped app that should respect the OS.

It's a genuine reversal, not an inverted filter: paper becomes a warm near-black rather
than pure `#000`, and the semantic hues are re-picked for contrast on a dark ground rather
than reused. Reusing them would leave the amber unreadable, which would quietly break
ADR 0006 — the whole point of that badge is that you can't miss it.

## Open questions

- **A serif for financial figures?** Tempting for document feel; risks looking
  old-fashioned rather than calm, and system serifs vary too much across platforms to rely
  on. Not now.
- **Density toggle.** Bookkeepers would want tighter; owners probably wouldn't. Wait for
  someone to ask.
- **Print stylesheet.** A P&L is a thing people print and hand to a bank. Genuinely on-brand
  for "document-like" and currently unhandled. Worth doing before v1.
