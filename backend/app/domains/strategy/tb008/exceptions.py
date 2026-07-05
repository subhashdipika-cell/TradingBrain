"""
TradingBrain

TB008 - Adaptive Calendar Spread Engine - Exceptions
"""

from __future__ import annotations


class TB008Exception(Exception):
    """Base exception for TB008."""


class StrategyConfigurationError(TB008Exception):
    """Invalid TB008 configuration."""


class InvalidVolatilityRegimeError(TB008Exception):
    """Volatility regime could not be determined."""


class StructureConstructionError(TB008Exception):
    """The calendar structure could not be built (e.g. missing strikes)."""


class PayoffEvaluationError(TB008Exception):
    """The payoff profile could not be evaluated."""
