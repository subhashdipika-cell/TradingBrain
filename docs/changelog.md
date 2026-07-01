# Changelog

All notable changes to TradingBrain will be documented here.

## TB-010 - Dhan candle feed for live ICT (2026-06-30)

- **Dhan candles**: `DhanCandleFeed` (`intraday_minute_data`) + module-level
  `candles_from_response` parser, mirroring AlphaEdge's `dhan_collector`
  (parallel OHLCV arrays, epoch-UTC -> IST). MT5 has no NSE data, so NIFTY
  structure for TB002 now comes from Dhan's Data API.
- **Client builder**: `build_dhan_client` uses the v2 `DhanContext` form (with
  fallback); `DhanFeed`/`DhanBroker` aligned to it.
- **Live ICT**: `application/ict_live.DhanLiveICT` pulls H1 + 5m (->15m) candles
  (throttled) and feeds the ICT detector, exposing `enrich(context)`.
- **Wired into forward testing**: `LivePaperTrader.from_dhan(enable_ict=True)`
  attaches the live ICT enricher as the engine's `context_enricher`, so TB002
  gets real setups during a forward test - no MT5 needed.
- Tests: 101 passing (incl. candle parser, guarded SDK paths).

## TB-009 - ICT setup detector (2026-06-30)

- **ICT primitives** (`tb002/ict_primitives.py`): fair value gaps, inversion
  (IFVG) detection, swing highs/lows (liquidity), and liquidity sweeps - pure
  functions on candle lists.
- **ICTDetector** (`tb002/detector.py`): assembles the four-layer model
  (directional sweep -> HTF inversion FVG within N candles -> 15m pullback FVG
  tapped -> LTF inversion trigger) and derives geometry (entry / stop above the
  swept high / first target >= 1.5R / external runner). Produces the
  ``tb002_setup`` metadata TB002 consumes; verified to round-trip into a TB002
  SELL signal (confidence 0.95, R:R 2.43).
- **Setup provider** (`tb002/setup_provider.py`): MT5 candle loader + resample
  (5m->15m) + `ICTSetupProvider.enrich(context)`.
- **Engine hook**: optional `context_enricher` called each bar to inject
  setups into the context.
- **Honest calibration finding**: over the 6 *calm* days of real AlphaEdge
  NIFTY H1 data the detector finds 0 complete setups - faithful to the model
  (HTF FVGs there invert in 28-29 candles, not <=2). ICT setups are
  volatility-driven and rare; the rules were not loosened to manufacture trades.
- Tests: 97 passing.

## TB-008 - Regime activation, forward testing, analysis, baskets (2026-06-30)

- **Regime-based activation**: the engine now drives the `StrategySelector` -
  TB001 (theta Iron Fly) in calm/RANGING regimes, TB002 (ICT liquidity-sweep
  inversion) in VOLATILE/TRENDING/REVERSAL/BREAKOUT (the "VIX kicked up"
  conditions from the source playbook). A trade is attributed to and managed
  by the strategy that opened it.
- **Directional execution**: TB002's directional view is executed as a
  defined-risk long option (long CALL/PUT), sized so premium (max loss) stays
  within the risk budget; spot-based target/stop.
- **Forward testing**: `python -m app.application.forward_test --symbol NIFTY`
  (or start_ForwardTest.bat) - live Dhan option chain + paper fills during
  market hours, regime-selected strategies, results saved. Credentials read
  from settings or AlphaEdge's dhan_config.json.
- **Launchers**: start_TradingBrain.bat / close_TradingBrain.bat (backend 8200
  + frontend 5174).
- **Analysis page**: backtest/forward-test runs persisted (`results_store`);
  `GET /results` + `/results/{id}`; dashboard "Analysis" tab listing past runs
  with metrics + equity curve + trade log.
- **Basket orders**: `Broker.submit_basket`; `DhanBroker` places multi-leg
  baskets hedge-first and aborts atomically if any leg is unresolvable (never
  sends a half-built spread).
- Tests: 90 passing.

## TB-007 - Hedged structures, live execution, regime selection (2026-06-30)

- **Hedged Iron Fly**: TB001 now trades a defined-risk Iron Fly (sell ATM
  straddle + buy OTM wings) by default. Engine generalized to leg-lists with
  **hedge-first execution** (BUY protective legs before SELL writes -> reduced
  spread margin) and shorts-first unwind. Sizing caps max-loss at the risk
  budget; margin/lot drops from ~Rs 2.25L (naked) to ~Rs 3-9k (real data).
  Black-Scholes fallback prices legs whose strike drifts out of the chain
  window, keeping hedged MTM balanced.
- **(d) Regime selector**: `strategy/selector.py` routes regime -> strategy
  (RANGING -> TB001 theta; REVERSAL/BREAKOUT -> TB002; sits out TRENDING/
  VOLATILE).
- **(a) Live execution**: `adapters/scrip_master.py` resolves option legs to
  Dhan security ids; `DhanBroker` places orders (dry-run default) respecting
  hedge-first.
- **(b) Live paper trading**: `application/live.py` `LivePaperTrader` (DhanFeed
  real data + PaperBroker simulated fills + kill switch + live logging).
- **(c) Dashboard real data**: `POST /api/v1/backtest/dhan` + a "Use real Dhan
  data" toggle in the frontend, driven by `DHAN_DATA_DIR`.
- Tests: 86 passing (incl. scrip master, DhanBroker dry-run, live runner,
  hedged/naked sizing).

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
