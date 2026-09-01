"""
TradingBrain

TB001 - Strategy Constants
"""

from __future__ import annotations

from datetime import time

# ---------------------------------------------------------------------
# Strategy Information
# ---------------------------------------------------------------------

STRATEGY_ID = "TB001"
STRATEGY_NAME = "Dynamic Theta Harvesting"
STRATEGY_VERSION = "1.0.0"

# ---------------------------------------------------------------------
# Market Timings (Indian Market)
# ---------------------------------------------------------------------

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

DEFAULT_ENTRY_TIME = time(9, 20)

NO_NEW_ENTRY_AFTER = time(15, 0)

# ---------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------

DEFAULT_CONFIDENCE = 0.0

DEFAULT_SCORE = 0.0

DEFAULT_REQUESTED_RISK = 0.02

# ---------------------------------------------------------------------
# Risk Limits
# ---------------------------------------------------------------------

MAX_STRATEGY_DRAWDOWN = 0.10

MAX_DAILY_LOSS = 0.10

MAX_POSITION_RISK = 0.02

# ---------------------------------------------------------------------
# Strategy Parameters
# ---------------------------------------------------------------------

DEFAULT_SHIFT_MULTIPLIER = 1.0

DEFAULT_MIN_PREMIUM = 60.0

DEFAULT_INITIAL_CAPITAL = 0.33

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

LOGGER_NAME = "TB001"
