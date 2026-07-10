"""
TradingBrain
Market Context Contract
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domains.shared.enums import (
    ExecutionMode,
    MarketRegime,
    TrendDirection,
    VolatilityRegime,
)


@dataclass(slots=True)
class MarketContext:
    """
    Standardized market information available to every strategy.
    """

    # Instrument
    symbol: str
    exchange: str
    timeframe: str
    timestamp: datetime
    execution_mode: ExecutionMode

    # Market State
    market_regime: MarketRegime = MarketRegime.UNKNOWN
    volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL
    trend: TrendDirection = TrendDirection.UNKNOWN

    # OHLC
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    close_price: float = 0.0
    last_price: float = 0.0
    previous_close: float = 0.0

    # Volatility
    atr: float = 0.0
    implied_volatility: float = 0.0
    historical_volatility: float = 0.0
    vix: float = 0.0

    # Trend
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    adx: float = 0.0

    # Greeks
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0

    # Open Interest (from the live/synthetic option chain; None when the
    # chain carries no usable OI - see OptionChain.has_oi_data)
    max_call_oi_strike: float | None = None  # resistance: heaviest call OI
    max_put_oi_strike: float | None = None   # support: heaviest put OI
    pcr: float | None = None                 # total put OI / total call OI
    max_pain_strike: float | None = None

    # Session
    is_market_open: bool = False
    is_expiry: bool = False
    minutes_from_open: int = 0
    minutes_to_close: int = 0

    # Intelligence
    sentiment_score: float = 0.0
    news_score: float = 0.0
    confidence: float = 0.0

    # Extension Points
    indicators: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)