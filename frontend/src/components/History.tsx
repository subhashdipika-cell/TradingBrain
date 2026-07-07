import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { ResultRecord, Trade } from "../api/types";
import { formatDateTime, formatINR } from "../format";

/**
 * History — every trade TradingBrain has taken, flattened chronologically
 * across all forward-test runs (toggle to include backtests). Full-width
 * layout modeled on IntelliTrade's History page: stat tiles up top,
 * Export → Obsidian in the header, tables below.
 */

interface Row extends Trade {
  runId: string;
  runDate: string;
  runType: string;
  runSymbol: string;
  strategy?: string;
}

const MAX_RUNS = 25; // detail-fetch cap — the newest runs

const tile: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--border)",
  borderRadius: 10,
  padding: "14px 18px",
  minWidth: 150,
  flex: "1 1 150px",
};
const tileLabel: React.CSSProperties = {
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  opacity: 0.55,
  marginBottom: 4,
};
const tileValue: React.CSSProperties = { fontSize: 22, fontWeight: 700 };

export function History() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [includeBacktests, setIncludeBacktests] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    api
      .listResults()
      .then(async (r) => {
        const wanted = r.results
          .filter((s) => includeBacktests || s.run_type === "forward-test")
          .sort((a, b) => (b.created_at > a.created_at ? 1 : -1))
          .slice(0, MAX_RUNS);
        const details = await Promise.all(
          wanted.map((s) => api.getResult(s.id).catch(() => null)),
        );
        const flat: Row[] = [];
        for (const rec of details.filter(Boolean) as ResultRecord[]) {
          for (const t of rec.trades) {
            flat.push({
              ...t,
              runId: rec.id,
              runDate: rec.created_at,
              runType: rec.run_type,
              runSymbol: rec.symbol,
              strategy: (t as Row).strategy,
            });
          }
        }
        flat.sort((a, b) => (b.entry_time > a.entry_time ? 1 : -1));
        setRows(flat);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [includeBacktests]);

  const exportObsidian = async () => {
    setExportMsg("exporting…");
    try {
      const month = new Date().toISOString().slice(0, 7);
      const r = await api.exportMonthly(month);
      setExportMsg(`✓ saved ${r.path ?? month}`);
    } catch (e) {
      setExportMsg(`✗ ${e instanceof Error ? e.message : "export failed"}`);
    }
    setTimeout(() => setExportMsg(null), 8000);
  };

  const stats = useMemo(() => {
    const wins = rows.filter((t) => t.pnl > 0).length;
    const net = rows.reduce((a, t) => a + t.pnl, 0);
    const byStrategy = new Map<string, { n: number; net: number; wins: number }>();
    for (const t of rows) {
      const k = t.strategy || t.structure || "—";
      const s = byStrategy.get(k) ?? { n: 0, net: 0, wins: 0 };
      s.n += 1;
      s.net += t.pnl;
      if (t.pnl > 0) s.wins += 1;
      byStrategy.set(k, s);
    }
    const best = [...byStrategy.entries()].sort((a, b) => b[1].net - a[1].net)[0];
    return { wins, net, byStrategy, best };
  }, [rows]);

  return (
    <main style={{ width: "100%" }}>
      {/* Header: title left, actions right */}
      <div
        className="card"
        style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}
      >
        <div style={{ flex: 1, minWidth: 240 }}>
          <h2 style={{ margin: 0 }}>Trade History</h2>
          <p className="hint" style={{ margin: "4px 0 0" }}>
            Every trade across {includeBacktests ? "all runs" : "forward tests"} — the
            AutoTrader&apos;s daily brain runs land here. Monthly rollups auto-save to
            Obsidian on the last day of each month.
          </p>
        </div>
        <label className="hint" style={{ cursor: "pointer", whiteSpace: "nowrap" }}>
          <input
            type="checkbox"
            checked={includeBacktests}
            onChange={(e) => setIncludeBacktests(e.target.checked)}
          />{" "}
          include backtests
        </label>
        <button className="tab" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "↻ Refresh"}
        </button>
        <button className="tab active" onClick={exportObsidian}>
          Export → Obsidian
        </button>
        {exportMsg && <span className="hint">{exportMsg}</span>}
      </div>

      {error && <div className="card error">{error}</div>}

      {/* Stat tiles */}
      {rows.length > 0 && (
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 20 }}>
          <div style={tile}>
            <div style={tileLabel}>Trades</div>
            <div style={tileValue}>{rows.length}</div>
          </div>
          <div style={tile}>
            <div style={tileLabel}>Win / Loss</div>
            <div style={tileValue}>
              {stats.wins}W / {rows.length - stats.wins}L
            </div>
          </div>
          <div style={tile}>
            <div style={tileLabel}>Win rate</div>
            <div style={tileValue}>{((100 * stats.wins) / rows.length).toFixed(1)}%</div>
          </div>
          <div style={tile}>
            <div style={tileLabel}>Net P&amp;L</div>
            <div style={tileValue} className={stats.net >= 0 ? "pos" : "neg"}>
              {formatINR(stats.net)}
            </div>
          </div>
          <div style={tile}>
            <div style={tileLabel}>Best strategy</div>
            <div style={{ ...tileValue, fontSize: 16 }}>
              {stats.best ? `${stats.best[0]} (${formatINR(stats.best[1].net)})` : "—"}
            </div>
          </div>
        </div>
      )}

      {/* Trades table */}
      <div className="card">
        <h2>Trades</h2>
        {loading && <p className="hint">Loading trades…</p>}
        {!loading && rows.length === 0 && (
          <p className="hint">
            No trades yet. The AutoTrader runs the brain&apos;s pick each trading day
            (10:20–14:30 IST window); STAND_ASIDE days take no trades by decision.
          </p>
        )}
        {rows.length > 0 && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Entry (IST)</th>
                  <th>Exit</th>
                  <th>Symbol</th>
                  <th>Strategy</th>
                  <th>Structure</th>
                  <th>Lots</th>
                  <th>Reason</th>
                  <th>Run</th>
                  <th className="num">P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t, i) => (
                  <tr key={`${t.runId}-${i}`}>
                    <td>{formatDateTime(t.entry_time)}</td>
                    <td>{formatDateTime(t.exit_time)}</td>
                    <td>{t.runSymbol}</td>
                    <td>{t.strategy || "—"}</td>
                    <td>{t.structure}</td>
                    <td>{t.lots}</td>
                    <td>
                      <span className="tag">{t.exit_reason}</span>
                    </td>
                    <td>
                      <span className="tag">
                        {t.runType === "forward-test" ? "FWD" : "BT"} {t.runDate.slice(0, 10)}
                      </span>
                    </td>
                    <td className={`num ${t.pnl >= 0 ? "pos" : "neg"}`}>
                      {formatINR(t.pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Strategy scoreboard */}
      {rows.length > 0 && (
        <div className="card">
          <h2>By strategy</h2>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Trades</th>
                  <th>Win %</th>
                  <th className="num">Net</th>
                </tr>
              </thead>
              <tbody>
                {[...stats.byStrategy.entries()]
                  .sort((a, b) => b[1].net - a[1].net)
                  .map(([k, s]) => (
                    <tr key={k}>
                      <td>{k}</td>
                      <td>{s.n}</td>
                      <td>{((100 * s.wins) / s.n).toFixed(1)}%</td>
                      <td className={`num ${s.net >= 0 ? "pos" : "neg"}`}>
                        {formatINR(s.net)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </main>
  );
}
