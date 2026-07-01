// Mirrors the backend Pydantic schemas in app/schemas/backtest.py.

export interface HealthResponse {
  status: string;
}

export interface BacktestRequest {
  symbol: string;
  num_days: number;
  bar_minutes: number;
  starting_capital: number;
  base_iv: number;
  annual_vol: number;
  seed: number;
}

export interface TradeSummary {
  total: number;
  wins: number;
  losses: number;
  win_rate: number;
  profit_factor: number;
  expectancy: number;
  average_win: number;
  average_loss: number;
  largest_win: number;
  largest_loss: number;
  net_profit: number;
  total_costs: number;
  gross_profit_pre_cost: number;
}

export interface EquitySummary {
  starting: number;
  ending: number;
  net_return: number;
  return_pct: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  sharpe: number;
  samples: number;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

export interface Trade {
  symbol: string;
  structure: string;
  entry_time: string;
  exit_time: string;
  pnl: number;
  exit_reason: string;
  lots: number;
}

export interface BacktestResponse {
  request: BacktestRequest;
  trades_summary: TradeSummary;
  equity_summary: EquitySummary;
  equity_curve: EquityPoint[];
  trades: Trade[];
  report: string;
}

export interface ResultSummary {
  id: string;
  created_at: string;
  run_type: string;
  symbol: string;
  net_return: number;
  return_pct: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown_pct: number;
  sharpe: number;
  total_trades: number;
  total_costs: number;
}

export interface ResultRecord {
  id: string;
  created_at: string;
  run_type: string;
  symbol: string;
  summary: { trades: TradeSummary; equity: EquitySummary };
  report: string;
  equity_curve: EquityPoint[];
  trades: (Trade & { strategy?: string })[];
}

// ── Forward test ──────────────────────────────────────────────────────────────
export interface ForwardTestRequest {
  symbol: string;
  starting_capital?: number;
  max_polls?: number;
  single_strategy?: boolean;
}

export interface ForwardTestStartResponse {
  status: string;
  symbol: string;
  max_polls: number;
  market_open: boolean;
  note: string | null;
}

export interface ForwardTestStatus {
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  symbol: string | null;
  last_run_id: string | null;
  error: string | null;
  market_open: boolean;
}

// ── Daily report (percent fields are 0-100) ───────────────────────────────────
export interface DailyReportRun {
  id: string;
  created_at: string;
  run_type: string;
  symbol: string;
  net_return: number;
  return_pct: number;
  win_rate: number;
  total_trades: number;
  total_costs: number;
  max_drawdown_pct: number;
}

export interface GroupRow {
  label: string;
  total: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  net: number;
}

export interface DailyReportTrade {
  entry_time: string | null;
  session: string | null;
  run_type: string | null;
  strategy?: string | null;
  structure?: string | null;
  lots?: number | null;
  exit_reason?: string | null;
  pnl?: number | null;
}

export interface DailyReport {
  date: string;
  totals: {
    runs: number;
    forward_tests: number;
    backtests: number;
    trades: number;
    wins: number;
    losses: number;
    win_rate: number | null;
    net_pnl: number;
    total_costs: number;
  };
  runs: DailyReportRun[];
  by_strategy: GroupRow[];
  by_session: GroupRow[];
  trades: DailyReportTrade[];
}

export interface ExportResult {
  ok: boolean;
  path: string;
  date?: string;
  month?: string;
  runs: number;
}
