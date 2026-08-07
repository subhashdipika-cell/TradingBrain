import { useState } from "react";
import { api } from "./api/client";
import type { BacktestRequest, BacktestResponse } from "./api/types";
import { BacktestForm } from "./components/BacktestForm";
import { EquityChart } from "./components/EquityChart";
import { HealthBadge } from "./components/HealthBadge";
import { SummaryCards } from "./components/SummaryCards";
import { TradesTable } from "./components/TradesTable";

export default function App() {
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (payload: BacktestRequest) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.runBacktest(payload);
      setResult(response);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>TradingBrain</h1>
          <p className="subtitle">TB001 · Dynamic Theta Harvesting</p>
        </div>
        <HealthBadge />
      </header>

      <main className="layout">
        <aside>
          <BacktestForm onRun={run} loading={loading} />
        </aside>

        <section className="results">
          {error && <div className="card error">{error}</div>}

          {!result && !error && (
            <div className="card placeholder">
              Configure parameters and run a backtest to see results.
            </div>
          )}

          {result && (
            <>
              <SummaryCards
                trades={result.trades_summary}
                equity={result.equity_summary}
              />
              <EquityChart
                points={result.equity_curve}
                baseline={result.equity_summary.starting}
              />
              <TradesTable trades={result.trades} />
              <details className="card">
                <summary>Full text report</summary>
                <pre className="report">{result.report}</pre>
              </details>
            </>
          )}
        </section>
      </main>
    </div>
  );
}
