"""
TradingBrain

TB007 - Strategy Constants

Convexity Buy - a long-volatility option BUYER. The deliberate mirror of the
short-premium book (TB001 Iron Fly / TB003-006 credit sellers): instead of
selling theta into a coiled market, it BUYS a cheap, defined-risk long option
when volatility is low AND price is compressed, then rides the expansion.

Design principle (Taleb, Fooled by Randomness): buying options is only a
big-move edge when the payoff is genuinely convex AND cheap (low IV, real
asymmetry) - not when you're paying decay on a directional guess.
"Convexity is not any cheap option."
"""

from __future__ import annotations

from datetime import time

# ---------------------------------------------------------------------
# Strategy Information
# ---------------------------------------------------------------------

STRATEGY_ID = "TB007"
STRATEGY_NAME = "Convexity Buy"
STRATEGY_VERSION = "1.0.0"

# ---------------------------------------------------------------------
# Market Timings (Indian Market)
# ---------------------------------------------------------------------

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# Avoid the volatile open (the platform also enforces a 10:15 open cutoff -
# the open window destroyed the short-premium book in the live audits).
DEFAULT_ENTRY_TIME = time(10, 15)
NO_NEW_ENTRY_AFTER = time(15, 0)

# ---------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------

# CHEAP gate: only buy when implied vol is low (a proxy for "convexity on
# sale"). Expressed as an annualised fraction (0.13 = 13%). A future refinement
# is an India-VIX percentile rank; an absolute ceiling is the deterministic v1.
DEFAULT_MAX_ENTRY_IV = 0.13

# COILED gate: require a Bollinger squeeze (bandwidth in the bottom 30% of its
# recent range) that is still "live" within this many bars of the breakout.
DEFAULT_SQUEEZE_GRACE_BARS = 3

# NOT-PAYING-DECAY gate: skip expiry-day (0-DTE) buys - pure theta gambling.
DEFAULT_BLOCK_EXPIRY_DAY = True

# ---------------------------------------------------------------------
# Structure / exits
# ---------------------------------------------------------------------

# Payoff asymmetry: spot target = entry +/- TARGET_R x (entry - stop). The
# option is convex on top of this, so the realised payoff ratio is even better.
DEFAULT_TARGET_R = 3.0

# Structure mode:
#   False -> directional squeeze-break (long CALL/PUT on the break) - the
#            validated v1 that fits the engine's directional debit path.
#   True  -> delta-neutral LONG STRADDLE (buy ATM call + put on the coil, no
#            directional guess) - the more Taleb-faithful form; profits from a
#            large move either way. Uses the engine's LONG_VOL (DEBIT) path.
DEFAULT_NEUTRAL_STRADDLE = False

# LONG_STRADDLE MTM exits (fractions of the debit paid):
#   bank when the straddle gains this much, cut to trim theta before the floor.
DEFAULT_STRADDLE_TARGET_PCT = 0.60  # +60% of debit -> the expansion delivered
DEFAULT_STRADDLE_STOP_PCT = 0.50  # -50% of debit -> cut the bleed (max loss = debit)

# Overnight holding (straddle mode only). The intraday 15:15 square-off caps a
# convex bet before the expansion can develop; letting the straddle breathe for
# a few sessions is the point. Bounded by ``max_hold_sessions`` and always
# closed on/before expiry (never a 0-DTE overnight).
DEFAULT_HOLD_OVERNIGHT = False
DEFAULT_MAX_HOLD_SESSIONS = 2

# ---------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------

# Premium paid IS the max loss (defined risk). Risk a small, fixed slice per
# trade - the win rate is low by design, so sizing must survive the bleed.
DEFAULT_REQUESTED_RISK = 0.01  # 1% of capital per convex bet
MAX_STRATEGY_DRAWDOWN = 0.10
MAX_DAILY_LOSS = 0.04

DEFAULT_CONFIDENCE = 0.55
DEFAULT_INITIAL_CAPITAL = 0.25  # capital allocation fraction

LOGGER_NAME = "TB007"
