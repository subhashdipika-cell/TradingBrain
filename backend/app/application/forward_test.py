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
    use_selector: bool = True,
    max_polls: int | None = None,
) -> str | None:
    """Run a live paper (forward) test and persist the result. Returns run id."""
    key = symbol.upper()
    if key not in _UNDERLYING:
        raise ValueError(f"No Dhan underlying id mapped for symbol '{symbol}'.")
    security_id, segment = _UNDERLYING[key]
    client_id, access_token = _load_credentials()

    trader = LivePaperTrader.from_dhan(
        security_id=security_id,
        segment=segment,
        client_id=client_id,
        access_token=access_token,
        symbol="NIFTY" if key in ("NIFTY", "NIFTY50") else key,
        starting_capital=starting_capital,
        use_selector=use_selector,
        max_polls=max_polls,
        log=log,
    )

    journal = trader.run()

    store = ResultsStore(settings.RESULTS_DIR)
    from app.domains.analytics.reports import render_report

    report = render_report(journal, title=f"Forward test - {symbol}")
    summary = store.save(
        run_type="forward-test",
        symbol=symbol,
        journal=journal,
        report=report,
        params={"starting_capital": starting_capital, "use_selector": use_selector},
    )
    log.info(
        "Saved forward-test result %s (net Rs %.0f)", summary.id, summary.net_return
    )
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
        "--single-strategy",
        action="store_true",
        help="Use TB001 only instead of regime-based selection.",
    )
    args = parser.parse_args()
    run_forward_test(
        symbol=args.symbol,
        starting_capital=args.capital,
        use_selector=not args.single_strategy,
        max_polls=args.max_polls,
    )


if __name__ == "__main__":
    main()
