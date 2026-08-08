# TradingBrain Quantitative Trading Audit

Date: 2026-08-09
Scope: live Dhan feed, market structure, strategy routing, option selection,
execution, risk and exits.

## Executive summary

The low trade count and poor forward-test results have three primary causes:

1. **The live option feed is not producing real candles.** In
   `backend/app/domains/execution/adapters/dhan_adapter.py`, `DhanFeed._poll_once`
   creates a candle with `open == high == low == close == under_ltp` on every
   option-chain poll. The engine therefore computes structure from a sequence of
   flat snapshots rather than OHLC bars. This makes ATR/ADX/EMA unreliable and
   routes the selector toward sideways/default strategies.
2. **The selector uses absolute IV regimes, not volatility edge.**
   `backend/app/domains/strategy/selector.py::_structure_router` ignores
   `context.vix`, IV percentile/rank, IV-versus-realized volatility, skew and
   event risk. It even routes low-IV ranges to TB001 Iron Fly, despite TB001 now
   rejecting low IV. This creates both false “no strategy” decisions and premium
   selling when the compensation is poor.
3. **Most credit strategies use static strike distances and have weak execution
   protection.** `backend/app/domains/strategy/credit_sellers.py` chooses
   `short_otm`/`wing_otm` strike steps, not target delta. `DhanBroker` sends
   market orders, does not check bid/ask width or open interest, and reports the
   snapshot price as a fill before trade-book reconciliation.

## Module 1 — Market structure identification

### Findings

- `tb002/ict_primitives.py::swing_high_indices` and `swing_low_indices` use
  `left=2, right=2` by default. This is not inherently too strict; it is a
  normal five-bar pivot and correctly waits for two bars to the right. It is
  strict when combined with the detector’s full chain:
  HTF sweep -> inverted FVG -> 15-minute pullback -> LTF inversion -> 1.5R
  geometry. That explains rare TB002 signals.
- The swing detector has no ATR, tick-size or percentage prominence filter.
  A one-tick wick can become a swing and a sweep. Add a minimum prominence such
  as `max(tick_size, atr * 0.10, price * 0.0002)`.
- `find_fvgs` accepts any positive gap. There is no minimum gap size, so tiny
  micro-gaps can satisfy the IFVG chain.
- `ICTDetector._directional_sweep` and `_pullback` search the entire supplied
  history and do not enforce a maximum age relative to `now`. A stale sweep or
  stale FVG can remain eligible indefinitely.
- `DhanLiveICT.refresh` fetches Dhan intraday data and immediately builds the
  provider. `candles_from_response` does not remove the latest forming candle.
  That can repaint the latest FVG, sweep, and inversion state.
- `setup_provider.resample` groups candles by array position rather than by
  session/date and aligned time bucket. A missing candle shifts every later
  15-minute bucket and can corrupt the multi-timeframe structure.
- The normal engine indicator path (`application/engine.py::_build_context`)
  does use `analyse` and a rolling candle list, but DhanFeed supplies flat
  candles. The indicator code is therefore technically present but receives
  invalid inputs in live mode.

### Recommended structure detector

The detector should operate only on completed, time-aligned candles and expose
the reason a setup was rejected:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass(frozen=True)
class StructureSignal:
    regime: str
    direction: str
    confirmed_at: datetime
    level: float | None
    reason: str

def closed_candles(candles, now, timeframe_minutes):
    cutoff = now.replace(second=0, microsecond=0)
    cutoff -= timedelta(minutes=cutoff.minute % timeframe_minutes)
    return [
        c for c in candles
        if c.timestamp + timedelta(minutes=timeframe_minutes) <= cutoff
    ]

def prominent_swing(candles, i, *, atr, tick_size=0.05):
    level = candles[i].high
    prominence = max(tick_size, (atr or 0.0) * 0.10,
                     abs(level) * 0.0002)
    left = max(c.high for c in candles[max(0, i - 2):i])
    right = max(c.high for c in candles[i + 1:i + 3])
    return level - max(left, right) >= prominence

def confirmed_bos(close, level, atr, *, min_atr=0.15):
    # Require a close beyond the level, not a wick, with a volatility buffer.
    return close > level + max((atr or 0.0) * min_atr, level * 0.0002)
```

Use 15-minute candles for macro regime and 3/5-minute completed candles for
the trigger. Keep the last candle out of both calculations until its end time
has passed. Require a BOS close beyond an ATR/percentage buffer and invalidate
setups after a configurable age, for example 12 LTF bars.

## Module 2 — Strategy mapping and strike selection

### Findings

- `_structure_router` has the correct directional intent for normal regimes:
  bullish trend -> TB005 Bull Put, bearish trend -> TB006 Bear Call, range ->
  TB001/TB004, breakout/reversal -> TB002.
- It is not volatility-aware enough. `context.vix` is populated by DhanFeed but
  never used by the resolver. No IV percentile, IV rank, IV-RV spread, skew,
  event flag or expected-move comparison is passed into the matrix.
- Low IV range -> TB001 is economically backwards for a premium seller unless
  a strong realized-volatility edge exists. It also conflicts with TB001’s
  low-volatility gate, which is a direct source of skipped trades.
- `credit_sellers.py` uses `short_otm` and `wing_otm` index offsets. This is a
  major risk: 2 or 3 strikes OTM can mean very different deltas across expiry,
  IV and symbols. TB008 already has a reusable `select_by_delta` helper, but
  the credit strategies do not use it.
- TB001 is ATM-centered and TB004/TB005/TB006 use fixed index distances. There
  is no check that the resulting short legs have the intended delta, credit /
  width ratio, or acceptable bid/ask spread.

### Recommended selector matrix

Use structure plus volatility edge, not structure alone:

```python
def choose_strategy(ctx):
    ivp = float(ctx.metadata.get("iv_percentile", 0.0))
    rv = float(ctx.historical_volatility or 0.0)
    iv = float(ctx.implied_volatility or 0.0)
    iv_edge = iv - rv if rv > 0 else 0.0
    vix = float(ctx.vix or 0.0)

    if ctx.metadata.get("event_risk"):
        return None
    if ivp < 25 and iv_edge <= 0:
        return None                    # do not sell cheap volatility
    if vix >= 28 or ctx.volatility_regime.value == "EXTREME":
        return "TB004"                 # defined-risk only
    if ctx.market_regime.value == "RANGING":
        return "TB001" if ivp >= 60 else "TB004"
    if ctx.trend.value == "BULLISH":
        return "TB005"                 # delta-selected bull put spread
    if ctx.trend.value == "BEARISH":
        return "TB006"                 # delta-selected bear call spread
    return None
```

Strike selection should target deltas, for example short 0.15–0.20 delta and
hedge 0.05–0.10 delta, then validate the net credit as a fraction of spread
width. Never fall back silently to a fixed 100-point or fixed-strike offset.

## Module 3 — Dhan data and execution

### Findings

- `DhanFeed` is polling `option_chain` every 3.5 seconds. It is not consuming a
  Dhan WebSocket tick stream and has no tick-to-candle aggregator.
- `_poll_once` creates zero-range candles. This is the most important live data
  defect because all engine indicators consume these candles.
- There is no sequence number, timestamp deduplication, gap detection or stale
  snapshot rejection. A delayed API response can be processed as if it were a
  fresh bar.
- `DhanCandleFeed.fetch_intraday` does not remove the current incomplete candle.
  `candles_from_response` also trusts parallel arrays without checking monotonic
  timestamps or duplicate timestamps.
- `DhanBroker.submit` uses `order_type="MARKET"` by default and passes
  `price=0`. It does not verify bid/ask, OI, volume, quote age, or a maximum
  slippage budget.
- The broker returns a synthetic fill at `snapshot.option_price`. For real
  orders, this is not the fill price. The code comments acknowledge this, but
  the engine can still size exits and record PnL before trade-book reconciliation.
- `submit_basket` resolves contracts first but then places each leg sequentially.
  A rejected or delayed leg can leave a temporary unhedged position. The engine
  now rolls back incomplete paper baskets, but a live broker must reconcile
  order status and hedge immediately.

### Recommended Dhan execution wrapper

Extend `OptionQuote` with `bid`, `ask`, `open_interest`, `volume`, and
`quote_timestamp`, then gate every sell:

```python
from datetime import datetime, timedelta

def verify_liquidity(quote, *, now: datetime, max_spread_pct=0.08,
                     min_oi=100_000, min_volume=1_000,
                     max_quote_age=5.0):
    if quote.bid <= 0 or quote.ask <= quote.bid:
        return False, "missing/invalid bid-ask"
    mid = (quote.bid + quote.ask) / 2
    if (quote.ask - quote.bid) / mid > max_spread_pct:
        return False, "bid-ask spread too wide"
    if quote.open_interest < min_oi:
        return False, "open interest too low"
    if quote.volume < min_volume:
        return False, "volume too low"
    if (now - quote.quote_timestamp).total_seconds() > max_quote_age:
        return False, "stale quote"
    return True, "liquid"

def limit_price_for_sell(quote, max_slippage_pct=0.02):
    # Start at bid; do not cross an uncontrolled spread.
    mid = (quote.bid + quote.ask) / 2
    return max(quote.bid, mid * (1 - max_slippage_pct))
```

Use a limit order at the verified price, wait for an order-update/trade-book
fill, and cancel/reprice with a bounded number of attempts. If any leg fails,
buy back filled short legs and keep the strategy state flat. Log the rejection
reason rather than returning only `None`.

## Module 4 — Risk and exits

### Findings

- The platform `RiskEngine` has a max daily loss and max drawdown circuit breaker;
  this part exists and is active in `TradingEngine._on_bar`.
- Defaults are broad for short options: `max_daily_loss=0.05`,
  `max_drawdown=0.10`, and `max_trades_per_day=10`. A premium-selling system
  should usually use a smaller daily stop and a hard per-strategy loss budget.
- `RiskLimits.max_net_delta`, `max_net_gamma`, and `max_total_exposure` are
  declared but not enforced by `RiskEngine.approve_entry` or `update`.
- `TB001.risk_layer` has placeholder methods that always return `False`.
- `CreditSellStrategy.manage_position` and `manage_risk` are no-ops. There is
  no rolling of an untested side, delta re-centering, or partial reduction.
- The engine’s credit exits are based on total structure premium expansion and
  time square-off. This is useful as a backstop, but not enough by itself for a
  short strangle/condor: the untested-side delta and portfolio gamma should be
  monitored as the underlying moves.
- A 30–50% premium stop is not equivalent to a maximum account loss. Gap moves,
  slippage, and multi-leg execution can exceed it. Risk sizing should be based
  on defined maximum loss plus an execution buffer.

## Implementation priorities

1. Replace flat Dhan polling candles with completed, time-aligned OHLC bars and
   reject stale/duplicate data.
2. Add IV percentile/IV-RV edge and event-risk inputs to the selector; stop
   routing low-IV ranges to ATM premium selling.
3. Convert TB003–TB006 strike selection to delta targets and enforce liquidity,
   credit/width and quote-age checks.
4. Enforce portfolio delta/gamma/exposure limits before entry and continuously.
5. Add rejection-reason logging at every gate:
   `structure`, `iv_edge`, `liquidity`, `strike_delta`, `risk`, `execution`.

These changes should be validated on a timestamped historical replay and then
forward-tested in paper mode. A higher trade count alone is not a success
criterion; the acceptance criteria should include positive expectancy after
costs, bounded tail loss, and no stale/forming-candle signals.
