"""
TradingBrain

TB001 - Strategy Exceptions
"""

from __future__ import annotations


class TB001Exception(Exception):
    """
    Base exception for the TB001 strategy.
    """


class StrategyConfigurationError(TB001Exception):
    """
    Raised when the strategy configuration is invalid.
    """


class StrategyInitializationError(TB001Exception):
    """
    Raised when strategy initialization fails.
    """


class InvalidMarketContextError(TB001Exception):
    """
    Raised when MarketContext is invalid or incomplete.
    """


class InvalidSignalError(TB001Exception):
    """
    Raised when a generated signal is invalid.
    """


class PositionManagementError(TB001Exception):
    """
    Raised when position management fails.
    """


class StrikeAdjustmentError(TB001Exception):
    """
    Raised when strike adjustment cannot be completed.
    """


class RiskValidationError(TB001Exception):
    """
    Raised when strategy risk validation fails.
    """


class RegimeDetectionError(TB001Exception):
    """
    Raised when market regime cannot be determined.
    """