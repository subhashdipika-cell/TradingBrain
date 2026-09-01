"""
TradingBrain
Application - Forward Test Runner

Turnkey forward testing: connects to Dhan with your API token, polls the LIVE
option chain during market hours, and runs the regime-selected strategies with
SIMULATED fills (paper). Real data, no capital at risk. Results are saved to
the results store so they show up on the dashboard's analysis page.

Usage (tomorrow, during market hours):

    python -m app.application.forward_test --symbol NIFTY

Credentials are read from settings (DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN) or, if
unset, from the AlphaEdge ``dhan_config.json`` (DHAN_CONFIG_PATH). Requires
``pip install dhanhq``.

Author: TradingBrain
"""

from __future__ import annotations

import argparse
import json
import logging
import os

from app.application.live import LivePaperTrader
from app.application.results_store import ResultsStore
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("tradingbrain.forward")

# Dhan underlying security ids for the index option chains (segment IDX_I).
# Verify/extend via AlphaEdge's dhan_lookup.py if these change.
_UNDERLYING = {
    "NIFTY": (13, "IDX_I"),
    "NIFTY50": (13, "IDX_I"),
    "BANKNIFTY": (25, "IDX_I"),
    "FINNIFTY": (27, "IDX_I"),
}


def _load_credentials() -> tuple[str, str]:
    """Return (client_id, access_token) from settings or AlphaEdge config."""
    client_id = settings.DHAN_CLIENT_ID
    access_token = settings.DHAN_ACCESS_TOKEN
    if client_id and access_token:
        return client_id, access_token

    path = settings.DHAN_CONFIG_PATH
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        return str(cfg.get("client_id", "")), str(cfg.get("access_token", ""))

    raise RuntimeError(
        "No Dhan credentials. Set DHAN_CLIENT_ID/DHAN_ACCESS_TOKEN in .env or "
        "provide a dhan_config.json at DHAN_CONFIG_PATH."
    )


def run_forward_test(
    *,
    symbol: str = "NIFTY",
    starting_capital: float = 1_000_000.0,
    strategy: str = "AUTO",
    max_polls: int | None = None,
) -> str | None:
    """Run a live paper (forward) test and persist the result. Returns run id.

    ``strategy="AUTO"`` uses the structure-aware regime selector; a specific name
    (TB001..TB006) forward-tests that single strategy."""
    key = symbol.upper()
    if key not in _UNDERLYING:
        raise ValueError(f"No Dhan underlying id mapped for symbol '{symbol}'.")

    # Daily first-run holiday verification (Dhan holiday calendar, cached per
    # IST day) — don't start a live paper session on a closed market.
    from app.domains.market.holidays import trading_day_check
    ok_day, why = trading_day_check()
    if not ok_day:
        raise RuntimeError(f"Forward test refused: {why}")

    security_id, segment = _UNDERLYING[key]
    client_id, access_token = _load_credentials()

    # strategy="BRAIN": the Daily Brain confirms the regime from the last 2-3
    # days of behaviour and picks today's strategy from its learned memory
    # (see intelligence/daily_brain.py). It may refuse to trade (STAND_ASIDE).
    brain_mode = (strategy or "").upper() == "BRAIN"
    today_gap_pct = None
    if brain_mode:
        from app.domains.intelligence import daily_brain
        p = daily_brain.plan()
        if p["strategy"] == "STAND_ASIDE":
            raise RuntimeError(
                f"Brain says STAND ASIDE today ({p['regime']}): {p['reason']}")
        strategy = p["strategy"]
        today_gap_pct = p["lookback"].get("today_gap_pct")
        log.info("Brain plan %s: regime=%s -> strategy=%s (%s)",
                 p["date"], p["regime"], strategy, p["reason"])
        if today_gap_pct is not None:
            log.info("Today's open gap: %+.2f%%", today_gap_pct)

    auto = (strategy or "AUTO").upper() == "AUTO"
    strat_obj = None
    if not auto:
        from app.domains.strategy.contracts.registry import StrategyRegistry
        from app.domains.strategy.selector import register_all_strategies
        register_all_strategies()
        strat_obj = StrategyRegistry.get(strategy)()

    trader = LivePaperTrader.from_dhan(
        security_id=security_id,
        segment=segment,
        client_id=client_id,
        access_token=access_token,
        symbol="NIFTY" if key in ("NIFTY", "NIFTY50") else key,
        starting_capital=starting_capital,
        use_selector=auto,
        strategy=strat_obj,
        max_polls=max_polls,
        today_gap_pct=today_gap_pct,
        log=log,
    )

    journal = trader.run()

    store = ResultsStore(settings.RESULTS_DIR)
    from app.domains.analytics.reports import render_report

    label = "AUTO (regime)" if auto else strategy
    report = render_report(journal, title=f"Forward test [{label}] - {symbol}")
    summary = store.save(
        run_type="forward-test",
        symbol=symbol,
        journal=journal,
        report=report,
        params={"starting_capital": starting_capital, "strategy": strategy},
    )
    log.info(
        "Saved forward-test result %s (net Rs %.0f)", summary.id, summary.net_return
    )

    # Feed the realized day result back into the Daily Brain's regime memory —
    # this is how the brain LEARNS which strategy pays in which regime. Every
    # forward-test outcome counts as evidence, not only brain-chosen runs.
    try:
        from app.domains.intelligence import daily_brain
        strat_used = "AUTO(regime)" if auto else str(strategy)
        if not auto:
            upd = daily_brain.record_outcome(
                strat_used, summary.net_return / starting_capital * 100.0)
            log.info("Brain memory updated: %s", upd)
    except Exception as exc:  # noqa: BLE001 — learning must not break the run
        log.warning("Brain outcome recording failed: %s", exc)

    return summary.id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Dhan forward (paper) test.")
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument(
        "--max-polls",
        type=int,
        default=None,
        help="Stop after N polls (default: run until interrupted).",
    )
    parser.add_argument(
        "--strategy",
        default="AUTO",
        help="AUTO (regime-based) or a specific strategy: TB001..TB006.",
    )
    args = parser.parse_args()
    run_forward_test(
        symbol=args.symbol,
        starting_capital=args.capital,
        strategy=args.strategy,
        max_polls=args.max_polls,
    )


if __name__ == "__main__":
    main()
