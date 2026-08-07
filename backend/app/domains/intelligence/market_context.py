"""
TradingBrain
Intelligence - Market Context Enricher

Composes the intelligence providers (regime, sentiment, news, predictor) and
writes their outputs back onto a :class:`MarketContext`. This is the single
integration point between the intelligence domain and the strategies: an
engine can run an enricher each bar before handing context to the strategy.

All providers default to no-op/neutral implementations, so enrichment is safe
to enable without any external services or API keys.

Author: TradingBrain
"""

from __future__ import annotations

from app.domains.intelligence.feature_store import FeatureStore
from app.domains.intelligence.news_engine import NewsProvider, NullNewsProvider
from app.domains.intelligence.predictor import MomentumPredictor, Predictor
from app.domains.intelligence.regime_detection import (
    RegimeClassifier,
    RuleBasedRegimeClassifier,
)
from app.domains.intelligence.sentiment import (
    NeutralSentimentProvider,
    SentimentProvider,
)
from app.domains.strategy.contracts.context import MarketContext


class MarketContextEnricher:
    """Augments a MarketContext with intelligence signals."""

    def __init__(
        self,
        *,
        regime: RegimeClassifier | None = None,
        sentiment: SentimentProvider | None = None,
        news: NewsProvider | None = None,
        predictor: Predictor | None = None,
        feature_store: FeatureStore | None = None,
    ) -> None:
        self.regime = regime or RuleBasedRegimeClassifier()
        self.sentiment = sentiment or NeutralSentimentProvider()
        self.news = news or NullNewsProvider()
        self.predictor = predictor or MomentumPredictor()
        self.features = feature_store or FeatureStore()

    def enrich(self, context: MarketContext) -> MarketContext:
        """Populate intelligence fields on ``context`` in place and return it."""
        context.market_regime = self.regime.classify(context)

        context.sentiment_score = self.sentiment.score(context.symbol)

        news_items = self.news.items(context.symbol, context.timestamp)
        if news_items:
            context.news_score = sum(i.impact for i in news_items) / len(news_items)

        prediction = self.predictor.predict(context)
        if prediction.is_actionable:
            context.trend = prediction.direction
            context.confidence = prediction.confidence

        self.features.set_many(
            context.timestamp,
            {
                "implied_volatility": context.implied_volatility,
                "sentiment_score": context.sentiment_score,
                "news_score": context.news_score,
                "confidence": context.confidence,
            },
        )
        return context
