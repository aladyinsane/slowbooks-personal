/**
 * First-run warning that shipped guesses have touched the user's books (ADR 0006).
 *
 * The wording is the whole point. We are not bragging about automation -- we are
 * telling the user how much to trust it, and specifically that the dangerous outcome
 * is not an obvious error but a plausible one they scroll past.
 */

interface Props {
  count: number;
  onAcceptAll: () => void;
  onReview: () => void;
  busy: boolean;
}

export function StarterRuleBanner({ count, onAcceptAll, onReview, busy }: Props) {
  return (
    <section className="banner" role="alert" aria-labelledby="starter-heading">
      <h2 id="starter-heading">
        {count} {count === 1 ? "transaction was" : "transactions were"} categorized by a
        starter rule
      </h2>

      <p>
        SlowBooks ships with about 60 common merchant rules — <code>STAPLES</code> →
        Office Supplies, <code>SHELL</code> → Vehicle &amp; Fuel — so your first import
        isn&rsquo;t entirely manual. They are <strong>guesses about your business, and we
        have never seen your business.</strong>
      </p>

      <p className="warn">
        Please check these before accepting. A wrong guess here is easy to miss precisely
        because it looks reasonable — an uncategorized row demands your attention, but a
        plausible-but-wrong one gets a glance and a scroll. <code>SHELL</code> is fuel for
        a contractor and a customer for a chemical supplier.
      </p>

      <p>
        Every starter guess is marked <span className="badge badge-starter">starter rule</span> in
        the list below. When you correct one, SlowBooks remembers your choice and stops
        guessing for that merchant — the badge disappears for good.
      </p>

      <div className="banner-actions">
        <button onClick={onReview} disabled={busy} className="primary">
          Let me review them
        </button>
        <button onClick={onAcceptAll} disabled={busy}>
          {busy ? "Accepting…" : "Accept all starter guesses"}
        </button>
      </div>
    </section>
  );
}
