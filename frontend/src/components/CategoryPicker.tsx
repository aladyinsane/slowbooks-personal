import { useEffect, useMemo, useRef, useState } from "react";
import type { Account } from "../lib/api";

/**
 * A searchable category picker with guidance attached.
 *
 * Replaces a native <select> for two reasons the user hit directly:
 *
 *   1. 36 accounts is too many to scan, and a native select can't be filtered.
 *   2. "What does a credit card payment go to?" is a fair question with a non-obvious
 *      answer, and the answer belongs at the moment of choosing rather than in a help
 *      page nobody opens. Principle 2: rigor underneath, plain language on top.
 *
 * Keyboard-first because this is bulk work (principle 5): type to filter, arrows to
 * move, Enter to choose, Escape to back out.
 */

const STOPWORDS = new Set([
  "a", "an", "and", "for", "from", "in", "is", "it", "my", "of", "on", "or", "the",
  "this", "to", "was", "with",
]);

interface Props {
  accounts: Account[];
  value: number | null;
  onChange: (accountId: number | null) => void;
  disabled?: boolean;
  /** The row's own account, which can never be its own category. */
  excludeId?: number;
}

export function CategoryPicker({ accounts, value, onChange, disabled, excludeId }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const selected = accounts.find((a) => a.id === value) ?? null;

  const options = useMemo(() => {
    const usable = accounts.filter((a) => a.id !== excludeId);
    const terms = query
      .trim()
      .toLowerCase()
      .split(/\s+/)
      // People type how they speak — "paid the card", "money for my van". Requiring every
      // word means one stopword nobody wrote into a description returns zero results,
      // which reads as "we don't have that category" rather than "your grammar failed".
      .filter((t) => t && !STOPWORDS.has(t));
    if (terms.length === 0) return usable;

    // Every word must appear somewhere, in any order — not one contiguous substring.
    // Searching "card payment" has to find *Credit Card Payable*, whose name and
    // guidance both contain those words but never adjacently. A substring match returned
    // Interest Expense and hid the one account that answers the question.
    //
    // Guidance is searched too: people describe what they did ("paid the card"), not what
    // we named the account.
    const matches = usable.filter((a) => {
      const haystack =
        `${a.code} ${a.name} ${a.guidance ?? ""} ${a.group_name ?? ""}`.toLowerCase();
      return terms.every((term) => haystack.includes(term));
    });

    // A hit on the account's own name beats a hit buried in its explanation. Otherwise
    // "card payment" lists Interest Expense (whose guidance mentions the phrase) above
    // Credit Card Payable (which is the answer), and the first option is the one people
    // take. Stable by code within each tier so the order never wobbles.
    const rank = (a: Account) => {
      const title = `${a.code} ${a.name}`.toLowerCase();
      return terms.every((term) => title.includes(term)) ? 0 : 1;
    };
    return matches.sort((x, y) => rank(x) - rank(y) || x.code.localeCompare(y.code));
  }, [accounts, query, excludeId]);

  useEffect(() => setActive(0), [query]);

  useEffect(() => {
    if (!open) return;
    const onClickAway = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, [open]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Keep the highlighted row visible without smooth-scrolling: this is the bulk path.
  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function choose(account: Account | null) {
    onChange(account?.id ?? null);
    setOpen(false);
    setQuery("");
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, options.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (options[active]) choose(options[active]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      setQuery("");
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        className={selected ? "picker-value" : "picker-value picker-empty"}
        disabled={disabled}
        onClick={() => setOpen(true)}
        title={selected?.guidance ?? undefined}
      >
        {selected ? `${selected.code} ${selected.name}` : "Choose a category…"}
      </button>
    );
  }

  return (
    <div className="picker" ref={boxRef}>
      <input
        ref={inputRef}
        type="text"
        className="picker-search"
        placeholder="Type to search…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
        role="combobox"
        aria-expanded="true"
        aria-controls="picker-list"
        aria-autocomplete="list"
      />
      <ul className="picker-list" id="picker-list" role="listbox" ref={listRef}>
        {options.length === 0 && (
          <li className="picker-none">
            Nothing matches &ldquo;{query}&rdquo;.
          </li>
        )}
        {options.map((account, i) => (
          <li
            key={account.id}
            role="option"
            aria-selected={account.id === value}
            data-active={i === active}
            className={i === active ? "picker-option active" : "picker-option"}
            onMouseEnter={() => setActive(i)}
            onMouseDown={(e) => {
              e.preventDefault(); // keep focus so the click-away handler doesn't race
              choose(account);
            }}
          >
            <span className="picker-name">
              <span className="picker-code">{account.code}</span> {account.name}
              {/* Secondary label rather than a sectioned/nested list (ADR 0014) --
                  the keyboard-nav index math above is flat-array based, and grouping
                  visually without restructuring the option list keeps that intact. */}
              {account.group_name && (
                <span className="picker-group"> — {account.group_name}</span>
              )}
            </span>
            {/* The reason this component exists. */}
            {account.guidance && <span className="picker-hint">{account.guidance}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
