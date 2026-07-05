# TradingBrain Backend

A modular options-trading platform. The first strategy, **TB001 - Dynamic
Theta Harvesting**, sells ATM short straddles on NIFTY/BANKNIFTY and harvests
option time decay (theta) under controlled risk.

## Architecture

The codebase is organized as cooperating domains under `app/domains`:

| Domain | Responsibility |
|--------|----------------|
| `shared` | enums, type aliases, value objects, utilities |
| `market` | Black-Scholes pricing & Greeks, option chain, session, expiry, instrument specs, candles |
| `portfolio` | positions, holdings, capital, Greeks exposure, mark-to-market PnL |
| `risk` | limits, position sizing, drawdown, kill switch, account-level risk engine |
| `execution` | `DataFeed`/`Broker` interfaces, synthetic backtest feed, paper broker, live adapter seams (MT5/Dhan/Zerodha) |
| `strategy` | `BaseStrategy` framework (`contracts`) + the TB001 implementation |
| `intelligence` | regime, sentiment, news, predictor, feature store, LLM reasoning (Claude seam), optimizer |
| `analytics` | trade statistics, performance metrics, journal, reports |

The **application layer** (`app/application`) hosts the `TradingEngine`
orchestrator and the backtest runner. The same engine runs a backtest, a paper
session, or live trading - only the `DataFeed` + `Broker` change.

## Running a backtest

From `backend/` with the virtualenv active:

```bash
python -m app.application.backtest                 # default: NIFTY, 30 sessions
python -m app.application.backtest --days 60 --symbol BANKNIFTY --capital 1500000
python -m app.application.backtest --iv 0.15 --days 40   # richer IV
```

It synthesizes intraday data + an option chain (no external data needed), runs
TB001 end-to-end, and prints a performance report (win rate, profit factor,
drawdown, Sharpe). The backtest is deterministic for a given `--seed`.

> Theta harvesting is profitable when **implied volatility exceeds realized
> volatility**. The synthetic feed lets you set both (`--iv` and `annual_vol`);
> with `realized > implied` the strategy correctly loses, demonstrating the
> engine models the volatility risk premium faithfully.

Programmatic use:

```python
from app.application.backtest import run_backtest, BacktestConfig
result = run_backtest(BacktestConfig(num_days=60, base_iv=0.14, annual_vol=0.10))
print(result.report)
```

## Tests

```bash
python -m pytest tests/ -q
```

## Going live (next steps)

Live trading is wired but credential-gated. Implement one adapter pair in
`app/domains/execution/adapters/` (Dhan is the natural fit for NSE index
options), then swap it into the engine in place of `BacktestFeed`/`PaperBroker`.
The LLM reasoning layer (`intelligence/llm_reasoning.py`) calls Claude
(`claude-opus-4-8`) and activates when `ANTHROPIC_API_KEY` is set.
