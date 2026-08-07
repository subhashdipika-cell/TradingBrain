"""
TradingBrain
Portfolio - Holdings

A collection of open positions keyed by instrument. Provides aggregate
PnL and clean separation between open and closed legs.

Author: TradingBrain
"""

from __future__ import annotations

from collections.abc import Iterator

from app.domains.portfolio.position import Position


class Holdings:
    """Container for the portfolio's positions, keyed by instrument."""

    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    def get(self, instrument: str) -> Position | None:
        return self._positions.get(instrument)

    def get_or_create(
        self,
        *,
        symbol: str,
        instrument: str,
        multiplier: int,
        **kwargs: object,
    ) -> Position:
        position = self._positions.get(instrument)
        if position is None:
            position = Position(
                symbol=symbol,
                instrument=instrument,
                quantity=0,
                avg_price=0.0,
                multiplier=multiplier,
                **kwargs,  # type: ignore[arg-type]
            )
            self._positions[instrument] = position
        return position

    def open_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.is_open]

    def all_positions(self) -> list[Position]:
        return list(self._positions.values())

    def __iter__(self) -> Iterator[Position]:
        return iter(self._positions.values())

    def __len__(self) -> int:
        return len(self._positions)

    @property
    def has_open_positions(self) -> bool:
        return any(p.is_open for p in self._positions.values())

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------
    def realized_pnl(self) -> float:
        return sum(p.realized_pnl for p in self._positions.values())

    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl() for p in self._positions.values())

    def total_pnl(self) -> float:
        return self.realized_pnl() + self.unrealized_pnl()

    def remove_closed(self) -> None:
        """Drop fully-closed positions (keeps their realized PnL booked)."""
        self._positions = {k: v for k, v in self._positions.items() if v.is_open}
