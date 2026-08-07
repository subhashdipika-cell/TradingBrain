"""
TradingBrain
Execution - Dhan Adapter (live)

Live NSE option-chain feed via the official ``dhanhq`` SDK, mirroring the
proven AlphaEdge ``dhan_options_collector`` so the data shape matches exactly:
``dhan.option_chain(security_id, segment, expiry)`` returns the underlying LTP
and an ``oc`` map of strike -> {ce, pe} legs carrying last_price, IV (percent),
OI, volume and greeks (delta/theta/vega).

``DhanFeed`` is implemented and ready: pair it with ``PaperBroker`` for **live
paper trading** (real data, simulated fills) using only your API token. It
lazily imports ``dhanhq`` so this module loads without the dependency.

``DhanBroker`` (real-money order placement) is intentionally left as a guarded
stub: it needs a scrip-master lookup to resolve an option's security id and
carries real execution risk, so wire and test it deliberately.

Requires: ``pip install dhanhq`` + a Dhan ``client_id`` and ``access_token``.
"""

from __future__ import annotations

import time as _time
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

from app.domains.execution.broker import Broker, Fill, Order
from app.domains.execution.feed import DataFeed, MarketSnapshot
from app.domains.market.candle import Candle
from app.domains.market.expiry import time_to_expiry_years
from app.domains.market.greeks import OptionGreeks, black_scholes
from app.domains.market.option_chain import OptionChain, OptionQuote
from app.domains.market.symbol import InstrumentSpec
from app.domains.shared.enums import OptionRight

_IST = timezone(timedelta(hours=5, minutes=30))


def _unwrap(resp: object) -> dict:
    """Peel the dhanhq {status, remarks, data} + API {status, data} wrappers."""
    if not isinstance(resp, dict):
        return {}
    if resp.get("status") == "failure":
        return {"_error": resp.get("remarks")}
    data = resp.get("data", resp)
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    return data if isinstance(data, dict) else {}


class DhanFeed(DataFeed):
    """Live option-chain feed via Dhan (polls ``option_chain``)."""

    def __init__(
        self,
        *,
        spec: InstrumentSpec,
        security_id: int,
        segment: str,
        client_id: str,
        access_token: str,
        expiry: str | None = None,
        atm_range: int = 5,
        poll_seconds: float = 3.5,  # Dhan option-chain limit ~1 req / 3s
        rate: float = 0.065,
        max_polls: int | None = None,
    ) -> None:
        self._spec = spec
        self._security_id = security_id
        self._segment = segment
        self._client_id = client_id
        self._access_token = access_token
        self._expiry = expiry
        self._atm_range = atm_range
        self._poll_seconds = poll_seconds
        self._rate = rate
        self._max_polls = max_polls
        self._client = None

    @property
    def spec(self) -> InstrumentSpec:
        return self._spec

    # ------------------------------------------------------------------
    def _ensure_client(self):
        if self._client is None:
            try:
                from dhanhq import dhanhq
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "DhanFeed requires the 'dhanhq' package. Run "
                    "`pip install dhanhq`."
                ) from exc
            self._client = dhanhq(self._client_id, self._access_token)
        return self._client

    def nearest_expiry(self) -> str | None:
        client = self._ensure_client()
        data = _unwrap(client.expiry_list(self._security_id, self._segment))
        expiries = data.get("data") if isinstance(data.get("data"), list) else None
        if not expiries:
            return None
        today = datetime.now(_IST).strftime("%Y-%m-%d")
        future = [e for e in expiries if str(e) >= today]
        return (future or expiries)[0]

    def stream(self) -> Iterator[MarketSnapshot]:
        client = self._ensure_client()
        expiry = self._expiry or self.nearest_expiry()
        if expiry is None:
            raise RuntimeError("DhanFeed: could not resolve an expiry.")

        polls = 0
        while self._max_polls is None or polls < self._max_polls:
            snapshot = self._poll_once(client, expiry)
            if snapshot is not None:
                yield snapshot
            polls += 1
            _time.sleep(self._poll_seconds)

    # ------------------------------------------------------------------
    def _poll_once(self, client, expiry: str) -> MarketSnapshot | None:
        data = _unwrap(client.option_chain(self._security_id, self._segment, expiry))
        if "_error" in data:
            return None
        under_ltp = float(data.get("last_price") or 0.0)
        oc_map = data.get("oc") or {}
        if not under_ltp or not oc_map:
            return None

        now = datetime.now(_IST).replace(tzinfo=None)
        expiry_date = date.fromisoformat(expiry)
        tte = time_to_expiry_years(now, expiry_date)

        chain = OptionChain(
            symbol=self._spec.symbol,
            underlying=under_ltp,
            expiry=expiry_date,
            timestamp=now,
        )
        strikes = sorted(oc_map.keys(), key=lambda s: float(s))
        atm_i = min(
            range(len(strikes)),
            key=lambda i: abs(float(strikes[i]) - under_ltp),
        )
        lo = max(0, atm_i - self._atm_range)
        hi = min(len(strikes), atm_i + self._atm_range + 1)

        ivs: list[float] = []
        for sk in strikes[lo:hi]:
            node = oc_map[sk]
            for typ, right in (("ce", OptionRight.CALL), ("pe", OptionRight.PUT)):
                leg = node.get(typ) or {}
                if not leg:
                    continue
                iv = float(leg.get("implied_volatility", 0) or 0) / 100.0
                ivs.append(iv)
                chain.add(
                    OptionQuote(
                        symbol=self._spec.symbol,
                        expiry=expiry_date,
                        strike=round(float(sk), 2),
                        right=right,
                        greeks=self._greeks(leg, right, float(sk), under_ltp, tte, iv),
                        underlying=under_ltp,
                    )
                )

        candle = Candle(
            timestamp=now,
            open=under_ltp,
            high=under_ltp,
            low=under_ltp,
            close=under_ltp,
        )
        return MarketSnapshot(
            timestamp=now,
            spec=self._spec,
            candle=candle,
            implied_vol=(sum(ivs) / len(ivs)) if ivs else 0.0,
            expiry=expiry_date,
            time_to_expiry=tte,
            option_chain=chain,
        )

    def _greeks(
        self,
        leg: dict,
        right: OptionRight,
        strike: float,
        spot: float,
        tte: float,
        iv: float,
    ) -> OptionGreeks:
        g = leg.get("greeks") or {}
        bs = black_scholes(
            right=right,
            spot=spot,
            strike=strike,
            time_to_expiry=max(tte, 1e-9),
            volatility=max(iv, 1e-4),
            rate=self._rate,
        )
        return OptionGreeks(
            price=float(leg.get("last_price", 0) or 0),
            delta=float(g.get("delta", bs.delta) or bs.delta),
            gamma=bs.gamma,
            theta=float(g.get("theta", bs.theta) or bs.theta),
            vega=float(g.get("vega", bs.vega) or bs.vega),
            rho=bs.rho,
        )


class DhanBroker(Broker):
    """
    Live order execution via Dhan (SCAFFOLD - real money).

    Implementing this safely needs a scrip-master lookup to resolve an option
    leg (symbol/strike/right/expiry) to its Dhan ``security_id`` (see
    AlphaEdge's ``dhan_lookup.py`` / ``dhan_scrip_master.csv``), plus careful
    handling of product type, order type and partial fills. Left guarded on
    purpose - use ``PaperBroker`` with ``DhanFeed`` for live *paper* trading.
    """

    def __init__(self, *, client_id: str, access_token: str) -> None:
        self._client_id = client_id
        self._access_token = access_token

    def submit(self, order: Order, snapshot: MarketSnapshot) -> Fill | None:
        raise NotImplementedError(
            "DhanBroker.submit: resolve the option security_id via a scrip "
            "master and call dhanhq.place_order(...). Use PaperBroker + DhanFeed "
            "for live paper trading until real execution is wired and tested."
        )
