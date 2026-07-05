"""
TradingBrain

TB002 - Strategy Exceptions
"""

from __future__ import annotations


class TB002Exception(Exception):
    """Base exception for the TB002 strategy."""


class StrategyConfigurationError(TB002Exception):
    """Raised when the strategy configuration is invalid."""


class InvalidSetupError(TB002Exception):
    """Raised when a TB002 setup payload cannot be parsed."""
