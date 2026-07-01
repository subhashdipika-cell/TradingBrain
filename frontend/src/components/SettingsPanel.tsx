import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

export function SettingsPanel() {
  const [lots, setLots] = useState<Record<string, number>>({});
  const [updated, setUpdated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .lotSizes()
      .then((d) => {
        setLots(d.lots || {});
        setUpdated(d.updated ?? null);
      })
      .catch(() => undefined);
  }, []);

  useEffect(load, [load]);

  const refresh = async () => {
    setBusy(true);
    setMsg("Fetching from Dhan…");
    try {
      const d = await api.refreshLotSizes();
      if (d.ok) {
        setLots(d.applied || d.lots || {});
        setUpdated(d.updated ?? null);
        setMsg(`✓ Updated from Dhan scrip master`);
      } else {
        setMsg(`✗ ${d.error ?? "refresh failed"}`);
      }
    } catch (e) {
      setMsg(`✗ ${e instanceof Error ? e.message : "refresh failed"}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <div className="chart-header">
        <h2>Index lot sizes</h2>
        <button onClick={refresh} disabled={busy}>
          {busy ? "Updating…" : "⟳ Update from Dhan"}
        </button>
      </div>

      <p className="hint">
        NSE/BSE revise F&amp;O lot sizes periodically. This pulls the current values
        from Dhan&apos;s scrip master (SEM_LOT_UNITS) and applies them to backtests and
        forward tests. {updated ? `Last updated ${new Date(updated).toLocaleString("en-IN")}.` : "Not yet refreshed — showing built-in defaults."}
      </p>
      {msg && <p className="hint">{msg}</p>}

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Instrument</th>
              <th className="num">Lot size</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(lots).sort((a, b) => a[0].localeCompare(b[0])).map(([sym, lot]) => (
              <tr key={sym}>
                <td>{sym}</td>
                <td className="num">{lot}</td>
              </tr>
            ))}
            {Object.keys(lots).length === 0 && (
              <tr>
                <td colSpan={2} className="hint">No lot sizes loaded.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
