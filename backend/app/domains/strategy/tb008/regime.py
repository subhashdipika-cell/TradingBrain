"""
TradingBrain

TB008 - Volatility Regime Classifier

Classifies the India-VIX regime and decides whether it is safe to deploy the
calendar structure. TB008 only activates in LOW volatility; it also flags
"expansion risk" (vol so compressed it is likely to expand), which the source
method uses to flatten the payoff further.
"""

from __future__ import annotations

from app.domains.strategy.tb008.configuration import TB008Configuration
from app.domains.strategy.tb008.models import VixAssessment, VixLevel, VixTrend


class VixRegimeClassifier:
    """Assesses the volatility regime from VIX (and an optional prior read)."""

    def __init__(self, config: TB008Configuration) -> None:
        self.config = config

    def assess(self, vix: float, prior_vix: float | None = None) -> VixAssessment:
        level = self._level(vix)
        trend = self._trend(vix, prior_vix)
        favorable = level is VixLevel.LOW and trend is not VixTrend.EXPANDING
        return VixAssessment(
            vix=vix,
            level=level,
            trend=trend,
            favorable=favorable,
            expansion_risk=vix <= self.config.vix_expansion_risk,
        )

    def _level(self, vix: float) -> VixLevel:
        if vix <= self.config.vix_low_max:
            return VixLevel.LOW
        if vix <= self.config.vix_medium_max:
            return VixLevel.MEDIUM
        return VixLevel.HIGH

    @staticmethod
    def _trend(vix: float, prior_vix: float | None) -> VixTrend:
        if prior_vix is None or prior_vix <= 0:
            return VixTrend.STABLE
        change = (vix - prior_vix) / prior_vix
        if change >= 0.10:
            return VixTrend.EXPANDING
        if change <= -0.10:
            return VixTrend.CONTRACTING
        return VixTrend.STABLE
