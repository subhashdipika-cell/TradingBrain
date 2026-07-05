"""
TradingBrain

TB008 - Hedging Layer (the heart of the strategy)

Builds the next-expiry RATIO calendar hedge that flattens the payoff and
controls MTM. Instead of a direct 1:1 same-expiry hedge (which would just be an
iron condor), it buys a ratio of long options on the FAR expiry - one closer
protective leg plus further-out legs - creating a double calendar that keeps
profit in the centre and on both sides while smoothing MTM.

VIX-aware: when volatility is so compressed it is likely to expand, the hedges
are pushed a step further out to flatten the curve even more (accepting less
centre profit), per the source method.
"""

from __future__ import annotations

from app.domains.market.option_chain import OptionChain
from app.domains.shared.enums import OptionRight
from app.domains.strategy.tb008.configuration import TB008Configuration
from app.domains.strategy.tb008.exceptions import StructureConstructionError
from app.domains.strategy.tb008.models import CalendarLeg
from app.domains.strategy.tb008.selection import select_by_delta


class HedgingLayer:
    def __init__(self, config: TB008Configuration) -> None:
        self.config = config

    def build_ratio_hedge(
        self,
        far_chain: OptionChain,
        lot_size: int,
        *,
        expansion_risk: bool = False,
    ) -> list[CalendarLeg]:
        """Buy the ratio calendar hedge on the far expiry, both sides."""
        # When vol is compressed, shift every hedge delta lower (further OTM)
        # to flatten the payoff more.
        delta_shift = 0.7 if expansion_risk else 1.0

        legs: list[CalendarLeg] = []
        for right in (OptionRight.CALL, OptionRight.PUT):
            for target_delta, lots in self.config.hedge_legs:
                quote = select_by_delta(far_chain, right, target_delta * delta_shift)
                if quote is None:
                    raise StructureConstructionError(
                        f"Far chain lacks a {right.value} near delta {target_delta}."
                    )
                legs.append(
                    CalendarLeg(
                        right=right,
                        strike=quote.strike,
                        side="BUY",
                        expiry_bucket="far",
                        lots=lots,
                        price=quote.price,
                        delta=quote.greeks.delta,
                    )
                )
        return legs
