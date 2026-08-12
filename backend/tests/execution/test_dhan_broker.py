"""Tests for the Dhan scrip-master resolver and live DhanBroker (dry-run)."""

from __future__ import annotations

from datetime import date

from app.domains.execution.adapters.dhan_adapter import DhanBroker
from app.domains.execution.adapters.scrip_master import ScripMaster
from app.domains.execution.broker import Order
from app.domains.shared.enums import OptionRight

HEADER = (
    "EXCH_ID,SEGMENT,SECURITY_ID,INSTRUMENT,UNDERLYING_SYMBOL,SYMBOL_NAME,"
    "LOT_SIZE,SM_EXPIRY_DATE,STRIKE_PRICE,OPTION_TYPE"
)


def _write_master(path) -> None:
    rows = [
        HEADER,
        "NSE,D,44900,OPTIDX,NIFTY,NIFTY 02 JUL 25000 CALL,75,2026-07-02,25000.00000,CE",
        "NSE,D,44901,OPTIDX,NIFTY,NIFTY 02 JUL 25000 PUT,75,2026-07-02,25000.00000,PE",
        "NSE,D,44902,OPTIDX,NIFTY,NIFTY 02 JUL 25200 CALL,75,2026-07-02,25200.00000,CE",
        "BSE,D,99001,OPTIDX,SENSEX,SENSEX 25 JUN 66000 CALL,20,2026-06-25,66000.00000,CE",
    ]
    path.write_text("\n".join(rows), encoding="utf-8")


def test_scrip_master_resolves_option(tmp_path):
    p = tmp_path / "scrip.csv"
    _write_master(p)
    master = ScripMaster(str(p))

    info = master.resolve(
        underlying="NIFTY",
        expiry=date(2026, 7, 2),
        strike=25000.0,
        right=OptionRight.CALL,
    )
    assert info is not None
    assert info.security_id == 44900
    assert info.exchange_segment == "NSE_FNO"
    assert info.lot_size == 75


def test_scrip_master_segment_for_bse(tmp_path):
    p = tmp_path / "scrip.csv"
    _write_master(p)
    master = ScripMaster(str(p))
    info = master.resolve(
        underlying="SENSEX",
        expiry=date(2026, 6, 25),
        strike=66000.0,
        right=OptionRight.CALL,
    )
    assert info is not None and info.exchange_segment == "BSE_FNO"


def test_scrip_master_missing_returns_none(tmp_path):
    p = tmp_path / "scrip.csv"
    _write_master(p)
    master = ScripMaster(str(p))
    assert (
        master.resolve(
            underlying="NIFTY",
            expiry=date(2026, 7, 2),
            strike=99999.0,
            right=OptionRight.PUT,
        )
        is None
    )


def test_dhan_broker_dry_run_resolves_without_placing(tmp_path):
    from datetime import datetime

    from app.domains.execution.feed import MarketSnapshot
    from app.domains.market.candle import Candle
    from app.domains.market.option_chain import OptionChain
    from app.domains.market.symbol import NIFTY

    p = tmp_path / "scrip.csv"
    _write_master(p)
    broker = DhanBroker(
        client_id="cid",
        access_token="tok",
        scrip_master=ScripMaster(str(p)),
        dry_run=True,
    )

    ts = datetime(2026, 6, 30, 9, 20)
    snapshot = MarketSnapshot(
        timestamp=ts,
        spec=NIFTY,
        candle=Candle(timestamp=ts, open=25000, high=25000, low=25000, close=25000),
        implied_vol=0.12,
        expiry=date(2026, 7, 2),
        time_to_expiry=2 / 365,
        option_chain=OptionChain(
            symbol="NIFTY", underlying=25000, expiry=date(2026, 7, 2), timestamp=ts
        ),
    )
    order = Order(
        symbol="NIFTY",
        instrument="NIFTY25000CE",
        quantity=-75,
        right=OptionRight.CALL,
        strike=25000.0,
    )
    fill = broker.submit(order, snapshot)
    assert fill is not None
    assert fill.metadata["security_id"] == 44900
    assert fill.metadata["order_id"] is None  # dry-run: no order placed
    assert fill.price > 0  # BS fallback priced the leg


def _snapshot(tmp_path):
    from datetime import datetime

    from app.domains.execution.feed import MarketSnapshot
    from app.domains.market.candle import Candle
    from app.domains.market.option_chain import OptionChain
    from app.domains.market.symbol import NIFTY

    ts = datetime(2026, 6, 30, 9, 20)
    return MarketSnapshot(
        timestamp=ts,
        spec=NIFTY,
        candle=Candle(timestamp=ts, open=25000, high=25000, low=25000, close=25000),
        implied_vol=0.12,
        expiry=date(2026, 7, 2),
        time_to_expiry=2 / 365,
        option_chain=OptionChain(
            symbol="NIFTY", underlying=25000, expiry=date(2026, 7, 2), timestamp=ts
        ),
    )


def test_basket_is_placed_hedge_first(tmp_path):
    p = tmp_path / "scrip.csv"
    _write_master(p)
    broker = DhanBroker(
        client_id="c", access_token="t", scrip_master=ScripMaster(str(p)), dry_run=True
    )
    snapshot = _snapshot(tmp_path)

    # Pass writes first; the basket must reorder hedges (BUY) ahead of writes.
    orders = [
        Order(
            symbol="NIFTY",
            instrument="N25000CE",
            quantity=-75,
            right=OptionRight.CALL,
            strike=25000,
        ),  # write
        Order(
            symbol="NIFTY",
            instrument="N25200CE",
            quantity=75,
            right=OptionRight.CALL,
            strike=25200,
        ),  # hedge
    ]
    fills = broker.submit_basket(orders, snapshot)
    assert len(fills) == 2
    assert fills[0].order.is_buy  # hedge filled first
    assert not fills[1].order.is_buy


def test_basket_aborts_when_a_leg_is_unresolvable(tmp_path):
    p = tmp_path / "scrip.csv"
    _write_master(p)
    broker = DhanBroker(
        client_id="c", access_token="t", scrip_master=ScripMaster(str(p)), dry_run=True
    )
    snapshot = _snapshot(tmp_path)

    orders = [
        Order(
            symbol="NIFTY",
            instrument="N25000CE",
            quantity=75,
            right=OptionRight.CALL,
            strike=25000,
        ),
        # Strike 30000 isn't in the scrip master -> whole basket aborts.
        Order(
            symbol="NIFTY",
            instrument="N30000CE",
            quantity=-75,
            right=OptionRight.CALL,
            strike=30000,
        ),
    ]
    assert broker.submit_basket(orders, snapshot) == []


def test_dhan_broker_reconciles_actual_fill(tmp_path):
    p = tmp_path / "scrip.csv"
    _write_master(p)
    broker = DhanBroker(
        client_id="c", access_token="t", scrip_master=ScripMaster(str(p)),
        dry_run=False, fill_timeout_seconds=0.01, fill_poll_seconds=0.001,
    )
    broker._client = _FakeDhanClient()
    fill = broker.submit(
        Order(
            symbol="NIFTY", instrument="NIFTY25000CE", quantity=-75,
            right=OptionRight.CALL, strike=25000,
        ),
        _snapshot(tmp_path),
    )
    assert fill is not None
    assert fill.quantity == -75
    assert fill.price == 101.25
    assert fill.metadata["reconciled"] is True


class _FakeDhanClient:
    def place_order(self, **kwargs):
        return {"status": "success", "data": {"orderId": "order-1"}}

    def get_order_by_id(self, order_id):
        return {
            "status": "success",
            "data": {
                "orderId": order_id,
                "orderStatus": "TRADED",
                "filledQty": 75,
                "averageTradedPrice": 101.25,
            },
        }
