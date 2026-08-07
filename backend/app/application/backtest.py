"""
TradingBrain
Application - Backtest Runner

Wires the default research stack - synthetic feed + paper broker + portfolio +
risk engine + TB001 - and runs an end-to-end backtest. Run directly to print a
performance report:

    python -m app.application.backtest
    python -m app.application.backtest --days 60 --capital 1500000 --symbol BANKNIFTY

Author: TradingBrain
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date

from app.application.engine import EngineConfig, TradingEngine
from app.domains.analytics.journal import TradeJournal
from app.domains.analytics.reports import render_report
from app.domains.execution.backtest_feed import BacktestFeed
from app.domains.execution.costs import FlatCostModel, IndianOptionsCostModel
from app.domains.execution.historical_feed import OptionChainHistoricalFeed
from app.domains.execution.paper_broker import PaperBroker
from app.domains.market.symbol import get_instrument
from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.limits import RiskLimits
from app.domains.risk.position_sizing import PositionSizer
from app.domains.risk.risk_engine import RiskEngine
from app.domains.strategy.tb001 import TB001Strategy


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    symbol: str = "NIFTY"
    start_date: date = date(2026, 1, 1)
    num_days: int = 30
    bar_minutes: int = 5
    start_spot: float = 25_000.0
    annual_vol: float = 0.13
    base_iv: float = 0.12
    starting_capital: float = 1_000_000.0
    slippage_pct: float = 0.0005
    include_costs: bool = True  # apply realistic NSE F&O transaction costs
    seed: int = 42


@dataclass(frozen=True, slots=True)
class BacktestResult:
    journal: TradeJournal
    report: str


def run_backtest(config: BacktestConfig | None = None) -> BacktestResult:
    """Assemble the research stack and run a full backtest."""
    cfg = config or BacktestConfig()
    spec = get_instrument(cfg.symbol)

    feed = BacktestFeed(
        spec=spec,
        start_date=cfg.start_date,
        num_days=cfg.num_days,
        bar_minutes=cfg.bar_minutes,
        start_spot=cfg.start_spot,
        annual_vol=cfg.annual_vol,
        base_iv=cfg.base_iv,
        seed=cfg.seed,
    )
    cost_model = IndianOptionsCostModel() if cfg.include_costs else FlatCostModel(0.0)
    broker = PaperBroker(
        slippage_pct=cfg.slippage_pct,
        cost_model=cost_model,
        tick_size=spec.tick_size,
    )
    portfolio = Portfolio(starting_capital=cfg.starting_capital)
    strategy = TB001Strategy()
    risk_engine = RiskEngine(
        RiskLimits(
            max_daily_loss=strategy.configuration.max_daily_loss,
            max_drawdown=strategy.configuration.max_strategy_drawdown,
        )
    )
    engine = TradingEngine(
        strategy=strategy,
        feed=feed,
        broker=broker,
        portfolio=portfolio,
        risk_engine=risk_engine,
        sizer=PositionSizer(),
        config=EngineConfig(
            bar_minutes=cfg.bar_minutes,
            capital_allocation=strategy.configuration.capital_allocation,
        ),
    )

    journal = engine.run()
    report = render_report(
        journal, title=f"TB001 Backtest - {cfg.symbol} ({cfg.num_days} sessions)"
    )
    return BacktestResult(journal=journal, report=report)


def run_dhan_backtest(
    *,
    directory: str,
    symbol: str = "NIFTY50",
    starting_capital: float = 1_000_000.0,
    slippage_pct: float = 0.0,
    include_costs: bool = True,
    bar_minutes: int = 1,
) -> BacktestResult:
    """
    Backtest TB001 on REAL Dhan option-chain snapshots accumulated by AlphaEdge
    (``..._OPT_*.csv`` files in ``directory``). Uses real premiums and Dhan
    greeks; PnL is net of real NSE costs.
    """
    spec = get_instrument(symbol)
    prefix = symbol.upper()

    feed = OptionChainHistoricalFeed.from_dhan_dir(directory, spec=spec, prefix=prefix)
    cost_model = IndianOptionsCostModel() if include_costs else FlatCostModel(0.0)
    broker = PaperBroker(
        slippage_pct=slippage_pct, cost_model=cost_model, tick_size=spec.tick_size
    )
    strategy = TB001Strategy()
    engine = TradingEngine(
        strategy=strategy,
        feed=feed,
        broker=broker,
        portfolio=Portfolio(starting_capital=starting_capital),
        risk_engine=RiskEngine(
            RiskLimits(
                max_daily_loss=strategy.configuration.max_daily_loss,
                max_drawdown=strategy.configuration.max_strategy_drawdown,
            )
        ),
        sizer=PositionSizer(),
        config=EngineConfig(
            bar_minutes=bar_minutes,
            capital_allocation=strategy.configuration.capital_allocation,
        ),
    )
    journal = engine.run()
    report = render_report(journal, title=f"TB001 on real Dhan data - {symbol}")
    return BacktestResult(journal=journal, report=report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a TB001 backtest.")
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--bar-minutes", type=int, default=5)
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--spot", type=float, default=25_000.0)
    parser.add_argument("--iv", type=float, default=0.12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--dhan-dir",
        default=None,
        help="Directory of real Dhan option CSVs (e.g. AlphaEdge "
        "strategy-lab/data/options). Runs on real data instead of synthetic.",
    )
    args = parser.parse_args()

    if args.dhan_dir:
        result = run_dhan_backtest(
            directory=args.dhan_dir,
            symbol=args.symbol,
            starting_capital=args.capital,
            bar_minutes=args.bar_minutes,
        )
    else:
        result = run_backtest(
            BacktestConfig(
                symbol=args.symbol,
                num_days=args.days,
                bar_minutes=args.bar_minutes,
                starting_capital=args.capital,
                start_spot=args.spot,
                base_iv=args.iv,
                seed=args.seed,
            )
        )
    print(result.report)


if __name__ == "__main__":
    main()
