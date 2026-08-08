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

from app.domains.execution.adapters.scrip_master import ScripMaster
from app.domains.execution.broker import Broker, Fill, Order
from app.domains.execution.feed import DataFeed, MarketSnapshot
from app.domains.market.candle import Candle
from app.domains.market.expiry import time_to_expiry_years
from app.domains.market.greeks import OptionGreeks, black_scholes
from app.domains.market.option_chain import OptionChain, OptionQuote
from app.domains.market.symbol import InstrumentSpec
from app.domains.shared.enums import OptionRight

_IST = timezone(timedelta(hours=5, minutes=30))


def build_dhan_client(client_id: str, access_token: str):
    """
    Build an authenticated dhanhq client. Matches AlphaEdge's working setup:
    the v2 SDK ``dhanhq(DhanContext(client_id, token))``; falls back to the
    older ``dhanhq(client_id, token)`` signature for compatibility.
    """
    try:
        import dhanhq as _dhanhq_pkg
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Dhan integration requires the 'dhanhq' package. Run "
            "`pip install dhanhq`."
        ) from exc

    context_cls = getattr(_dhanhq_pkg, "DhanContext", None)
    client_cls = getattr(_dhanhq_pkg, "dhanhq")
    if context_cls is not None:
        return client_cls(context_cls(client_id, access_token))
    return client_cls(client_id, access_token)


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
        include_far: bool = False,
        vix_security_id: int = 21,  # Dhan India VIX index (verify via lookup)
        vix_refresh_seconds: float = 60.0,
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
        # Also fetch the NEXT expiry chain (for calendar strategies, TB008).
        # A wider atm_range is used so far-OTM (~2-delta) strikes are present.
        self._include_far = include_far
        # Real India VIX (throttled) so TB008's regime gate is trustworthy.
        self._vix_security_id = vix_security_id
        self._vix_refresh_seconds = vix_refresh_seconds
        self._vix_value = 0.0
        self._vix_fetched_at = 0.0
        self._client = None
        self._bar_minute = None
        self._bar_open = 0.0
        self._bar_high = 0.0
        self._bar_low = 0.0

    @property
    def spec(self) -> InstrumentSpec:
        return self._spec

    # ------------------------------------------------------------------
    def _ensure_client(self):
        if self._client is None:
            self._client = build_dhan_client(self._client_id, self._access_token)
        return self._client

    def expiries(self) -> list[str]:
        """Future expiries (ascending); [0]=near weekly, [1]=next weekly, ..."""
        client = self._ensure_client()
        data = _unwrap(client.expiry_list(self._security_id, self._segment))
        expiries = data.get("data") if isinstance(data.get("data"), list) else None
        if not expiries:
            return []
        today = datetime.now(_IST).strftime("%Y-%m-%d")
        future = sorted(e for e in expiries if str(e) >= today)
        return future or sorted(expiries)

    def nearest_expiry(self) -> str | None:
        found = self.expiries()
        return found[0] if found else None

    def stream(self) -> Iterator[MarketSnapshot]:
        client = self._ensure_client()
        found = self.expiries()
        near = self._expiry or (found[0] if found else None)
        if near is None:
            raise RuntimeError("DhanFeed: could not resolve an expiry.")
        far = found[1] if (self._include_far and len(found) > 1) else None

        polls = 0
        while self._max_polls is None or polls < self._max_polls:
            snapshot = self._poll_once(client, near, far)
            if snapshot is not None:
                yield snapshot
            polls += 1
            _time.sleep(self._poll_seconds)

    # ------------------------------------------------------------------
    def _build_chain(self, client, expiry: str):
        """Return (OptionChain, avg_iv, tte, expiry_date, under_ltp) or None."""
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
            range(len(strikes)), key=lambda i: abs(float(strikes[i]) - under_ltp)
        )
        lo = max(0, atm_i - self._atm_range)
        hi = min(len(strikes), atm_i + self._atm_range + 1)

        # Only average IV across strikes NEAR the money (skew inflates far-OTM
        # IV, which would bias the ATM-IV / VIX-proxy high).
        atm_ivs: list[float] = []
        for i in range(lo, hi):
            sk = strikes[i]
            node = oc_map[sk]
            for typ, right in (("ce", OptionRight.CALL), ("pe", OptionRight.PUT)):
                leg = node.get(typ) or {}
                if not leg:
                    continue
                iv = float(leg.get("implied_volatility", 0) or 0) / 100.0
                if abs(i - atm_i) <= 2:
                    atm_ivs.append(iv)
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
        atm_iv = (sum(atm_ivs) / len(atm_ivs)) if atm_ivs else 0.0
        return chain, atm_iv, tte, expiry_date, under_ltp

    def _get_vix(self, client) -> float:
        """Throttled India VIX read (last 1-min close). 0.0 on failure."""
        now = _time.monotonic()
        if self._vix_value and (now - self._vix_fetched_at) < self._vix_refresh_seconds:
            return self._vix_value
        try:
            ist = datetime.now(_IST)
            resp = client.intraday_minute_data(
                security_id=str(self._vix_security_id),
                exchange_segment="IDX_I",
                instrument_type="INDEX",
                from_date=(ist - timedelta(days=3)).strftime("%Y-%m-%d"),
                to_date=ist.strftime("%Y-%m-%d"),
                interval=1,
            )
            candles = candles_from_response(resp)
            if candles:
                self._vix_value = candles[-1].close
                self._vix_fetched_at = now
        except Exception:  # pragma: no cover - network/SDK errors
            pass
        return self._vix_value

    def _poll_once(
        self, client, near: str, far: str | None = None
    ) -> MarketSnapshot | None:
        built = self._build_chain(client, near)
        if built is None:
            return None
        chain, atm_iv, tte, expiry_date, under_ltp = built

        far_chain = far_expiry = None
        far_tte = 0.0
        if far is not None:
            far_built = self._build_chain(client, far)
            if far_built is not None:
                far_chain, _, far_tte, far_expiry, _ = far_built

        now = datetime.now(_IST).replace(tzinfo=None)
        bar_minute = now.replace(second=0, microsecond=0)
        if self._bar_minute != bar_minute:
            self._bar_minute = bar_minute
            self._bar_open = under_ltp
            self._bar_high = under_ltp
            self._bar_low = under_ltp
        else:
            self._bar_high = max(self._bar_high, under_ltp)
            self._bar_low = min(self._bar_low, under_ltp)
        candle = Candle(
            timestamp=bar_minute,
            open=self._bar_open,
            high=self._bar_high,
            low=self._bar_low,
            close=under_ltp,
        )
        return MarketSnapshot(
            timestamp=now,
            spec=self._spec,
            candle=candle,
            implied_vol=atm_iv,
            expiry=expiry_date,
            time_to_expiry=tte,
            option_chain=chain,
            far_chain=far_chain,
            far_expiry=far_expiry,
            far_time_to_expiry=far_tte,
            vix=self._get_vix(client),
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
    Live order execution via Dhan (REAL MONEY - use with care).

    Resolves each leg's ``security_id`` via a :class:`ScripMaster`, then places
    a Dhan order. The engine submits BUY (hedge) legs before SELL (write) legs,
    so Dhan recognizes the hedge and blocks only the reduced spread margin (the
    "hedge-first" rule). For atomic margin benefit you can additionally route a
    single basket order - see ``place_basket`` notes below.

    Caveats for production:
    - Market orders return an order id immediately; the *actual* fill price
      must be reconciled from the trade book / order-update postback. This
      adapter returns a Fill priced at the snapshot reference as a best effort
      and stamps the order id in ``Fill.metadata`` - reconcile before relying
      on PnL.
    - ``dry_run=True`` (default) resolves + logs but does NOT place orders.
      Set ``dry_run=False`` to trade live.
    """

    def __init__(
        self,
        *,
        client_id: str,
        access_token: str,
        scrip_master: ScripMaster,
        product_type: str = "MARGIN",
        order_type: str = "MARKET",
        dry_run: bool = True,
    ) -> None:
        self._client_id = client_id
        self._access_token = access_token
        self._scrip = scrip_master
        self._product_type = product_type
        self._order_type = order_type
        self._dry_run = dry_run
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            self._client = build_dhan_client(self._client_id, self._access_token)
        return self._client

    def submit(self, order: Order, snapshot: MarketSnapshot) -> Fill | None:
        if order.strike is None or order.right is None:
            return None

        info = self._scrip.resolve(
            underlying=snapshot.symbol,
            expiry=snapshot.expiry,
            strike=order.strike,
            right=order.right,
        )
        if info is None:
            # Cannot resolve the contract -> do not place an unbalanced trade.
            return None

        txn = "BUY" if order.is_buy else "SELL"
        ref_price = snapshot.option_price(order.right, order.strike)

        order_id = None
        if not self._dry_run:
            client = self._ensure_client()
            resp = client.place_order(
                security_id=str(info.security_id),
                exchange_segment=info.exchange_segment,
                transaction_type=txn,
                quantity=abs(order.quantity),
                order_type=self._order_type,
                product_type=self._product_type,
                price=0,
            )
            data = _unwrap(resp)
            if "_error" in data:
                return None
            order_id = data.get("orderId") or data.get("order_id")

        return Fill(
            order=order,
            quantity=order.quantity,
            price=ref_price,  # best-effort; reconcile via trade book
            timestamp=snapshot.timestamp,
            commission=0.0,
            metadata={
                "security_id": info.security_id,
                "exchange_segment": info.exchange_segment,
                "order_id": order_id,
                "dry_run": self._dry_run,
            },
        )

    def submit_basket(
        self, orders: list[Order], snapshot: MarketSnapshot
    ) -> list[Fill]:
        """
        Place a multi-leg basket HEDGE-FIRST: all BUY (protective) legs before
        any SELL (write) legs, so Dhan recognizes the hedge and blocks only the
        reduced combined (spread) margin - the rule that turns a ~Rs 1.5L naked
        requirement into ~Rs 30-40k.

        Resolves every leg up front and aborts the whole basket if any leg is
        unresolvable, so a hedged structure is never sent half-built (which
        would momentarily demand full naked margin).
        """
        # Resolve all legs first; abort atomically on any failure.
        for order in orders:
            if order.strike is None or order.right is None:
                return []
            if (
                self._scrip.resolve(
                    underlying=snapshot.symbol,
                    expiry=snapshot.expiry,
                    strike=order.strike,
                    right=order.right,
                )
                is None
            ):
                return []

        # TODO: optionally call Dhan's margin calculator here to preview the
        # combined spread margin before placing.
        hedge_first = sorted(orders, key=lambda o: 0 if o.is_buy else 1)
        fills: list[Fill] = []
        for order in hedge_first:
            fill = self.submit(order, snapshot)
            if fill is not None:
                fills.append(fill)
        return fills


def candles_from_response(resp: object) -> list[Candle]:
    """
    Convert a Dhan charts response (intraday/historical) into Candles. The SDK
    returns parallel OHLCV arrays under ``data`` with epoch-second (UTC)
    timestamps; we shift them to IST to align with the option feed.
    """
    data = _unwrap(resp)
    if "_error" in data:
        return []
    opens = data.get("open") or []
    highs = data.get("high") or []
    lows = data.get("low") or []
    closes = data.get("close") or []
    vols = data.get("volume") or []
    times = data.get("timestamp") or []
    n = min(len(opens), len(highs), len(lows), len(closes), len(times))
    candles: list[Candle] = []
    for i in range(n):
        ts = (
            datetime.fromtimestamp(int(times[i]), tz=timezone.utc)
            .astimezone(_IST)
            .replace(tzinfo=None)
        )
        candles.append(
            Candle(
                timestamp=ts,
                open=float(opens[i]),
                high=float(highs[i]),
                low=float(lows[i]),
                close=float(closes[i]),
                volume=float(vols[i]) if i < len(vols) else 0.0,
            )
        )
    return candles


class DhanCandleFeed:
    """
    Fetches intraday OHLC candles for an instrument from Dhan's Data API
    (``intraday_minute_data``), mirroring AlphaEdge's ``dhan_collector``. Used
    to feed TB002's ICT detector with real NIFTY candles (MT5 has no NSE data).

    For the index spot use security_id=13, exchange_segment="IDX_I",
    instrument_type="INDEX"; for the tradable future use the FUTIDX contract id
    with exchange_segment="NSE_FNO", instrument_type="FUTIDX".
    """

    def __init__(
        self,
        *,
        security_id: int,
        exchange_segment: str,
        instrument_type: str,
        client_id: str,
        access_token: str,
    ) -> None:
        self._security_id = security_id
        self._segment = exchange_segment
        self._instrument = instrument_type
        self._client_id = client_id
        self._access_token = access_token
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            self._client = build_dhan_client(self._client_id, self._access_token)
        return self._client

    def fetch_intraday(self, *, interval: int, days: int = 5) -> list[Candle]:
        """Fetch completed ``interval``-minute candles for the last ``days`` days."""
        client = self._ensure_client()
        now = datetime.now(_IST)
        resp = client.intraday_minute_data(
            security_id=str(self._security_id),
            exchange_segment=self._segment,
            instrument_type=self._instrument,
            from_date=(now - timedelta(days=days)).strftime("%Y-%m-%d"),
            to_date=now.strftime("%Y-%m-%d"),
            interval=interval,
        )
        candles = candles_from_response(resp)
        cutoff = now.replace(second=0, microsecond=0)
        return [
            candle
            for candle in candles
            if candle.timestamp + timedelta(minutes=interval) <= cutoff
        ]
