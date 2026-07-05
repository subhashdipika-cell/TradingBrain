"""
TradingBrain
Execution - Transaction Cost Model

Realistic Indian NSE F&O (options) transaction costs, applied per order so a
backtest reflects the *net* picture after all charges. For an intraday short
straddle these costs are material: one round trip is 4 orders (sell call, sell
put, buy call, buy put), each carrying brokerage + statutory charges.

Charge structure (per executed options order), as configured by ``CostRates``:

- Brokerage           : flat per order (discount-broker model), capped by a %.
- STT                 : 0.10% of premium, SELL side only (options).
- Exchange txn charges: ~0.03503% of premium, both sides (NSE).
- SEBI charges        : 0.0001% of premium (Rs 10 / crore), both sides.
- Stamp duty          : 0.003% of premium, BUY side only.
- GST                 : 18% of (brokerage + exchange + SEBI).

NOTE: statutory rates are revised periodically by SEBI/exchanges (e.g. STT on
options sell rose to 0.10% on 2024-10-01). Defaults below reflect that era and
are fully configurable - verify against your broker's contract note.

Author: TradingBrain
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CostRates:
    """Configurable charge rates (fractions of premium turnover)."""

    brokerage_per_order: float = 20.0
    # Options brokerage is a FLAT per-order fee at discount brokers (the
    # "0.03% or Rs 20 whichever lower" rule applies to equity/futures, not
    # options). Set a positive cap to enable the min() rule for futures.
    brokerage_pct_cap: float = 0.0
    stt_sell_pct: float = 0.0010  # 0.10% on sell premium (options)
    exchange_txn_pct: float = 0.0003503  # NSE options, both sides
    sebi_pct: float = 0.000001  # Rs 10 / crore, both sides
    stamp_buy_pct: float = 0.00003  # 0.003% on buy premium
    gst_pct: float = 0.18  # on brokerage + exchange + sebi


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """Itemized charges for one order."""

    brokerage: float = 0.0
    stt: float = 0.0
    exchange: float = 0.0
    sebi: float = 0.0
    stamp: float = 0.0
    gst: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.brokerage
            + self.stt
            + self.exchange
            + self.sebi
            + self.stamp
            + self.gst
        )


class CostModel(ABC):
    """Computes transaction charges for an executed order."""

    @abstractmethod
    def charge(self, *, price: float, units: int, is_buy: bool) -> CostBreakdown:
        """Charges for filling ``units`` of an option at ``price`` (premium)."""
        raise NotImplementedError


class FlatCostModel(CostModel):
    """A simple flat brokerage-per-order model (no statutory charges)."""

    def __init__(self, per_order: float = 20.0) -> None:
        self._per_order = per_order

    def charge(self, *, price: float, units: int, is_buy: bool) -> CostBreakdown:
        if units <= 0 or price <= 0:
            return CostBreakdown()
        return CostBreakdown(brokerage=self._per_order)


class IndianOptionsCostModel(CostModel):
    """Full NSE options charge stack (brokerage + statutory + GST)."""

    def __init__(self, rates: CostRates | None = None) -> None:
        self.rates = rates or CostRates()

    def charge(self, *, price: float, units: int, is_buy: bool) -> CostBreakdown:
        if units <= 0 or price <= 0:
            return CostBreakdown()

        r = self.rates
        turnover = price * units

        # Flat brokerage for options; opt into the % cap only if configured.
        if r.brokerage_pct_cap > 0:
            brokerage = min(r.brokerage_per_order, r.brokerage_pct_cap * turnover)
        else:
            brokerage = r.brokerage_per_order
        stt = 0.0 if is_buy else r.stt_sell_pct * turnover
        exchange = r.exchange_txn_pct * turnover
        sebi = r.sebi_pct * turnover
        stamp = r.stamp_buy_pct * turnover if is_buy else 0.0
        gst = r.gst_pct * (brokerage + exchange + sebi)

        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            exchange=exchange,
            sebi=sebi,
            stamp=stamp,
            gst=gst,
        )
