from inspect import signature

from app.api.forward_test import ForwardTestRequest
from app.application.backtest import BacktestConfig, run_dhan_backtest
from app.application.forward_test import run_forward_test
from app.application.live import LivePaperTrader
from app.core.config import Settings
from app.domains.risk.limits import RiskLimits
from app.domains.strategy.credit_sellers import CreditSellConfig
from app.domains.strategy.tb001 import constants as tb001
from app.domains.strategy.tb002 import constants as tb002
from app.domains.strategy.tb007 import constants as tb007
from app.schemas.backtest import BacktestRequest


def test_default_trading_capital_is_ten_lakh() -> None:
    expected = 1_000_000.0

    assert Settings.model_fields["AUTO_FT_CAPITAL"].default == expected
    assert BacktestConfig().starting_capital == expected
    assert BacktestRequest().starting_capital == expected
    assert ForwardTestRequest().starting_capital == expected
    assert signature(LivePaperTrader.build).parameters["starting_capital"].default == expected
    assert signature(LivePaperTrader.from_dhan).parameters["starting_capital"].default == expected
    assert signature(run_forward_test).parameters["starting_capital"].default == expected
    assert signature(run_dhan_backtest).parameters["starting_capital"].default == expected


def test_default_risk_is_ten_percent_daily_and_two_percent_per_trade() -> None:
    limits = RiskLimits()

    assert limits.max_daily_loss == 0.10
    assert limits.max_position_risk == 0.02
    assert tb001.MAX_DAILY_LOSS == 0.10
    assert tb001.DEFAULT_REQUESTED_RISK == 0.02
    assert tb002.MAX_DAILY_LOSS == 0.10
    assert tb002.DEFAULT_REQUESTED_RISK == 0.02
    assert tb002.HIGH_VOL_REQUESTED_RISK == 0.02
    assert tb007.MAX_DAILY_LOSS == 0.10
    assert tb007.DEFAULT_REQUESTED_RISK == 0.02
    assert CreditSellConfig().max_daily_loss == 0.10
    assert CreditSellConfig().capital_allocation == 0.02
