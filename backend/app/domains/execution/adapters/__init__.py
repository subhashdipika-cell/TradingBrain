"""
TradingBrain
Execution - Live Adapters

Live data-feed and broker adapters. These implement the same
:class:`~app.domains.execution.feed.DataFeed` /
:class:`~app.domains.execution.broker.Broker` interfaces as the paper/backtest
components, so wiring one in is a one-line swap in the engine.

They are intentionally scaffolded: each requires real credentials and a
running broker/terminal connection, which cannot be exercised in CI. The
connection logic is marked with ``NotImplementedError`` and a clear TODO so
the integration seam stays honest until it is built and tested live.
"""
