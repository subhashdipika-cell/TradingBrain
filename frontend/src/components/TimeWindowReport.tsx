import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { TimeWindowDecision, TimeWindowReport as TimeWindowReportData } from "../api/types";
import { formatINR, formatPct } from "../format";

function profitFactor(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "∞";
}

function DecisionRow({ decision }: { decision: TimeWindowDecision }) {
  return (
    <tr>
      <td>{decision.bucket}</td>
      <td className="num">{decision.trades}</td>
      <td className="num">{decision.sessions}</td>
      <td className="num">{formatPct(decision.win_rate, 0)}</td>
      <td className="num">{profitFactor(decision.profit_factor)}</td>
      <td className={`num ${decision.expectancy >= 0 ? "pos" : "neg"}`}>
        {formatINR(decision.expectancy)}
      </td>
      <td>
        <span className={`window-status ${decision.approved ? "approved" : "pending"}`}>
          {decision.approved ? "PROMOTED" : "COLLECTING EVIDENCE"}
        </span>
      </td>
      <td>
        {!decision.approved && decision.reasons.length > 0 && (
          <span className="window-reason">{decision.reasons.join(" · ")}</span>
        )}
      </td>
    </tr>
  );
}

export function TimeWindowReport() {
  const [data, setData] = useState<TimeWindowReportData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .timeWindowReport()
      .then(setData)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load time-window report"),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const symbols = data ? Object.entries(data.symbols) : [];
  const policy = data?.promotion_policy;

  return (
    <section className="card time-window-card">
      <div className="chart-header">
        <div>
          <h2>Entry-window promotion</h2>
          <p className="hint">
            Paper-trade evidence only. A window remains unrestricted until it clears every gate.
          </p>
        </div>
        <button className="ghost-btn" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}
      {policy && (
        <div className="window-policy">
          Promotion gate: {policy.min_trades} trades · {policy.min_sessions} sessions · expectancy
          &gt; ₹{policy.min_expectancy.toFixed(0)} · PF ≥ {policy.min_profit_factor.toFixed(2)} · win
          rate ≥ {formatPct(policy.min_win_rate, 0)}
        </div>
      )}

      {!loading && symbols.length === 0 && !error && (
        <p className="hint">No completed forward-test trades recorded yet.</p>
      )}

      {symbols.map(([symbol, decisions]) => (
        <div className="window-symbol" key={symbol}>
          <div className="window-symbol-header">
            <h3>{symbol}</h3>
            <span className="tag">{decisions.filter((d) => d.approved).length} promoted</span>
          </div>
          {decisions.length === 0 ? (
            <p className="hint">No entry-window observations yet.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Entry window</th>
                    <th className="num">Trades</th>
                    <th className="num">Sessions</th>
                    <th className="num">Win%</th>
                    <th className="num">PF</th>
                    <th className="num">Expectancy</th>
                    <th>Status</th>
                    <th>Gate reason</th>
                  </tr>
                </thead>
                <tbody>
                  {decisions.map((decision) => (
                    <DecisionRow key={decision.bucket} decision={decision} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
