import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ResultRecord, ResultSummary } from "../api/types";
import { formatDateTime, formatINR, formatNumber, formatPct } from "../format";
import { EquityChart } from "./EquityChart";
import { SummaryCards } from "./SummaryCards";
import { TradesTable } from "./TradesTable";

const RUN_LABEL: Record<string, string> = {
  backtest: "Backtest (synthetic)",
  "dhan-backtest": "Backtest (real Dhan)",
  "forward-test": "Forward test (live paper)",
};

export function Analysis() {
  const [runs, setRuns] = useState<ResultSummary[]>([]);
  const [selected, setSelected] = useState<ResultRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    api
      .listResults()
      .then((r) => setRuns(r.results))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  };

  useEffect(refresh, []);

  const open = (id: string) => {
    api
      .getResult(id)
      .then(setSelected)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  };

  return (
    <div>
      <div className="card">
        <div className="chart-header">
          <h2>Saved runs ({runs.length})</h2>
          <button className="ghost-btn" onClick={refresh}>
            Refresh
          </button>
        </div>
        {error && <div className="error">{error}</div>}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Type</th>
                <th>Symbol</th>
                <th className="num">Net P&amp;L</th>
                <th className="num">Return</th>
                <th className="num">Win%</th>
                <th className="num">PF</th>
                <th className="num">Max DD</th>
                <th className="num">Sharpe</th>
                <th className="num">Trades</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{formatDateTime(r.created_at)}</td>
                  <td>{RUN_LABEL[r.run_type] ?? r.run_type}</td>
                  <td>{r.symbol}</td>
                  <td className={`num ${r.net_return >= 0 ? "pos" : "neg"}`}>
                    {formatINR(r.net_return)}
                  </td>
                  <td className={`num ${r.return_pct >= 0 ? "pos" : "neg"}`}>
                    {formatPct(r.return_pct)}
                  </td>
                  <td className="num">{formatPct(r.win_rate, 1)}</td>
                  <td className="num">
                    {Number.isFinite(r.profit_factor)
                      ? formatNumber(r.profit_factor)
                      : "∞"}
                  </td>
                  <td className="num neg">{formatPct(r.max_drawdown_pct)}</td>
                  <td className="num">{formatNumber(r.sharpe)}</td>
                  <td className="num">{r.total_trades}</td>
                  <td>
                    <button className="ghost-btn" onClick={() => open(r.id)}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={11} className="placeholder">
                    No runs yet. Run a backtest or forward test to populate this.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <>
          <h2 style={{ margin: "8px 0" }}>
            {RUN_LABEL[selected.run_type] ?? selected.run_type} ·{" "}
            {selected.symbol} · {formatDateTime(selected.created_at)}
          </h2>
          <SummaryCards
            trades={selected.summary.trades}
            equity={selected.summary.equity}
          />
          <EquityChart
            points={selected.equity_curve}
            baseline={selected.summary.equity.starting}
          />
          <TradesTable trades={selected.trades} />
        </>
      )}
    </div>
  );
}
