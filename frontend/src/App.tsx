import { useState } from "react";
import { api } from "./api/client";
import type { BacktestRequest, BacktestResponse } from "./api/types";
import { Analysis } from "./components/Analysis";
import { BacktestForm } from "./components/BacktestForm";
import { Brand } from "./components/Brand";
import { DailyReport } from "./components/DailyReport";
import { EquityChart } from "./components/EquityChart";
import { ForwardTestPanel } from "./components/ForwardTestPanel";
import { HealthBadge } from "./components/HealthBadge";
import { SettingsPanel } from "./components/SettingsPanel";
import { SummaryCards } from "./components/SummaryCards";
import { TimeWindowReport } from "./components/TimeWindowReport";
import { TradesTable } from "./components/TradesTable";

type Tab = "run" | "analysis" | "reports" | "settings";

export default function App() {
  const [tab, setTab] = useState<Tab>("run");
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (payload: BacktestRequest, realData: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.runBacktest(payload, realData);
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
      <Brand />

      <header className="header">
        <p className="subtitle">
          Regime-based options engine · TB001 theta · TB002 ICT
        </p>
        <HealthBadge />
      </header>

      <nav className="tabs">
        <button
          className={tab === "run" ? "tab active" : "tab"}
          onClick={() => setTab("run")}
        >
          Run
        </button>
        <button
          className={tab === "analysis" ? "tab active" : "tab"}
          onClick={() => setTab("analysis")}
        >
          Analysis
        </button>
        <button
          className={tab === "reports" ? "tab active" : "tab"}
          onClick={() => setTab("reports")}
        >
          Reports
        </button>
        <button
          className={tab === "settings" ? "tab active" : "tab"}
          onClick={() => setTab("settings")}
        >
          Settings
        </button>
      </nav>

      {tab === "run" && (
        <main className="layout">
          <aside>
            <BacktestForm onRun={run} loading={loading} />
            <ForwardTestPanel />
          </aside>

          <section className="results">
            {error && <div className="card error">{error}</div>}

            {!result && !error && (
              <div className="card placeholder">
                Configure parameters and run a backtest to see results. Saved
                runs appear under the Analysis tab; daily summaries under Reports.
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
      )}

      {tab === "analysis" && (
        <main>
          <Analysis />
        </main>
      )}

      {tab === "reports" && (
        <main>
          <DailyReport />
          <TimeWindowReport />
        </main>
      )}

      {tab === "settings" && (
        <main>
          <SettingsPanel />
        </main>
      )}
    </div>
  );
}
