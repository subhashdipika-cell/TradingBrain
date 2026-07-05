"""
TradingBrain

TB008 - Strike Selection Helpers

Delta-based strike selection over an option chain. The source method places
legs by delta (~2-delta to sell, ~15/30-delta hedges), so selection is by the
option's delta rather than a fixed strike distance.
"""

from __future__ import annotations

from app.domains.market.option_chain import OptionChain, OptionQuote
from app.domains.shared.enums import OptionRight


def select_by_delta(
    chain: OptionChain, right: OptionRight, target_delta: float
) -> OptionQuote | None:
    """
    Return the quote for ``right`` whose |delta| is closest to ``target_delta``.

    Robust to real chains that do not quote a strike at exactly the target
    delta - it snaps to the nearest available. Returns ``None`` if no priced
    strike for that right exists.
    """
    best: OptionQuote | None = None
    best_gap = float("inf")
    for (strike, quote_right), quote in chain.quotes.items():
        if quote_right is not right:
            continue
        if quote.price <= 0:
            continue
        gap = abs(abs(quote.greeks.delta) - abs(target_delta))
        if gap < best_gap:
            best_gap = gap
            best = quote
        _ = strike  # (unused; iteration key)
    return best
