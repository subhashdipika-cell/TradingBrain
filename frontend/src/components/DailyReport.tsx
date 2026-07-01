import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { DailyReport as DailyReportData, GroupRow } from "../api/types";
import { formatINR } from "../format";

function todayIST(): string {
  const now = new Date();
  const ist = new Date(now.getTime() + (now.getTimezoneOffset() + 330) * 60000);
  return ist.toISOString().slice(0, 10);
}

// Report percent fields are already 0-100.
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(0)}%`);
const tone = (v: number) => (v > 0 ? "metric-pos" : v < 0 ? "metric-neg" : "");

function GroupTable({ title, rows }: { title: string; rows: GroupRow[] }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{title}</th>
              <th className="num">Trades</th>
              <th className="num">Win%</th>
              <th className="num">Net P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <td>{r.label}</td>
                <td className="num">{r.total}</td>
                <td className="num">{pct(r.win_rate)}</td>
                <td className={`num ${r.net >= 0 ? "pos" : "neg"}`}>{formatINR(r.net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function DailyReport() {
  const [date, setDate] = useState(todayIST());
  const [data, setData] = useState<DailyReportData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  const load = useCallback((d: string) => {
    setLoading(true);
    setError(null);
    api
      .dailyReport(d)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load report"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(date);
  }, [date, load]);

  const runExport = async (fn: () => Promise<{ runs: number; path: string }>, label: string) => {
    setExportMsg(`Exporting ${label}…`);
    try {
      const r = await fn();
      setExportMsg(`✓ Saved ${r.runs} run(s) → ${r.path}`);
    } catch (e) {
      setExportMsg(`✗ ${e instanceof Error ? e.message : "export failed"}`);
    }
  };

  const t = data?.totals;

  return (
    <div>
      <div className="card">
        <div className="chart-header">
          <h2>Daily report</h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            <button className="ghost-btn" onClick={() => load(date)}>
              Refresh
            </button>
            <button onClick={() => runExport(() => api.exportDaily(date), "day")}>
              Export day → Obsidian
            </button>
            <button
              className="ghost-btn"
              onClick={() => runExport(() => api.exportMonthly(date.slice(0, 7)), "month")}
            >
              Export month
            </button>
          </div>
        </div>

        {error && <div className="error">{error}</div>}
        {exportMsg && <p className="hint">{exportMsg}</p>}
        {loading && <p className="hint">Loading…</p>}

        {t && t.runs === 0 && (
          <p className="hint">No runs recorded for {data?.date}. Run a backtest or forward test.</p>
        )}

        {t && t.runs > 0 && (
          <>
            <p className="hint">
              {t.trades} trades · {t.forward_tests} forward-test / {t.backtests} backtest run(s) ·{" "}
              {t.wins}W / {t.losses}L
            </p>
            <div className="metrics">
              <div className={`metric ${tone(t.net_pnl)}`}>
                <span className="metric-label">Net P&amp;L (after costs)</span>
                <span className="metric-value">{formatINR(t.net_pnl)}</span>
              </div>
              <div className="metric metric-neg">
                <span className="metric-label">Total charges</span>
                <span className="metric-value">{formatINR(t.total_costs)}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Win rate</span>
                <span className="metric-value">{pct(t.win_rate)}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Trades</span>
                <span className="metric-value">{t.trades}</span>
              </div>
            </div>
            <p className="hint">
              Net P&amp;L is after all NSE options charges — brokerage, STT, exchange txn, SEBI,
              stamp duty and 18% GST.
            </p>
          </>
        )}
      </div>

      {data && data.by_session.length > 0 && <GroupTable title="By session" rows={data.by_session} />}
      {data && data.by_strategy.length > 0 && <GroupTable title="By strategy" rows={data.by_strategy} />}

      {data && data.trades.length > 0 && (
        <div className="card">
          <h2>Trades ({data.trades.length})</h2>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Entry (IST)</th>
                  <th>Session</th>
                  <th>Type</th>
                  <th>Strategy</th>
                  <th>Structure</th>
                  <th className="num">Lots</th>
                  <th>Exit reason</th>
                  <th className="num">P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {data.trades.map((tr, i) => (
                  <tr key={i}>
                    <td>{tr.entry_time ? tr.entry_time.replace("T", " ").slice(0, 16) : "—"}</td>
                    <td>{tr.session ?? "—"}</td>
                    <td>{tr.run_type ?? "—"}</td>
                    <td>{tr.strategy ?? "—"}</td>
                    <td>{tr.structure ?? "—"}</td>
                    <td className="num">{tr.lots ?? "—"}</td>
                    <td>{tr.exit_reason ?? "—"}</td>
                    <td className={`num ${(tr.pnl ?? 0) >= 0 ? "pos" : "neg"}`}>
                      {formatINR(tr.pnl ?? 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
