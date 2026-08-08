"""Regression tests for credit-seller entry throttling."""

from __future__ import annotations

from datetime import date

from app.domains.strategy.credit_sellers import IronCondorStrategy


def test_credit_seller_reset_does_not_enable_same_day_reentry() -> None:
    strategy = IronCondorStrategy()
    strategy._last_entry_date = date(2026, 8, 10)
    strategy.reset()
    assert strategy._last_entry_date == date(2026, 8, 10)


def test_credit_seller_post_market_opens_next_session() -> None:
    strategy = IronCondorStrategy()
    strategy._last_entry_date = date(2026, 8, 10)
    strategy.post_market(None)  # type: ignore[arg-type]
    assert strategy._last_entry_date is None
