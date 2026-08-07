"""
TradingBrain
Analytics - Reports

Turns a :class:`TradeJournal` into a human-readable performance report and a
machine-readable summary dict (handy for API responses and persistence).

Author: TradingBrain
"""

from __future__ import annotations

from typing import Any

from app.domains.analytics.journal import TradeJournal
from app.domains.analytics.performance import compute_performance
from app.domains.analytics.statistics import compute_statistics


def build_summary(
    journal: TradeJournal, *, periods_per_year: float = 252.0
) -> dict[str, Any]:
    """Compute a structured summary from a journal."""
    stats = compute_statistics(journal.pnls())
    perf = compute_performance(
        journal.equity_values(), periods_per_year=periods_per_year
    )
    total_costs = sum(t.commission for t in journal.trades)
    return {
        "trades": {
            "total": stats.total_trades,
            "wins": stats.wins,
            "losses": stats.losses,
            "win_rate": stats.win_rate,
            "profit_factor": stats.profit_factor,
            "expectancy": stats.expectancy,
            "average_win": stats.average_win,
            "average_loss": stats.average_loss,
            "largest_win": stats.largest_win,
            "largest_loss": stats.largest_loss,
            "net_profit": stats.net_profit,
            "total_costs": total_costs,
            "gross_profit_pre_cost": stats.net_profit + total_costs,
        },
        "equity": {
            "starting": perf.starting_equity,
            "ending": perf.ending_equity,
            "net_return": perf.net_return,
            "return_pct": perf.return_pct,
            "max_drawdown": perf.max_drawdown,
            "max_drawdown_pct": perf.max_drawdown_pct,
            "sharpe": perf.sharpe,
            "samples": perf.samples,
        },
    }


def render_report(
    journal: TradeJournal,
    *,
    title: str = "TradingBrain Backtest Report",
    periods_per_year: float = 252.0,
) -> str:
    """Render a fixed-width text performance report."""
    summary = build_summary(journal, periods_per_year=periods_per_year)
    t = summary["trades"]
    e = summary["equity"]

    pf = t["profit_factor"]
    pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"

    lines = [
        "=" * 56,
        title.center(56),
        "=" * 56,
        "Trades",
        "-" * 56,
        f"  Total trades        : {t['total']}",
        f"  Wins / Losses       : {t['wins']} / {t['losses']}",
        f"  Win rate            : {t['win_rate']:.1%}",
        f"  Profit factor       : {pf_str}",
        f"  Expectancy / trade  : Rs {t['expectancy']:,.2f}",
        f"  Average win         : Rs {t['average_win']:,.2f}",
        f"  Average loss        : Rs {t['average_loss']:,.2f}",
        f"  Largest win         : Rs {t['largest_win']:,.2f}",
        f"  Largest loss        : Rs {t['largest_loss']:,.2f}",
        "",
        "Costs (brokerage + STT + exchange + GST + stamp)",
        "-" * 56,
        f"  Gross profit (pre-cost) : Rs {t['gross_profit_pre_cost']:,.2f}",
        f"  Total transaction costs : Rs {t['total_costs']:,.2f}",
        f"  Net profit (post-cost)  : Rs {t['net_profit']:,.2f}",
        "",
        "Equity",
        "-" * 56,
        f"  Starting equity     : Rs {e['starting']:,.2f}",
        f"  Ending equity       : Rs {e['ending']:,.2f}",
        f"  Net return          : Rs {e['net_return']:,.2f} "
        f"({e['return_pct']:.2%})",
        f"  Max drawdown        : Rs {e['max_drawdown']:,.2f} "
        f"({e['max_drawdown_pct']:.2%})",
        f"  Sharpe (annualized) : {e['sharpe']:.2f}",
        "=" * 56,
    ]
    return "\n".join(lines)
