from datetime import datetime

from app.domains.market.expiry import next_weekly_expiry, time_to_expiry_years
from app.domains.market.option_chain import build_synthetic_chain
from app.domains.market.symbol import NIFTY
from app.domains.shared.enums import ExecutionMode, OptionRight
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.credit_sellers import IronCondorStrategy


def _context(*, live_chain: bool = False) -> MarketContext:
    timestamp = datetime(2026, 6, 30, 10, 0)
    expiry = next_weekly_expiry(timestamp.date())
    chain = build_synthetic_chain(
        spec=NIFTY,
        spot=25_000.0,
        expiry=expiry,
        timestamp=timestamp,
        time_to_expiry=time_to_expiry_years(timestamp, expiry),
        implied_vol=0.20,
    )
    context = MarketContext(
        symbol="NIFTY",
        exchange="NSE",
        timeframe="5m",
        timestamp=timestamp,
        execution_mode=ExecutionMode.BACKTEST,
        is_market_open=True,
        last_price=25_000.0,
        minutes_from_open=60,
        minutes_to_close=300,
    )
    context.metadata["option_chain"] = chain
    context.metadata["live_chain"] = live_chain
    return context


def test_credit_strategy_selects_delta_based_legs():
    signal = IronCondorStrategy().generate_signal(_context())
    assert signal is not None
    legs = signal.metadata["legs"]
    context_chain = _context().metadata["option_chain"]
    short_deltas = []
    for leg in legs:
        if leg["side"] != "SELL":
            continue
        right = OptionRight.CALL if leg["right"] == "CALL" else OptionRight.PUT
        short_deltas.append(abs(context_chain.get(leg["strike"], right).greeks.delta))
    assert short_deltas
    assert all(0.05 <= delta <= 0.35 for delta in short_deltas)


def test_live_chain_without_microstructure_is_rejected():
    context = _context(live_chain=True)
    assert IronCondorStrategy().generate_signal(context) is None
    assert "liquidity" in context.metadata["entry_rejection"]
