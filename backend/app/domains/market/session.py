"""
TradingBrain
Market - Trading Session (NSE)

Encapsulates NSE cash/F&O session timings and derives the
session-relative fields the strategy reads from MarketContext
(``is_market_open``, ``minutes_from_open``, ``minutes_to_close``).

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(frozen=True, slots=True)
class TradingSession:
    """An exchange trading session defined by open/close times."""

    open_time: time = time(9, 15)
    close_time: time = time(15, 30)

    def is_open(self, moment: datetime) -> bool:
        """True when ``moment`` falls within the session on a weekday."""
        if moment.weekday() >= 5:  # Sat/Sun
            return False
        return self.open_time <= moment.time() <= self.close_time

    def minutes_from_open(self, moment: datetime) -> int:
        """Minutes elapsed since the open (0 before open)."""
        opened = datetime.combine(moment.date(), self.open_time)
        delta = (moment - opened).total_seconds() / 60.0
        return max(0, int(delta))

    def minutes_to_close(self, moment: datetime) -> int:
        """Minutes remaining until the close (0 after close)."""
        closed = datetime.combine(moment.date(), self.close_time)
        delta = (closed - moment).total_seconds() / 60.0
        return max(0, int(delta))

    def session_length_minutes(self) -> int:
        open_dt = datetime.combine(date.min, self.open_time)
        close_dt = datetime.combine(date.min, self.close_time)
        return int((close_dt - open_dt).total_seconds() / 60.0)

    def is_after(self, moment: datetime, cutoff: time) -> bool:
        """True when ``moment`` is at/after ``cutoff`` on its day."""
        return moment.time() >= cutoff


# Default NSE session shared across the platform.
NSE_SESSION = TradingSession()
