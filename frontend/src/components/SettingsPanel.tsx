import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { AutoTraderStatus } from "../api/types";

export function SettingsPanel() {
  const [lots, setLots] = useState<Record<string, number>>({});
  const [updated, setUpdated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [at, setAt] = useState<AutoTraderStatus | null>(null);
  const [atBusy, setAtBusy] = useState(false);

  const load = useCallback(() => {
    api
      .lotSizes()
      .then((d) => {
        setLots(d.lots || {});
        setUpdated(d.updated ?? null);
      })
      .catch(() => undefined);
    api.autoTraderStatus().then(setAt).catch(() => setAt(null));
  }, []);

  useEffect(load, [load]);

  const toggleAutoTrader = async () => {
    if (!at) return;
    setAtBusy(true);
    try {
      setAt(await api.autoTraderToggle(!at.enabled));
    } catch {
      /* backend unreachable — status refresh below */
    } finally {
      setAtBusy(false);
    }
  };

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
    <>
    <div className="card">
      <div className="chart-header">
        <h2>Autonomous forward testing</h2>
        <button
          className={at?.enabled ? "tab" : "tab active"}
          onClick={toggleAutoTrader}
          disabled={atBusy || !at}
        >
          {atBusy ? "…" : at?.enabled ? "■ Stop" : "▶ Start"}
        </button>
      </div>
      <p className="hint">
        When ON, the Daily Brain confirms the regime each trading day and runs a
        forward test on its own inside the {at?.window ?? "10:20–14:30 IST"} entry
        window (STAND_ASIDE days take no trade by decision). Starting while inside
        the window triggers today&apos;s run immediately; stopping only prevents new
        runs — one already in flight completes and saves.
      </p>
      {at && (
        <p className="hint">
          Status: <strong className={at.enabled ? "pos" : "neg"}>
            {at.enabled ? "RUNNING DAILY" : "STOPPED"}
          </strong>
          {" · "}window {at.in_window ? "open now" : "closed now"}
          {at.running && " · forward test in progress"}
          {/* A stored decision belongs to last_day, which may be a PREVIOUS
              day (e.g. Monday morning before the 10:20 window still holds
              Saturday's "weekend skip") — label it honestly instead of
              presenting stale state as "today". */}
          {at.decision && (at.last_day === at.today
            ? ` · today: ${at.decision}`
            : ` · today: no decision yet (next check inside the window)` +
              ` · last (${at.last_day}): ${at.decision}`)}
        </p>
      )}
      {!at && <p className="hint neg">AutoTrader status unavailable — backend offline?</p>}
    </div>

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
    </>
  );
}
