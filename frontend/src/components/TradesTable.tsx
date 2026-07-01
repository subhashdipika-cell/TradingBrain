import type { Trade } from "../api/types";
import { formatDateTime, formatINR } from "../format";

interface Props {
  trades: Trade[];
}

export function TradesTable({ trades }: Props) {
  if (trades.length === 0) {
    return null;
  }

  return (
    <div className="card">
      <h2>Trades ({trades.length})</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Structure</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>Lots</th>
              <th>Reason</th>
              <th className="num">P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                <td>{t.structure}</td>
                <td>{formatDateTime(t.entry_time)}</td>
                <td>{formatDateTime(t.exit_time)}</td>
                <td>{t.lots}</td>
                <td>
                  <span className="tag">{t.exit_reason}</span>
                </td>
                <td className={`num ${t.pnl >= 0 ? "pos" : "neg"}`}>
                  {formatINR(t.pnl)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
