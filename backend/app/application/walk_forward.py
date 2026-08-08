"""Chronological walk-forward evaluation for collected option data.

The evaluator never shuffles dates and never lets a later file influence an
earlier fold. TradingBrain currently has fixed rule-based parameters rather
than a fitted model, so the train and validation windows document the
information available before each test window; they are not silently used to
optimize the test results.
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from datetime import date

from app.application.backtest import run_dhan_backtest
from app.domains.analytics.reports import build_summary


_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})\.csv$")


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    train_days: int = 10
    validation_days: int = 5
    test_days: int = 5
    step_days: int = 5

    def __post_init__(self) -> None:
        for name in ("train_days", "validation_days", "test_days", "step_days"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    fold: int
    train_files: tuple[str, ...]
    validation_files: tuple[str, ...]
    test_files: tuple[str, ...]

    @property
    def train_dates(self) -> tuple[date, date]:
        return _date_range(self.train_files)

    @property
    def validation_dates(self) -> tuple[date, date]:
        return _date_range(self.validation_files)

    @property
    def test_dates(self) -> tuple[date, date]:
        return _date_range(self.test_files)


@dataclass(frozen=True, slots=True)
class WalkForwardFoldResult:
    fold: int
    train: dict[str, object]
    validation: dict[str, object]
    test: dict[str, object]


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    symbol: str
    files: int
    folds: tuple[WalkForwardFoldResult, ...]
    report: str


def discover_option_files(directory: str, symbol: str) -> list[str]:
    """Return dated AlphaEdge option files in chronological order."""
    prefix = symbol.upper()
    paths = sorted(glob_pattern(directory, f"{prefix}_OPT_*.csv"), key=_file_date)
    if not paths:
        raise FileNotFoundError(f"No option files found for {prefix} in {directory!r}")
    return paths


def build_walk_forward_windows(
    files: list[str], config: WalkForwardConfig | None = None
) -> tuple[WalkForwardWindow, ...]:
    """Build non-leaking rolling train/validation/test windows."""
    cfg = config or WalkForwardConfig()
    ordered = sorted(files, key=_file_date)
    required = cfg.train_days + cfg.validation_days + cfg.test_days
    windows: list[WalkForwardWindow] = []
    start = 0
    fold = 1
    while start + required <= len(ordered):
        train_end = start + cfg.train_days
        validation_end = train_end + cfg.validation_days
        test_end = validation_end + cfg.test_days
        windows.append(
            WalkForwardWindow(
                fold=fold,
                train_files=tuple(ordered[start:train_end]),
                validation_files=tuple(ordered[train_end:validation_end]),
                test_files=tuple(ordered[validation_end:test_end]),
            )
        )
        start += cfg.step_days
        fold += 1
    return tuple(windows)


def run_walk_forward(
    *,
    directory: str,
    symbol: str = "NIFTY50",
    starting_capital: float = 1_000_000.0,
    config: WalkForwardConfig | None = None,
    include_costs: bool = True,
    bar_minutes: int = 1,
    strategy: str = "AUTO",
) -> WalkForwardResult:
    """Run each chronological test fold using only its test files."""
    files = discover_option_files(directory, symbol)
    windows = build_walk_forward_windows(files, config)
    if not windows:
        raise ValueError(
            f"Need more than {len(files)} files for the configured walk-forward windows"
        )

    fold_results: list[WalkForwardFoldResult] = []
    for window in windows:
        metrics: dict[str, dict[str, object]] = {}
        for name, selected in (
            ("train", window.train_files),
            ("validation", window.validation_files),
            ("test", window.test_files),
        ):
            result = run_dhan_backtest(
                directory=directory,
                files=list(selected),
                symbol=symbol,
                starting_capital=starting_capital,
                include_costs=include_costs,
                bar_minutes=bar_minutes,
                strategy=strategy,
            )
            metrics[name] = _summary(result.journal)
        fold_results.append(
            WalkForwardFoldResult(
                fold=window.fold,
                train=metrics["train"],
                validation=metrics["validation"],
                test=metrics["test"],
            )
        )

    report = render_walk_forward_report(symbol, files, fold_results, config or WalkForwardConfig())
    return WalkForwardResult(symbol, len(files), tuple(fold_results), report)


def render_walk_forward_report(
    symbol: str,
    files: list[str],
    folds: list[WalkForwardFoldResult],
    config: WalkForwardConfig,
) -> str:
    lines = [
        "=" * 78,
        f"TradingBrain Walk-Forward Report - {symbol}".center(78),
        "=" * 78,
        f"Files: {len(files)} | Folds: {len(folds)} | "
        f"Train/Validation/Test: {config.train_days}/{config.validation_days}/{config.test_days}",
        "Policy: fixed current rules; test windows were not used for parameter selection.",
        "",
        "Fold | Segment     | Trades | Win%  | PF   | Expectancy | Net P&L | Max DD",
        "-" * 78,
    ]
    for fold in folds:
        for name, metrics in (("train", fold.train), ("validation", fold.validation), ("test", fold.test)):
            lines.append(
                f"{fold.fold:>4} | {name:<11} | {int(metrics['trades']):>6} | "
                f"{float(metrics['win_rate']):>5.1%} | {float(metrics['profit_factor']):>4.2f} | "
                f"Rs {float(metrics['expectancy']):>9,.0f} | Rs {float(metrics['net_profit']):>7,.0f} | "
                f"{float(metrics['max_drawdown_pct']):>5.2%}"
            )
    test_metrics = [fold.test for fold in folds]
    if test_metrics:
        positive = sum(float(m["net_profit"]) > 0 for m in test_metrics)
        avg_expectancy = sum(float(m["expectancy"]) for m in test_metrics) / len(test_metrics)
        lines.extend(
            [
                "",
                f"Out-of-sample test folds profitable: {positive}/{len(test_metrics)}",
                f"Average test expectancy: Rs {avg_expectancy:,.2f}",
                "Conclusion: treat the strategy as unvalidated unless test folds are consistently profitable with adequate trade counts.",
                "=" * 78,
            ]
        )
    return "\n".join(lines)


def _summary(journal) -> dict[str, object]:
    summary = build_summary(journal)
    return {
        "trades": summary["trades"]["total"],
        "win_rate": summary["trades"]["win_rate"],
        "profit_factor": summary["trades"]["profit_factor"],
        "expectancy": summary["trades"]["expectancy"],
        "net_profit": summary["trades"]["net_profit"],
        "max_drawdown_pct": summary["equity"]["max_drawdown_pct"],
    }


def glob_pattern(directory: str, pattern: str) -> list[str]:
    # Kept as a tiny seam for tests and to avoid importing pathlib throughout
    # the report formatting code.
    from glob import glob

    return glob(os.path.join(directory, pattern))


def _file_date(path: str) -> date:
    match = _DATE_RE.search(os.path.basename(path))
    if match is None:
        raise ValueError(f"Expected YYYY-MM-DD in option filename: {path}")
    return date.fromisoformat(match.group(1))


def _date_range(paths: tuple[str, ...]) -> tuple[date, date]:
    dates = [_file_date(path) for path in paths]
    return min(dates), max(dates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TradingBrain walk-forward evaluation.")
    parser.add_argument("--directory", required=True)
    parser.add_argument("--symbol", default="NIFTY50")
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--train-days", type=int, default=10)
    parser.add_argument("--validation-days", type=int, default=5)
    parser.add_argument("--test-days", type=int, default=5)
    parser.add_argument("--step-days", type=int, default=5)
    args = parser.parse_args()
    result = run_walk_forward(
        directory=args.directory,
        symbol=args.symbol,
        starting_capital=args.capital,
        config=WalkForwardConfig(
            train_days=args.train_days,
            validation_days=args.validation_days,
            test_days=args.test_days,
            step_days=args.step_days,
        ),
    )
    print(result.report)


if __name__ == "__main__":
    main()
