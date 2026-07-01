"""
TradingBrain
Strategy - Regime-Based Strategy Selector

Routes the platform to the right strategy for the prevailing market regime.
Theta harvesting (TB001) earns in calm, range-bound markets and bleeds in
strong trends or volatility spikes - so the selector *gates* it by regime.
Directional reversal/breakout conditions can route to TB002, whose own setup
validation decides whether the ICT layers are present.

This is the meta-layer above the strategies: classify the regime, look up the
strategy mapped to it, instantiate it from the :class:`StrategyRegistry`.
As TB002.. are added they simply register and get mapped to their regimes.

Author: TradingBrain
"""

from __future__ import annotations

from app.domains.intelligence.regime_detection import (
    RegimeClassifier,
    RuleBasedRegimeClassifier,
)
from app.domains.shared.enums import MarketRegime
from app.domains.strategy.contracts.context import MarketContext
from app.domains.strategy.contracts.registry import StrategyRegistry
from app.domains.strategy.contracts.strategy import BaseStrategy


class StrategySelector:
    """Selects a strategy for the current market regime."""

    def __init__(
        self,
        *,
        classifier: RegimeClassifier | None = None,
        default_strategy: str | None = None,
    ) -> None:
        self._classifier = classifier or RuleBasedRegimeClassifier()
        self._mapping: dict[MarketRegime, str] = {}
        self._default = default_strategy
        self._instances: dict[str, BaseStrategy] = {}
        # Optional finer-grained router: (context) -> strategy name | None. When
        # set it takes precedence over the coarse regime map so selection can use
        # trend direction + volatility, not just the regime label.
        self._resolver = None
        # Strategies to initialise even if only reachable via the resolver.
        self._roster: set[str] = set()

    def set_resolver(self, resolver) -> "StrategySelector":
        self._resolver = resolver
        return self

    def add_to_roster(self, *names: str) -> "StrategySelector":
        for n in names:
            if not StrategyRegistry.exists(n):
                raise KeyError(f"Strategy '{n}' is not registered.")
            self._roster.add(n)
        return self

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def map_regime(
        self,
        regime: MarketRegime,
        strategy_name: str,
    ) -> "StrategySelector":
        """Map a regime to a registered strategy name (chainable)."""
        if not StrategyRegistry.exists(strategy_name):
            raise KeyError(
                f"Strategy '{strategy_name}' is not registered; register it "
                "before mapping a regime to it."
            )
        self._mapping[regime] = strategy_name
        return self

    def set_default(self, strategy_name: str | None) -> "StrategySelector":
        if strategy_name is not None and not StrategyRegistry.exists(strategy_name):
            raise KeyError(f"Strategy '{strategy_name}' is not registered.")
        self._default = strategy_name
        return self

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------
    def classify(self, context: MarketContext) -> MarketRegime:
        return self._classifier.classify(context)

    def strategy_name_for(self, regime: MarketRegime) -> str | None:
        return self._mapping.get(regime, self._default)

    def select(self, context: MarketContext) -> BaseStrategy | None:
        """
        Classify the regime and return the strategy suited to it, or ``None``
        when no strategy should trade this regime.
        """
        regime = self.classify(context)
        context.market_regime = regime
        if self._resolver is not None:
            name = self._resolver(context)
            return self._instance(name) if name else None
        return self.select_for_regime(regime)

    def select_for_regime(self, regime: MarketRegime) -> BaseStrategy | None:
        name = self.strategy_name_for(regime)
        if name is None:
            return None
        return self._instance(name)

    def active_mapping(self) -> dict[MarketRegime, str]:
        return dict(self._mapping)

    def all_strategies(self) -> list[BaseStrategy]:
        """Instantiate (once) and return every mapped/default strategy."""
        names = set(self._mapping.values()) | set(self._roster)
        if self._default is not None:
            names.add(self._default)
        return [self._instance(name) for name in sorted(names)]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _instance(self, name: str) -> BaseStrategy:
        # Reuse one instance per strategy so lifecycle state persists.
        if name not in self._instances:
            self._instances[name] = StrategyRegistry.get(name)()
        return self._instances[name]


def register_all_strategies() -> None:
    """Register every built-in strategy (idempotent)."""
    from app.domains.strategy.credit_sellers import CREDIT_STRATEGIES
    from app.domains.strategy.tb001 import TB001Strategy
    from app.domains.strategy.tb002 import TB002Strategy

    for cls in (TB001Strategy, TB002Strategy, *CREDIT_STRATEGIES):
        if not StrategyRegistry.exists(cls.name):
            StrategyRegistry.register(cls)


def _structure_router(context: MarketContext) -> str | None:
    """Pick the option-selling strategy that fits the current market structure.

    Structure is read from indicators the engine populates on the context
    (regime, trend direction, volatility). Mapping (confirmed with the user):

      Range + low IV       -> TB001 Iron Fly (max theta, ATM)
      Range + normal/high  -> TB004 Iron Condor (defined risk, wider)
      Uptrend              -> TB005 Bull Put Spread
      Downtrend            -> TB006 Bear Call Spread
      Strong breakout/rev. -> TB002 (ICT directional debit)
      Extreme vol / no edge-> stand aside (None)
    """
    from app.domains.shared.enums import TrendDirection, VolatilityRegime

    regime = context.market_regime
    trend = context.trend
    vol = context.volatility_regime

    if vol == VolatilityRegime.EXTREME:
        return None  # stand aside — tails too fat to sell

    if regime in (MarketRegime.RANGING, MarketRegime.UNKNOWN):
        return "TB001" if vol == VolatilityRegime.LOW else "TB004"

    if regime == MarketRegime.TRENDING:
        if trend == TrendDirection.BULLISH:
            return "TB005"
        if trend == TrendDirection.BEARISH:
            return "TB006"
        return "TB004"

    if regime in (MarketRegime.BREAKOUT, MarketRegime.REVERSAL):
        return "TB002"  # strong directional displacement — ICT buyer

    if regime == MarketRegime.VOLATILE:
        if trend == TrendDirection.BULLISH:
            return "TB005"
        if trend == TrendDirection.BEARISH:
            return "TB006"
        return "TB004"

    return "TB001"


def default_selector() -> StrategySelector:
    """
    Build the structure-aware selector: it classifies the regime from indicators
    and routes to the option-selling strategy that fits (Iron Fly / Iron Condor /
    Bull Put / Bear Call), or TB002 for strong directional breakouts.
    """
    register_all_strategies()

    selector = StrategySelector()
    # Coarse map (used if the resolver ever returns nothing + for lifecycle init).
    selector.map_regime(MarketRegime.RANGING, "TB001")
    selector.map_regime(MarketRegime.UNKNOWN, "TB001")
    selector.map_regime(MarketRegime.VOLATILE, "TB004")
    selector.map_regime(MarketRegime.TRENDING, "TB005")
    selector.map_regime(MarketRegime.BREAKOUT, "TB002")
    selector.map_regime(MarketRegime.REVERSAL, "TB002")
    # Ensure every routable strategy is initialised, then wire the fine router.
    selector.add_to_roster("TB001", "TB002", "TB003", "TB004", "TB005", "TB006")
    selector.set_resolver(_structure_router)
    return selector
