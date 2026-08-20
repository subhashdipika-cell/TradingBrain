"""Cost-aware before/after replay for the AUTO volatility-edge gate."""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.application.backtest import BacktestConfig, run_backtest
from app.domains.analytics.reports import build_summary


@dataclass(frozen=True, slots=True)
class ReplayScenario:
    name: str
    config: BacktestConfig


DEFAULT_SCENARIOS = (
    ReplayScenario(
        "cheap-volatility",
        BacktestConfig(
            num_days=20,
            bar_minutes=15,
            annual_vol=0.18,
            base_iv=0.12,
            seed=17,
            include_costs=True,
        ),
    ),
    ReplayScenario(
        "rich-high-volatility",
        BacktestConfig(
            num_days=20,
            bar_minutes=15,
            annual_vol=0.10,
            base_iv=0.22,
            seed=29,
            include_costs=True,
        ),
    ),
)


def _metrics(config: BacktestConfig, *, gated: bool) -> dict[str, float | int]:
    result = run_backtest(replace(config, enforce_volatility_edge=gated))
    trades = build_summary(result.journal)["trades"]
    return {
        "trade_count": int(trades["total"]),
        "expectancy": float(trades["expectancy"]),
        "net_profit": float(trades["net_profit"]),
        "total_costs": float(trades["total_costs"]),
    }


def compare_volatility_edge(
    scenarios: tuple[ReplayScenario, ...] = DEFAULT_SCENARIOS,
) -> list[dict[str, object]]:
    """Replay identical seeded paths with the legacy and gated selectors."""
    rows: list[dict[str, object]] = []
    for scenario in scenarios:
        baseline = _metrics(scenario.config, gated=False)
        gated = _metrics(scenario.config, gated=True)
        rows.append(
            {
                "scenario": scenario.name,
                "baseline": baseline,
                "gated": gated,
                "trade_count_impact": gated["trade_count"] - baseline["trade_count"],
                "expectancy_impact": gated["expectancy"] - baseline["expectancy"],
            }
        )
    return rows


def render_comparison(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Scenario | Selector | Trades | Expectancy/trade | Net P&L | Costs |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        for label, key in (("Prior AUTO", "baseline"), ("Vol-edge AUTO", "gated")):
            metrics = row[key]
            lines.append(
                f"| {row['scenario']} | {label} | {metrics['trade_count']} | "
                f"Rs {metrics['expectancy']:,.2f} | Rs {metrics['net_profit']:,.2f} | "
                f"Rs {metrics['total_costs']:,.2f} |"
            )
        lines.append(
            f"| {row['scenario']} | Impact | {row['trade_count_impact']:+d} | "
            f"Rs {row['expectancy_impact']:+,.2f} | - | - |"
        )
    return "\n".join(lines)


def main() -> None:
    print(render_comparison(compare_volatility_edge()))


if __name__ == "__main__":
    main()
