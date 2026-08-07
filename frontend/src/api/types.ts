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
