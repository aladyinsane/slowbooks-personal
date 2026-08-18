import { useState } from "react";
import { api, ApiError } from "../lib/api";

/**
 * Shown instead of the whole app when a request comes back locked (401) -- i.e. this
 * browser is on the same Wi-Fi as the computer running SlowBooks, LAN access is on, and
 * this device hasn't unlocked yet. The computer's own owner never sees this (loopback
 * requests are always exempt, see access.py).
 */
interface Props {
  onUnlock: () => void;
}

export function PinGate({ onUnlock }: Props) {
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.unlock(pin);
      onUnlock();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <div className="book-location pin-gate">
        <p className="label">This computer&rsquo;s books are protected on this network</p>
        <p className="muted">
          Enter the PIN set on the computer running SlowBooks.
        </p>
        <form onSubmit={submit}>
          <input
            type="text"
            inputMode="numeric"
            autoFocus
            placeholder="PIN"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
          />
          <button className="primary" type="submit" disabled={busy || pin === ""}>
            {busy ? "Checking…" : "Unlock"}
          </button>
        </form>
        {error && <p className="field-error">{error}</p>}
      </div>
    </main>
  );
}
