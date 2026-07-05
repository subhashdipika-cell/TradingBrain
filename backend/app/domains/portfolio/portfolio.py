"""
TradingBrain
Portfolio - Aggregate

The Portfolio is the single source of truth for what the account holds and
what it is worth. It applies fills, marks positions to the current option
chain, books realized PnL into capital, and exposes equity / drawdown / net
Greeks to the risk engine and analytics.

Author: TradingBrain
"""

from __future__ import annotations

from datetime import datetime

from app.domains.market.option_chain import OptionChain
from app.domains.portfolio.capital import Capital
from app.domains.portfolio.exposure import GreeksExposure, aggregate_exposure
from app.domains.portfolio.holdings import Holdings
from app.domains.portfolio.position import Position
from app.domains.shared.enums import OptionRight


class Portfolio:
    """Account aggregate: capital + holdings + valuation."""

    def __init__(self, starting_capital: float) -> None:
        self.capital = Capital(starting_capital=starting_capital)
        self.holdings = Holdings()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def apply_fill(
        self,
        *,
        symbol: str,
        instrument: str,
        quantity: int,
        price: float,
        multiplier: int = 1,
        right: OptionRight | None = None,
        strike: float | None = None,
        timestamp: datetime | None = None,
    ) -> float:
        """
        Apply a signed fill (+ buy, - sell) and book any realized PnL.

        Returns the realized PnL delta produced by this fill.
        """
        position = self.holdings.get_or_create(
            symbol=symbol,
            instrument=instrument,
            multiplier=multiplier,
            right=right,
            strike=strike,
        )
        if position.opened_at is None and timestamp is not None:
            position.opened_at = timestamp

        realized_before = position.realized_pnl
        position.apply_fill(quantity, price)
        position.mark(price)
        realized_delta = position.realized_pnl - realized_before

        if realized_delta != 0.0:
            self.capital.book_realized(realized_delta)

        return realized_delta

    def mark_to_chain(self, chain: OptionChain) -> None:
        """Mark every open option position to the current chain price."""
        for position in self.holdings.open_positions():
            if position.strike is None or position.right is None:
                continue
            quote = chain.get(position.strike, position.right)
            if quote is not None:
                position.mark(quote.price)
        self.capital.update_high_water_mark(self.unrealized_pnl())

    def mark_instrument(self, instrument: str, price: float) -> None:
        position = self.holdings.get(instrument)
        if position is not None:
            position.mark(price)

    # ------------------------------------------------------------------
    # Valuation
    # ------------------------------------------------------------------
    def realized_pnl(self) -> float:
        return self.capital.realized_pnl

    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl() for p in self.holdings.open_positions())

    def total_pnl(self) -> float:
        return self.realized_pnl() + self.unrealized_pnl()

    def equity(self) -> float:
        return self.capital.equity(self.unrealized_pnl())

    def drawdown_fraction(self) -> float:
        return self.capital.drawdown_fraction(self.unrealized_pnl())

    def net_greeks(self, chain: OptionChain) -> GreeksExposure:
        return aggregate_exposure(self.holdings.open_positions(), chain)

    @property
    def has_open_positions(self) -> bool:
        return self.holdings.has_open_positions

    def open_positions(self) -> list[Position]:
        return self.holdings.open_positions()
