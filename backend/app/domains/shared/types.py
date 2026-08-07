"""
TradingBrain
Shared Type Aliases

Lightweight semantic aliases used across domains. They document intent
(a ``Price`` is conceptually different from a ``Quantity``) without adding
runtime overhead.

Author: TradingBrain
"""

from __future__ import annotations

from typing import TypeAlias

# Identifiers
Symbol: TypeAlias = str
StrategyId: TypeAlias = str
OrderId: TypeAlias = str
TradeId: TypeAlias = str

# Numeric domains (INR for this platform)
Money: TypeAlias = float
Price: TypeAlias = float
Quantity: TypeAlias = int
Lots: TypeAlias = int

# Rates / ratios expressed as fractions (0.10 == 10%)
Rate: TypeAlias = float
Fraction: TypeAlias = float
Basis: TypeAlias = float

# Time expressed in trading-relevant units
Years: TypeAlias = float
Minutes: TypeAlias = int
