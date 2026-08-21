import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { PaperPromotionReport as PaperPromotionReportData } from "../api/types";
import { formatINR, formatPct } from "../format";

function profitFactor(value: number | null): string {
  return value === null ? "∞" : value.toFixed(2);
}

export function PaperPromotionReport() {
  const [data, setData] = useState<PaperPromotionReportData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .paperPromotionReport()
      .then(setData)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Failed to load promotion evidence"),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const policy = data?.promotion_policy;
  const promoted = data?.decisions.filter((decision) => decision.approved_for_paper_scaling).length ?? 0;

  return (
    <section className="card promotion-card">
      <div className="chart-header">
        <div>
          <h2>PAPER strategy promotion</h2>
          <p className="hint">
            Completed forward trades only. Backtests and synthetic replays never count toward promotion.
          </p>
        </div>
        <button className="ghost-btn" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      <div className="promotion-safety">
        <strong>LIVE authorization: BLOCKED</strong>
        <span>Promotion permits controlled PAPER scaling only.</span>
      </div>

      {error && <div className="error">{error}</div>}
      {policy && (
        <div className="window-policy">
          Gate: {policy.min_trades} trades · {policy.min_sessions} sessions · profitable sessions ≥ {formatPct(policy.min_profitable_session_rate, 0)} · expectancy &gt; {formatINR(policy.min_expectancy)} · PF ≥ {policy.min_profit_factor.toFixed(2)} · drawdown ≤ {formatPct(policy.max_drawdown_pct, 0)} · single loss ≤ {formatPct(policy.max_single_loss_pct, 0)}
        </div>
      )}

      <div className="promotion-summary">
        <span className="metric-label">Strategy/instrument pairs promoted</span>
        <span className="metric-value">{promoted} / {data?.decisions.length ?? 0}</span>
      </div>

      {!loading && data?.decisions.length === 0 && !error && (
        <p className="hint">No completed PAPER forward trades recorded in the current results store.</p>
      )}

      {data && data.decisions.length > 0 && (
        <div className="table-scroll promotion-table">
          <table>
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Symbol</th>
                <th className="num">Trades</th>
                <th className="num">Sessions</th>
                <th className="num">Profitable days</th>
                <th className="num">PF</th>
                <th className="num">Expectancy</th>
                <th className="num">Max DD</th>
                <th className="num">Largest loss</th>
                <th>Status / blockers</th>
              </tr>
            </thead>
            <tbody>
              {data.decisions.map((decision) => (
                <tr key={`${decision.symbol}-${decision.strategy}`}>
                  <td>{decision.strategy}</td>
                  <td>{decision.symbol}</td>
                  <td className="num">{decision.trades}</td>
                  <td className="num">{decision.sessions}</td>
                  <td className="num">{formatPct(decision.profitable_session_rate, 0)}</td>
                  <td className="num">{profitFactor(decision.profit_factor)}</td>
                  <td className={`num ${decision.expectancy > 0 ? "pos" : "neg"}`}>
                    {formatINR(decision.expectancy)}
                  </td>
                  <td className="num">{formatPct(decision.max_drawdown_pct, 1)}</td>
                  <td className="num neg">{formatINR(decision.largest_loss)}</td>
                  <td>
                    <span className={`window-status ${decision.approved_for_paper_scaling ? "approved" : "pending"}`}>
                      {decision.status.replace("_", " ")}
                    </span>
                    {decision.reasons.length > 0 && (
                      <span className="window-reason">{decision.reasons.join(" · ")}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
