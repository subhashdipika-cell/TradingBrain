"""
TradingBrain

TB008 - Position Manager

Manages the open calendar structure: rolls / re-centres hedges as the market
moves and as the near expiry approaches. Kept as a clear extension point;
adjustments run through the hedging layer.
"""

from __future__ import annotations

from app.domains.strategy.tb008.configuration import TB008Configuration
from app.domains.strategy.tb008.models import CalendarStructure


class PositionManager:
    def __init__(self, config: TB008Configuration) -> None:
        self.config = config

    def should_adjust(self, structure: CalendarStructure, spot: float) -> bool:
        """
        Adjust when the underlying has drifted toward a sold strike (the near
        leg is gaining delta) - the point at which the source method re-centres
        hedges. Returns True when spot is within one weekly range of a sold leg.
        """
        band = spot * self.config.weekly_range_pct
        for leg in structure.sold_legs():
            if abs(leg.strike - spot) <= band:
                return True
        return False

    def should_roll_near_expiry(self, days_to_near_expiry: int) -> bool:
        """Roll the short legs to the next cycle once the near expiry is here."""
        return days_to_near_expiry <= 0
