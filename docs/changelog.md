# Changelog

All notable changes to TradingBrain will be documented here.

## TB-013 - NSE holiday calendar + intraday entry cutoff (2026-07-05)

- **Holiday calendar** (`app/domains/market/holidays.py`): NSE trading
  holidays refreshed once per IST day from Dhan's public holiday page
  (https://dhan.co/market-holiday/ — only the trading-holiday table; clearing
  holidays are normal trading days), cached to disk, hardcoded 2026 fallback.
  `run_forward_test` now refuses to start on weekends/holidays with a clear
  reason (surfaces in `/forward-test/status`).
- **Entry cutoff**: platform-wide `ENTRY_CUTOFF = 15:05` in the engine bar
  loop — no NEW positions after 15:05 IST (square-off remains 15:15, NSE
  close 15:30), applied identically in backtests and live/forward runs.

## TB-012 - TB008 two-expiry execution + India VIX (2026-07-03)

- **Multi-expiry snapshot**: `MarketSnapshot` now carries an optional
  next-expiry chain (`far_chain`, `far_expiry`, `far_time_to_expiry`) and a real
  `vix` field. `option_price(right, strike, far=True)` prices/marks a leg against
  the far chain + its time-to-expiry, so calendar legs are consistent across
  both expiries.
- **India VIX wired end to end**: `DhanFeed._get_vix` fetches real India VIX via
  `intraday_minute_data` (security_id 21, IDX_I / INDEX), throttled
  (`vix_refresh_seconds`). It flows snapshot.vix -> `MarketContext.vix` ->
  TB008. When VIX is unavailable (0.0) the strategy falls back to an ATM-focused
  IV proxy; the Dhan ATM-IV average is now taken only over strikes within +-2 of
  ATM (skew fix), not the whole wide window.
- **Engine CALENDAR path**: `_open_calendar` sizes by `budget // margin`, builds
  near/far legs (far instruments get an `_F` suffix to avoid key collisions),
  submits BUY hedges before SELLs, and records margin / 1%-of-margin profit
  target / max-loss. `_manage_open_trade` exits a calendar on rupee PnL vs
  target/stop; `_mark_portfolio` marks each leg against its own expiry bucket.
  `Order` carries `expiry_bucket`; `PaperBroker` prices far fills correctly.
- **Feeds**: `BacktestFeed(include_far, strikes_each_side)` emits a synthetic
  next-expiry chain; `DhanFeed(include_far=...)` resolves near + far expiries.
  `LivePaperTrader.from_dhan` turns both on automatically for TB008 (wider
  `atm_range=40` for the ~2-delta strikes).
- **Forward test**: `ForwardTest(TB008).bat` runs TB008 with Rs 10L capital
  (calendar margin ~Rs 2L/structure). Verified end to end: 13 double-calendar
  trades through the engine, correct two-expiry marking, TARGET/TIME_EXIT exits.
- Tests: +1 engine E2E (`test_tb008_engine`), TB008 suite 8; 110 passing,
  1 skipped. Ruff + black clean.

## TB-011 - TB008 Adaptive Calendar Spread Engine (2026-07-03)

- New strategy `app/domains/strategy/tb008` (ACSE): low-VIX double-calendar
  income - sell a far-OTM (~2-delta) strangle on the near expiry, hedge with a
  next-expiry RATIO calendar to flatten MTM, analyse the payoff, bank ~1%
  weekly early. Full layer set per the design: constants, exceptions, models,
  configuration, regime (VIX classifier), payoff_engine (central), core_layer,
  hedging_layer, risk_layer, position_manager, state_machine, strategy, plus a
  delta-based selection helper.
- **Payoff engine** evaluates the structure at the near expiry (near legs ->
  intrinsic, far legs -> BS time value): max profit/loss, breakevens, profit
  band, margin (~Rs 2L for NIFTY 3-lot, matches source), margin efficiency and
  MTM smoothness. Verified: bounded loss, smoothness ~0.87.
- Registered in the selector (available for `--strategy TB008`), but NOT
  auto-routed: it needs BOTH near + next-expiry chains
  (`context.metadata['option_chain']` + `['option_chain_far']`). With the
  current single-expiry feed it stands aside safely (never mis-executes). A
  multi-expiry feed unlocks live execution.
- Tests: 7 for TB008 (regime gating, structure build, payoff, exit, registry);
  109 total passing.

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
