import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";

/**
 * Opt-in same-Wi-Fi access (ADR 0001's "local-first" narrowed, not abandoned): the
 * server stays off the network until you turn this on here, and even then a PIN gates
 * anyone who isn't this computer. No cloud, no accounts -- collapsed by default for the
 * same reason AccountsPanel is, principle 4: most people never touch this screen.
 */
export function NetworkPanel() {
  const [open, setOpen] = useState(false);
  const [lanEnabled, setLanEnabled] = useState(false);
  const [pinConfigured, setPinConfigured] = useState(false);
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api
      .networkSettings()
      .then((s) => {
        setLanEnabled(s.lan_access_enabled);
        setPinConfigured(s.pin_configured);
      })
      .catch((err: Error) => setError(err.message));
  }, [open]);

  async function toggleLan(enabled: boolean) {
    setBusy(true);
    setError(null);
    try {
      await api.setLanAccess(enabled);
      setLanEnabled(enabled);
      setNote("Restart SlowBooks for this to take effect.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function savePin(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.setPin(pin);
      setPinConfigured(true);
      setPin("");
      setNote("PIN saved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <section className="accounts-collapsed">
        <button className="link plain" onClick={() => setOpen(true)}>
          Access on your phone
        </button>
      </section>
    );
  }

  return (
    <section className="network" aria-labelledby="network-heading">
      <h2 id="network-heading">Access on your phone</h2>
      <p className="lede">
        Off by default. Turning this on lets a phone on the same home Wi-Fi as this
        computer reach your books in a browser — nothing leaves your network, and
        nothing changes for using SlowBooks here.
      </p>

      {error && (
        <div className="bad-box" role="alert">
          {error}
        </div>
      )}

      <label className="network-toggle">
        <input
          type="checkbox"
          checked={lanEnabled}
          disabled={busy}
          onChange={(e) => void toggleLan(e.target.checked)}
        />
        Allow access from other devices on my Wi-Fi
      </label>

      {lanEnabled && !pinConfigured && (
        <p className="field-error">
          Set a PIN below before using this from your phone — without one, anything on
          your Wi-Fi could reach your books.
        </p>
      )}

      <form className="network-pin-form" onSubmit={savePin}>
        <label htmlFor="net-pin">{pinConfigured ? "Change PIN" : "Set a PIN"}</label>
        <input
          id="net-pin"
          type="text"
          inputMode="numeric"
          placeholder="4-8 digits"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
        />
        <button className="primary" type="submit" disabled={busy || pin === ""}>
          Save
        </button>
      </form>

      {note && <p className="posted">{note}</p>}
    </section>
  );
}
