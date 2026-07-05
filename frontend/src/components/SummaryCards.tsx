import type { EquitySummary, TradeSummary } from "../api/types";
import { formatINR, formatNumber, formatPct } from "../format";

interface Props {
  trades: TradeSummary;
  equity: EquitySummary;
}

interface Metric {
  label: string;
  value: string;
  tone?: "pos" | "neg" | "neutral";
}

function tone(value: number): "pos" | "neg" | "neutral" {
  if (value > 0) return "pos";
  if (value < 0) return "neg";
  return "neutral";
}

export function SummaryCards({ trades, equity }: Props) {
  const pf = Number.isFinite(trades.profit_factor)
    ? formatNumber(trades.profit_factor)
    : "∞";

  const metrics: Metric[] = [
    {
      label: "Net P&L (post-cost)",
      value: formatINR(equity.net_return),
      tone: tone(equity.net_return),
    },
    {
      label: "Return",
      value: formatPct(equity.return_pct),
      tone: tone(equity.return_pct),
    },
    { label: "Win rate", value: formatPct(trades.win_rate, 1) },
    { label: "Profit factor", value: pf },
    {
      label: "Max drawdown",
      value: formatPct(equity.max_drawdown_pct),
      tone: "neg",
    },
    { label: "Sharpe", value: formatNumber(equity.sharpe) },
    {
      label: "Total costs",
      value: formatINR(trades.total_costs),
      tone: "neg",
    },
    {
      label: "Gross P&L (pre-cost)",
      value: formatINR(trades.gross_profit_pre_cost),
      tone: tone(trades.gross_profit_pre_cost),
    },
    { label: "Trades", value: `${trades.total}` },
    {
      label: "Expectancy / trade",
      value: formatINR(trades.expectancy),
      tone: tone(trades.expectancy),
    },
  ];

  return (
    <div className="metrics">
      {metrics.map((m) => (
        <div key={m.label} className={`metric metric-${m.tone ?? "neutral"}`}>
          <span className="metric-label">{m.label}</span>
          <span className="metric-value">{m.value}</span>
        </div>
      ))}
    </div>
  );
}
