"""
TradingBrain
Application - Live ICT (Dhan candles -> TB002 setups)

Wires Dhan's intraday candle API to the ICT detector so TB002 gets real NIFTY
multi-timeframe structure during forward testing (MT5 has no NSE data). Pulls
H1 (HTF) and 5m (LTF, resampled to 15m) candles, throttled to respect Dhan's
rate limits, and exposes ``enrich(context)`` to inject the detected setup into
``metadata["tb002_setup"]``.

Author: TradingBrain
"""

from __future__ import annotations

import logging
import time

from app.domains.execution.adapters.dhan_adapter import DhanCandleFeed
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.tb002.detector import ICTDetector
from app.domains.strategy.tb002.setup_provider import ICTSetupProvider, resample

logger = logging.getLogger("tradingbrain.ict")


class DhanLiveICT:
    """Refreshes Dhan candles and detects TB002 ICT setups for a context."""

    def __init__(
        self,
        *,
        security_id: int = 13,  # NIFTY index
        exchange_segment: str = "IDX_I",
        instrument_type: str = "INDEX",
        client_id: str,
        access_token: str,
        htf_interval: int = 60,  # 1h
        ltf_interval: int = 5,  # 5m
        m15_factor: int = 3,  # 5m -> 15m
        history_days: int = 5,
        refresh_seconds: float = 60.0,
        detector: ICTDetector | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        self._feed = DhanCandleFeed(
            security_id=security_id,
            exchange_segment=exchange_segment,
            instrument_type=instrument_type,
            client_id=client_id,
            access_token=access_token,
        )
        self._htf_interval = htf_interval
        self._ltf_interval = ltf_interval
        self._m15_factor = m15_factor
        self._history_days = history_days
        self._refresh_seconds = refresh_seconds
        self._detector = detector or ICTDetector()
        self._log = log or logger
        self._provider: ICTSetupProvider | None = None
        self._ltf: list = []
        self._last_refresh = 0.0

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-pull candles from Dhan and rebuild the setup provider."""
        htf = self._feed.fetch_intraday(
            interval=self._htf_interval, days=self._history_days
        )
        ltf = self._feed.fetch_intraday(
            interval=self._ltf_interval, days=self._history_days
        )
        m15 = resample(ltf, self._m15_factor)
        self._provider = ICTSetupProvider(
            htf=htf, m15=m15, ltf=ltf, detector=self._detector, ltf_timeframe="5m"
        )
        self._ltf = ltf
        self._last_refresh = time.monotonic()
        self._log.info(
            "ICT candles refreshed (HTF=%d, 15m=%d, LTF=%d)",
            len(htf),
            len(m15),
            len(ltf),
        )

    def enrich(self, context: MarketContext) -> MarketContext:
        """Inject ``metadata['tb002_setup']`` when a setup is detected."""
        if (
            self._provider is None
            or (time.monotonic() - self._last_refresh) >= self._refresh_seconds
        ):
            try:
                self.refresh()
            except Exception as exc:  # pragma: no cover - network/SDK errors
                self._log.warning("ICT candle refresh failed: %s", exc)
                return context
        if self._provider is not None:
            self._provider.enrich(context)
        if self._ltf:
            # Full-day 5m history for bar-window strategies (TB009's opening
            # range) - a live run started mid-session can't otherwise see
            # candles from before it began polling.
            context.metadata["day_candles_5m"] = self._ltf
        return context
