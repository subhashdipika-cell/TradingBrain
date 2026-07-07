import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { ResultRecord, Trade } from "../api/types";
import { formatDateTime, formatINR } from "../format";

/**
 * History — every trade TradingBrain has taken, flattened chronologically
 * across all forward-test runs (with an optional toggle to include backtests).
 * Complements Analysis (per-run deep dive) the way a broker statement
 * complements a research report.
 */

interface Row extends Trade {
  runId: string;
  runDate: string;
  runType: string;
  runSymbol: string;
  strategy?: string;
}

const MAX_RUNS = 25; // detail-fetch cap — the newest runs

export function History() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [includeBacktests, setIncludeBacktests] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
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
        if (!alive) return;
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
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [includeBacktests]);

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
    return { wins, net, byStrategy };
  }, [rows]);

  return (
    <main className="layout single">
      <section className="results">
        {error && <div className="card error">{error}</div>}

        <div className="card">
          <h2>Trade History</h2>
          <p className="hint">
            Every trade taken across {includeBacktests ? "all runs" : "forward tests"} —
            the brain&apos;s autonomous daily runs land here too.{" "}
            <label style={{ cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={includeBacktests}
                onChange={(e) => setIncludeBacktests(e.target.checked)}
              />{" "}
              include backtests
            </label>
          </p>

          {loading && <p>Loading trades…</p>}
          {!loading && rows.length === 0 && (
            <p className="hint">
              No trades yet. The AutoTrader runs the brain&apos;s pick each trading day
              (10:20–14:30 IST window); STAND_ASIDE days take no trades by decision.
            </p>
          )}

          {rows.length > 0 && (
            <>
              <p>
                <strong>{rows.length}</strong> trades · {stats.wins}W/
                {rows.length - stats.wins}L ·{" "}
                <strong>{((100 * stats.wins) / rows.length).toFixed(1)}%</strong> win ·
                net{" "}
                <strong className={stats.net >= 0 ? "pos" : "neg"}>
                  {formatINR(stats.net)}
                </strong>
              </p>
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
                            {t.runType === "forward-test" ? "FWD" : "BT"}{" "}
                            {t.runDate.slice(0, 10)}
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

              <h2 style={{ marginTop: "1rem" }}>By strategy</h2>
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
            </>
          )}
        </div>
      </section>
    </main>
  );
}
