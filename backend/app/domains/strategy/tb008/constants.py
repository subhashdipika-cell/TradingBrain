"""
TradingBrain

TB008 - Adaptive Calendar Spread Engine (ACSE) - Constants
"""

from __future__ import annotations

from datetime import time

STRATEGY_ID = "TB008"
STRATEGY_NAME = "Adaptive Calendar Spread Engine"
STRATEGY_VERSION = "1.0.0"

# ---------------------------------------------------------------------
# Market timings (NSE)
# ---------------------------------------------------------------------
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
DEFAULT_ENTRY_TIME = time(9, 25)
NO_NEW_ENTRY_AFTER = time(15, 0)

# ---------------------------------------------------------------------
# Volatility regime (India VIX points)
# ---------------------------------------------------------------------
# The strategy is designed for LOW VIX. Below ~ this it is favourable.
VIX_LOW_MAX = 14.0  # <= this = LOW (favourable)
VIX_MEDIUM_MAX = 20.0  # <= this = MEDIUM
# above VIX_MEDIUM_MAX = HIGH (stand aside)

# Below this, volatility is unusually compressed and likely to EXPAND, so the
# transcript "loosens out" the centre profit for an even flatter payoff.
VIX_EXPANSION_RISK = 11.0

# ---------------------------------------------------------------------
# Structure defaults (from the transcript)
# ---------------------------------------------------------------------
# Sell far-OTM ~2-delta options on the NEAR expiry.
TARGET_SELL_DELTA = 0.02
SELL_LOTS = 3

# Ratio calendar hedge on the FAR (next) expiry: (target_delta, lots) per side.
# One close-ish protective leg + two further-out legs => 3 hedges for 3 sold.
HEDGE_LEGS = ((0.30, 1), (0.15, 2))

# Expected weekly range as a fraction of spot (market stays inside ~2% ~85% of
# the time). Used as a fallback; TradingBrain derives it from IV/expected move.
DEFAULT_WEEKLY_RANGE_PCT = 0.02

# ---------------------------------------------------------------------
# Profit / risk targets
# ---------------------------------------------------------------------
WEEKLY_PROFIT_TARGET_PCT = 0.01  # 1% of margin, in hand -> exit early
MAX_MARGIN_UTILISATION = 0.50  # cap deployed margin per trade
MAX_LOSS_PCT = 0.03  # of margin
MAX_MTM_SWING_PCT = 0.02  # of margin - the "safe feeling" ceiling

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
LOGGER_NAME = "TB008"
