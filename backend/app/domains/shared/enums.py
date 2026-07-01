"""
TradingBrain
Common Enumerations

This module contains all reusable enumerations shared across
domains, strategies, execution, risk and portfolio modules.

Author: TradingBrain
"""

from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"
    HOLD = "HOLD"
    NONE = "NONE"


class StrategyState(str, Enum):
    INITIALIZED = "INITIALIZED"
    WAITING = "WAITING"
    PRE_MARKET = "PRE_MARKET"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    EXITING = "EXITING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class MarketRegime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    BREAKOUT = "BREAKOUT"
    REVERSAL = "REVERSAL"
    UNKNOWN = "UNKNOWN"


class VolatilityRegime(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class TrendDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"
    UNKNOWN = "UNKNOWN"


class ExecutionMode(str, Enum):
    LIVE = "LIVE"
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"
    SIMULATION = "SIMULATION"


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExitReason(str, Enum):
    TARGET = "TARGET"
    STOP_LOSS = "STOP_LOSS"
    TRAILING_STOP = "TRAILING_STOP"
    MANUAL = "MANUAL"
    TIME_EXIT = "TIME_EXIT"
    RISK_EXIT = "RISK_EXIT"
    STRATEGY_EXIT = "STRATEGY_EXIT"
    KILL_SWITCH = "KILL_SWITCH"


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    COMMODITY = "COMMODITY"


class OptionRight(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class OptionStructure(str, Enum):
    """Multi-leg option structures a strategy can request."""

    SHORT_STRADDLE = "SHORT_STRADDLE"
    SHORT_STRANGLE = "SHORT_STRANGLE"
    LONG_STRADDLE = "LONG_STRADDLE"
    LONG_STRANGLE = "LONG_STRANGLE"
    LONG_CALL = "LONG_CALL"
    LONG_PUT = "LONG_PUT"
    SHORT_CALL = "SHORT_CALL"
    SHORT_PUT = "SHORT_PUT"
    # Defined-risk (hedged) premium-selling structures
    IRON_FLY = "IRON_FLY"  # short ATM straddle + long OTM wings
    IRON_CONDOR = "IRON_CONDOR"  # short OTM strangle + long further OTM wings


class Broker(str, Enum):
    DHAN = "DHAN"
    ZERODHA = "ZERODHA"
    BINANCE = "BINANCE"
    BYBIT = "BYBIT"
    PAPER = "PAPER"
