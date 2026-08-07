"""
TradingBrain
Market - Option Expiry Calendar

Helpers for index-option expiries. NIFTY weekly options expire on Thursday
(rolling to the prior trading day on a holiday - holiday handling is left to
a future calendar integration). The key output for theta harvesting is
``time_to_expiry_years`` which drives Black-Scholes valuation and decay.

Author: TradingBrain
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

# Standard NSE F&O expiry time (close of the expiry day).
EXPIRY_TIME = time(15, 30)

_MINUTES_PER_YEAR = 365.0 * 24.0 * 60.0


def next_weekly_expiry(reference: date, weekday: int = 3) -> date:
    """
    Next weekly expiry on/after ``reference``.

    ``weekday`` follows ``date.weekday()`` (Mon=0 .. Sun=6); default 3 == Thursday.
    """
    days_ahead = (weekday - reference.weekday()) % 7
    return reference + timedelta(days=days_ahead)


def next_monthly_expiry(reference: date, weekday: int = 3) -> date:
    """Last ``weekday`` (default Thursday) of ``reference``'s month, on/after it."""
    # Move to the first day of next month, step back to the last target weekday.
    if reference.month == 12:
        first_next = date(reference.year + 1, 1, 1)
    else:
        first_next = date(reference.year, reference.month + 1, 1)
    last_day = first_next - timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    monthly = last_day - timedelta(days=offset)
    if monthly < reference:
        return next_monthly_expiry(first_next, weekday)
    return monthly


def expiry_datetime(expiry: date) -> datetime:
    """The exact expiry instant (close of the expiry day)."""
    return datetime.combine(expiry, EXPIRY_TIME)


def time_to_expiry_years(now: datetime, expiry: date) -> float:
    """
    Time to expiry in years (calendar-time), clamped at 0.

    Calendar-time decay is used so theta accrues continuously through the
    day - the behaviour a short-premium strategy is designed to harvest.
    """
    expiry_dt = expiry_datetime(expiry)
    minutes = (expiry_dt - now).total_seconds() / 60.0
    if minutes <= 0.0:
        return 0.0
    return minutes / _MINUTES_PER_YEAR


def is_expiry_day(reference: date, weekday: int = 3) -> bool:
    return next_weekly_expiry(reference, weekday) == reference
