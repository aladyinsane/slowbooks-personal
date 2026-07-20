import { useEffect, useState } from "react";
import { api } from "../lib/api";

/**
 * Getting your books out (ADR 0008), and knowing where they live.
 *
 * The copy here is doing real work, so it's worth defending. Most software buries
 * export in a settings submenu and words it defensively. Ours says plainly that leaving
 * is easy, because ADR 0001 stakes the whole product on the books being the user's --
 * and a promise you only keep quietly isn't one anybody can rely on.
 *
 * Showing the file's location belongs here for the same reason: "your books are yours"
 * is more convincing when we point at exactly where they sit on your disk. In the
 * packaged app that's next to the program (ADR 0013); the path tells the user where to
 * back up and what to copy to move machines. It's read-only -- a browser tab can't open
 * a native folder picker, so choosing a new location waits for the desktop-window build.
 *
 * Plain <a download> rather than fetch(): the browser's own download machinery handles
 * the file, no buffering an archive in JS to hand it straight back.
 */

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(0)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

export function ExportPanel() {
  const [book, setBook] = useState<Awaited<ReturnType<typeof api.bookFile>> | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.bookFile().then(setBook).catch(() => setBook(null));
  }, []);

  async function copyPath() {
    if (!book) return;
    try {
      await navigator.clipboard.writeText(book.path);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked; the path is on screen to copy by hand regardless.
    }
  }

  return (
    <section className="export" aria-labelledby="export-heading">
      <h2 id="export-heading">Your books are yours</h2>
      <p className="lede">
        Take them whenever you like. No subscription check, no export limits, and nothing
        here needs SlowBooks to open it.
      </p>

      {book && (
        <div className="book-location">
          <p className="label">Where your books are saved</p>
          <p className="book-path">
            <code>{book.path}</code>
            <button type="button" className="link" onClick={copyPath}>
              {copied ? "copied" : "copy"}
            </button>
          </p>
          <p className="muted">
            {book.exists
              ? `${humanSize(book.size_bytes)} on this computer. Back it up by copying this file somewhere safe; to move computers, copy the whole folder.`
              : "This file is created the first time you record something."}
          </p>
        </div>
      )}

      <dl className="export-options">
        <div>
          <dt>
            <a href={api.exportZipUrl} download>
              Download everything (.zip)
            </a>
          </dt>
          <dd>
            Spreadsheets of every transaction and account, plus a general ledger and trial
            balance your accountant can open. Includes a README explaining every file.
          </dd>
        </div>

        <div>
          <dt>
            <a href={api.exportDatabaseUrl} download>
              Download the book file (.db)
            </a>
          </dt>
          <dd>
            The complete book, exactly as SlowBooks stores it. This is the file to keep as
            a backup — it&rsquo;s the one thing needed to restore everything.
          </dd>
        </div>

        <div>
          <dt>
            <a href={api.exportJsonUrl} download="slowbooks-export.json">
              Download as JSON
            </a>
          </dt>
          <dd>For moving your data into another program.</dd>
        </div>
      </dl>
    </section>
  );
}
