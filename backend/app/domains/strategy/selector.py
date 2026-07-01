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
        names = set(self._mapping.values())
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


def default_selector() -> StrategySelector:
    """
    Build the default selector wiring strategies to the regimes where their
    models are designed to operate.
    """
    from app.domains.strategy.tb001 import TB001Strategy
    from app.domains.strategy.tb002 import TB002Strategy

    if not StrategyRegistry.exists(TB001Strategy.name):
        StrategyRegistry.register(TB001Strategy)
    if not StrategyRegistry.exists(TB002Strategy.name):
        StrategyRegistry.register(TB002Strategy)

    selector = StrategySelector()
    # TB001 (theta harvesting / Iron Fly): sell premium when the market is
    # calm and range-bound - decay works, gamma risk is low.
    selector.map_regime(MarketRegime.RANGING, TB001Strategy.name)
    selector.map_regime(MarketRegime.UNKNOWN, TB001Strategy.name)
    # TB002 (ICT liquidity-sweep inversion): a *directional, high-volatility*
    # model. Per the source playbook, it is activated when volatility is
    # "kicked up" and the market is making displacement moves - reversals,
    # breakouts, strong trends and volatility spikes. It still only fires when
    # the upstream ICT setup (sweep + inversion + pullback + trigger) is
    # present in context.metadata["tb002_setup"].
    selector.map_regime(MarketRegime.REVERSAL, TB002Strategy.name)
    selector.map_regime(MarketRegime.BREAKOUT, TB002Strategy.name)
    selector.map_regime(MarketRegime.TRENDING, TB002Strategy.name)
    selector.map_regime(MarketRegime.VOLATILE, TB002Strategy.name)
    return selector
