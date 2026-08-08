import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { TimeWindowDecision, TimeWindowReport as TimeWindowReportData } from "../api/types";
import { formatINR, formatPct } from "../format";

function profitFactor(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "∞";
}

function WindowChart({ decisions }: { decisions: TimeWindowDecision[] }) {
  const width = 720;
  const height = 220;
  const left = 46;
  const right = 18;
  const top = 18;
  const bottom = 48;
  const baseline = 130;
  const plotHeight = 92;
  const maxAbs = Math.max(1, ...decisions.map((d) => Math.abs(d.net_pnl)));
  const slot = (width - left - right) / decisions.length;
  const barWidth = Math.max(18, Math.min(64, slot - 12));

  return (
    <div className="window-chart-wrap">
      <div className="window-chart-legend">
        <span><i className="legend-swatch pnl-swatch" />Net P&amp;L</span>
        <span><i className="legend-swatch expectancy-swatch" />Expectancy label</span>
      </div>
      <svg className="window-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Net P&L and expectancy by entry window">
        <line x1={left} x2={width - right} y1={baseline} y2={baseline} className="window-chart-zero" />
        <text x={left - 8} y={top + 4} textAnchor="end" className="window-chart-axis">+{formatINR(maxAbs)}</text>
        <text x={left - 8} y={baseline + 4} textAnchor="end" className="window-chart-axis">₹0</text>
        <text x={left - 8} y={baseline + plotHeight + 4} textAnchor="end" className="window-chart-axis">-{formatINR(maxAbs)}</text>
        {decisions.map((decision, index) => {
          const x = left + slot * index + (slot - barWidth) / 2;
          const barHeight = Math.max(2, (Math.abs(decision.net_pnl) / maxAbs) * plotHeight);
          const y = decision.net_pnl >= 0 ? baseline - barHeight : baseline;
          return (
            <g key={decision.bucket}>
              <title>{`${decision.bucket}: ${formatINR(decision.net_pnl)} net, ${formatINR(decision.expectancy)} expectancy`}</title>
              <rect x={x} y={y} width={barWidth} height={barHeight} rx="4" className={`window-bar ${decision.net_pnl >= 0 ? "positive" : "negative"}`} />
              <text x={x + barWidth / 2} y={decision.net_pnl >= 0 ? y - 6 : y + barHeight + 14} textAnchor="middle" className="window-chart-value">
                {formatINR(decision.net_pnl)}
              </text>
              <text x={x + barWidth / 2} y={height - bottom + 16} textAnchor="middle" className="window-chart-label">
                {decision.bucket.slice(0, 5)}
              </text>
              <text x={x + barWidth / 2} y={height - bottom + 31} textAnchor="middle" className="window-chart-expectancy">
                E {formatINR(decision.expectancy)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
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
            <>
              <WindowChart decisions={decisions} />
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
            </>
          )}
        </div>
      ))}
    </section>
  );
}
