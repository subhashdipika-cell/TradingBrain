"""
TradingBrain
Application Layer

Use-case orchestration that wires the domains together: the trading engine
and the backtest runner.
"""

from app.application.engine import EngineConfig, TradingEngine

__all__ = ["EngineConfig", "TradingEngine"]
