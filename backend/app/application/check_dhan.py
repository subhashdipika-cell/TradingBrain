"""
TradingBrain
Application - Dhan Connectivity Preflight

A 10-second sanity check before forward testing: verifies the token, resolves
the nearest expiry, pulls one option-chain snapshot, and pulls one batch of
intraday candles - printing clear PASS/FAIL for each.

    python -m app.application.check_dhan --symbol NIFTY

Requires ``pip install dhanhq`` and a valid token (settings or AlphaEdge
``dhan_config.json``). Option-chain checks need market hours; candle checks
work any time within the available history.

Author: TradingBrain
"""

from __future__ import annotations

import argparse

from app.application.forward_test import _UNDERLYING, _load_credentials
from app.domains.market.symbol import get_instrument

OK = "[ OK ]"
FAIL = "[FAIL]"


def _check(symbol: str) -> bool:
    key = symbol.upper()
    if key not in _UNDERLYING:
        print(f"{FAIL} No Dhan underlying id mapped for '{symbol}'.")
        return False
    security_id, segment = _UNDERLYING[key]
    spec = get_instrument("NIFTY" if key in ("NIFTY", "NIFTY50") else key)

    print(
        f"TradingBrain - Dhan preflight for {symbol} "
        f"(security_id={security_id}, segment={segment})"
    )
    print("-" * 60)

    # 0) Credentials + client
    try:
        client_id, access_token = _load_credentials()
        masked = (access_token[:4] + "..." + access_token[-4:]) if access_token else ""
        print(f"{OK} Credentials loaded (client_id={client_id}, token={masked})")
    except Exception as exc:
        print(f"{FAIL} Credentials: {exc}")
        return False

    passed = True

    # 1) Option-chain feed: expiry + one snapshot
    try:
        from app.domains.execution.adapters.dhan_adapter import DhanFeed

        feed = DhanFeed(
            spec=spec,
            security_id=security_id,
            segment=segment,
            client_id=client_id,
            access_token=access_token,
            max_polls=1,
        )
        expiry = feed.nearest_expiry()
        if expiry:
            print(f"{OK} Expiry list resolved -> nearest expiry {expiry}")
        else:
            print(f"{FAIL} Could not resolve an expiry (market closed or token?)")
            passed = False

        snapshot = next(iter(feed.stream()), None)
        if snapshot is not None and snapshot.option_chain.strikes():
            chain = snapshot.option_chain
            atm = chain.nearest_strike(snapshot.spot)
            print(
                f"{OK} Option chain: spot {snapshot.spot:.1f}, "
                f"{len(chain.strikes())} strikes, ATM {atm}, IV {snapshot.implied_vol:.2%}"
            )
        else:
            print(f"{FAIL} Empty option chain (market likely closed).")
            passed = False
    except Exception as exc:
        print(f"{FAIL} Option chain: {exc}")
        passed = False

    # 2) Intraday candles (for TB002 ICT)
    try:
        from app.domains.execution.adapters.dhan_adapter import DhanCandleFeed

        cfeed = DhanCandleFeed(
            security_id=security_id,
            exchange_segment=segment,
            instrument_type="INDEX",
            client_id=client_id,
            access_token=access_token,
        )
        candles = cfeed.fetch_intraday(interval=5, days=3)
        if candles:
            last = candles[-1]
            print(
                f"{OK} Intraday 5m candles: {len(candles)} bars, "
                f"last {last.timestamp} close {last.close:.1f}"
            )
        else:
            print(f"{FAIL} No candles returned (check segment/instrument/token).")
            passed = False
    except Exception as exc:
        print(f"{FAIL} Intraday candles: {exc}")
        passed = False

    print("-" * 60)
    print(
        "RESULT:",
        (
            "ALL CHECKS PASSED - ready to forward test."
            if passed
            else "Some checks failed - see above."
        ),
    )
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Dhan connectivity preflight.")
    parser.add_argument("--symbol", default="NIFTY")
    args = parser.parse_args()
    ok = _check(args.symbol)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
