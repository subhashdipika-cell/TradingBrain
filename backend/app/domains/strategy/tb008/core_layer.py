"""
TradingBrain

TB008 - Core Layer

Builds the near-expiry short strangle: estimate the expected weekly range,
select ~target-delta far-OTM strikes and sell them. This is the income leg the
hedging layer then calendars.
"""

from __future__ import annotations

import math

from app.domains.market.option_chain import OptionChain
from app.domains.shared.enums import OptionRight
from app.domains.strategy.tb008.configuration import TB008Configuration
from app.domains.strategy.tb008.exceptions import StructureConstructionError
from app.domains.strategy.tb008.models import CalendarLeg
from app.domains.strategy.tb008.selection import select_by_delta


class CoreLayer:
    def __init__(self, config: TB008Configuration) -> None:
        self.config = config

    def expected_weekly_range(self, spot: float, implied_vol: float) -> float:
        """
        Expected 1-sigma weekly move. Derived from IV when available (the
        TradingBrain enhancement over the transcript's manual estimate), else
        the configured range percentage.
        """
        if self.config.derive_from_data and implied_vol > 0:
            return spot * implied_vol * math.sqrt(7.0 / 365.0)
        return spot * self.config.weekly_range_pct

    def build_short_strangle(
        self, near_chain: OptionChain, lot_size: int
    ) -> list[CalendarLeg]:
        """Sell ~target-delta call and put on the near expiry."""
        call = select_by_delta(
            near_chain, OptionRight.CALL, self.config.target_sell_delta
        )
        put = select_by_delta(
            near_chain, OptionRight.PUT, self.config.target_sell_delta
        )
        if call is None or put is None:
            raise StructureConstructionError(
                "Near chain lacks priced strikes to sell at the target delta."
            )
        lots = self.config.sell_lots
        return [
            CalendarLeg(
                right=OptionRight.CALL,
                strike=call.strike,
                side="SELL",
                expiry_bucket="near",
                lots=lots,
                price=call.price,
                delta=call.greeks.delta,
            ),
            CalendarLeg(
                right=OptionRight.PUT,
                strike=put.strike,
                side="SELL",
                expiry_bucket="near",
                lots=lots,
                price=put.price,
                delta=put.greeks.delta,
            ),
        ]
