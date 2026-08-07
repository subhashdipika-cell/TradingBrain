# Changelog

All notable changes to TradingBrain will be documented here.

## TB-006 - Dhan data integration (2026-06-30)

- **historical**: `execution/historical_feed.py` replays stored CSV data via
  the `DataFeed` interface - `UnderlyingHistoricalFeed` (index OHLC -> BS
  chain) and `OptionChainHistoricalFeed` (real per-strike premiums). Added
  `from_dhan_csv`/`from_dhan_dir` matching AlphaEdge's `dhan_options_collector`
  schema (UTC->IST, IV percent->fraction, real Dhan delta/theta/vega).
- **verified on real data**: TB001 backtested over 1,030 real NIFTY option
  snapshots from `AlphaEdge/strategy-lab/data/options` (6 sessions), net of
  real NSE costs. CLI: `python -m app.application.backtest --dhan-dir <dir>
  --symbol NIFTY50`.
- **live**: `adapters/dhan_adapter.DhanFeed` polls `dhanhq.option_chain(...)`
  into `MarketSnapshot`s (pair with `PaperBroker` for live paper trading).
  `DhanBroker` (real-money) left guarded pending scrip-master + execution
  testing. `DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` added to settings.
- **misc**: `OptionChain.nearest_strike()` for robust ATM on real chains;
  `NIFTY50`->`NIFTY` alias; `SENSEX` instrument spec.

## TB-005 - Transaction costs + frontend (2026-06-30)

- **costs**: realistic NSE F&O transaction-cost model (`execution/costs.py`) -
  flat options brokerage, STT (sell), exchange, SEBI, GST, stamp (buy). Wired
  into the paper broker so backtest PnL is net-of-cost (~Rs 123 per 1-lot
  straddle round trip). Reports now show gross-vs-net and total cost drag.
- **API**: `POST /api/v1/backtest/run` and `GET /api/v1/backtest/symbols`.
- **frontend**: Vite + React + TypeScript dashboard on port 5174 (backend
  8200) - backtest form, summary cards (incl. costs), SVG equity curve, trade
  log, text report. Full stack verified live (health, CORS, backtest POST).

## TB-004 - Runnable platform core (2026-06-30)

End-to-end backtestable platform around TB001 (Dynamic Theta Harvesting).

- **market**: Black-Scholes-Merton pricing & Greeks (incl. implied vol),
  synthetic option chain + ATM selection, NSE session timings, weekly/monthly
  expiry calendar, instrument specs (NIFTY/BANKNIFTY/FINNIFTY), candles/ATR.
- **portfolio**: signed positions with avg-price/realized-PnL accounting,
  holdings, capital + high-water-mark, net Greeks exposure, mark-to-market.
- **risk**: limits, margin/risk-based position sizing, drawdown tracker,
  latching kill switch, account-level risk engine (daily-loss & drawdown gates).
- **execution**: `DataFeed`/`Broker` interfaces, deterministic synthetic
  backtest feed, paper broker (slippage + commission), live adapter seams for
  MT5 / Dhan / Zerodha.
- **application**: `TradingEngine` orchestrator (bar loop, multi-leg straddle
  lifecycle, target/stop/square-off exits) + CLI backtest runner.
- **analytics**: trade statistics, equity-curve performance (drawdown, Sharpe),
  journal, text report.
- **intelligence**: regime classifier, sentiment, news engine, momentum
  predictor, feature store, context enricher, grid-search optimizer, and an
  LLM reasoning layer (offline heuristic default + guarded Claude seam).
- **tests**: 46 passing (framework, greeks, portfolio, risk, intelligence,
  and a deterministic end-to-end backtest).

## TB-003 - Strategy framework (2026-06-30)

- `BaseStrategy` abstract lifecycle (`contracts/strategy.py`), `MarketContext`,
  `Signal`, `State`, and `StrategyRegistry`.
- `TB001Configuration` with validation; TB001 wired to emit option-structured
  short-straddle signals.
