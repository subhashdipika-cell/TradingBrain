"""
TradingBrain
Risk - Kill Switch

A latching emergency stop. Once tripped it blocks all new entries until
explicitly reset (typically next session). Tripping is sticky on purpose: a
breached risk limit should not silently re-arm intraday.

Author: TradingBrain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class KillSwitch:
    """Latching emergency stop for the trading engine."""

    tripped: bool = False
    reason: str = ""
    tripped_at: datetime | None = None
    history: list[tuple[datetime, str]] = field(default_factory=list)

    def trip(self, reason: str, when: datetime | None = None) -> None:
        if self.tripped:
            return
        self.tripped = True
        self.reason = reason
        self.tripped_at = when or datetime.utcnow()
        self.history.append((self.tripped_at, reason))

    @property
    def is_active(self) -> bool:
        return self.tripped

    def allow_new_entries(self) -> bool:
        return not self.tripped

    def reset(self) -> None:
        """Re-arm the switch (does not clear history)."""
        self.tripped = False
        self.reason = ""
        self.tripped_at = None
