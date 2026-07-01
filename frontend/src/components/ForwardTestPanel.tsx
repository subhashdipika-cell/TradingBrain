import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ForwardTestStatus } from "../api/types";

const SYMBOLS = ["NIFTY", "BANKNIFTY", "FINNIFTY"];

export function ForwardTestPanel() {
  const [symbol, setSymbol] = useState("NIFTY");
  const [maxPolls, setMaxPolls] = useState(30);
  const [singleStrategy, setSingleStrategy] = useState(false);
  const [status, setStatus] = useState<ForwardTestStatus | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const fetchStatus = () =>
    api.forwardTestStatus().then(setStatus).catch(() => undefined);

  useEffect(() => {
    fetchStatus();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  // Poll every 3s while a run is in progress.
  useEffect(() => {
    if (status?.running && pollRef.current == null) {
      pollRef.current = window.setInterval(fetchStatus, 3000);
    } else if (!status?.running && pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [status?.running]);

  const start = async () => {
    setError(null);
    setMsg(null);
    try {
      const r = await api.runForwardTest({
        symbol,
        max_polls: maxPolls,
        single_strategy: singleStrategy,
      });
      setMsg(
        r.note ??
          `Forward test started for ${r.symbol} (${r.max_polls} polls). The result appears in Analysis / Reports when it finishes.`,
      );
      fetchStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start forward test.");
    }
  };

  const running = status?.running ?? false;
  const marketOpen = status?.market_open ?? false;

  return (
    <form
      className="card form"
      onSubmit={(e) => {
        e.preventDefault();
        start();
      }}
    >
      <h2>Forward test (live paper)</h2>

      <span
        className="badge"
        style={{ color: marketOpen ? "#22c55e" : "#f59e0b", alignSelf: "flex-start" }}
      >
        {marketOpen ? "● NSE open" : "○ NSE closed"}
      </span>

      <label>
        Symbol
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      <label>
        Max polls (option-chain snapshots)
        <input
          type="number"
          min={1}
          max={5000}
          value={maxPolls}
          onChange={(e) => setMaxPolls(Number(e.target.value))}
        />
      </label>

      <label className="toggle">
        <input
          type="checkbox"
          checked={singleStrategy}
          onChange={(e) => setSingleStrategy(e.target.checked)}
        />
        TB001 only (skip regime selector)
      </label>

      <button type="submit" disabled={running}>
        {running ? "Forward test running…" : "Run forward test"}
      </button>

      <p className="hint">
        Polls the LIVE Dhan option chain and runs the regime-selected strategies with
        simulated fills — real premiums, no capital at risk. Costs (brokerage, STT,
        exchange, GST, stamp) are always applied.
      </p>

      {msg && <p className="hint">{msg}</p>}
      {status?.last_run_id && !status.error && (
        <p className="hint">Last run saved: {status.last_run_id} — see Analysis / Reports.</p>
      )}
      {status?.error && <div className="error">Last run failed: {status.error}</div>}
      {error && <div className="error">{error}</div>}
    </form>
  );
}
