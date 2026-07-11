"""
TradingBrain - 09:15 open-gate A/B harness

Tests whether any strategy tolerates entries in the 09:15-10:15 open window
that the platform blocks (engine.ENTRY_OPEN_CUTOFF = 10:15). Arm A runs the
current gate; Arm B lifts it to 09:15 and restores each strategy's earliest
entry config. Same data, same costs, same risk. The gate is patched at
RUNTIME only - no engine code changes.

Filed hypothesis (2026-07-11, 14 NIFTY50 sessions): TB005 Bull Put was the
ONLY strategy the open flipped positive (-1,561/PF 0.67 -> +1,605/PF 1.39;
early trades +2,400 on 15). Plausible mechanism: selling put spreads at the
bell captures peak open IV + full-day theta. Counterpoint: 15 trades is a
hypothesis, not evidence, and at 09:15 the trend gate cannot compute yet.
TB004/TB006/TB007 and the AUTO composite all confirmed the 10:15 gate
(AUTO +265 -> -1,667 with the gate lifted). TB001's early trades were
mildly positive (+2,572) - the historical "90% of losses at the open" came
from the pre-fix TB001.

RE-RUN THIS when the Dhan sample reaches ~40 NIFTY50 sessions (the weekly
TB007 tracker banner announces when it is due). If TB005-at-open still
holds, implement a per-strategy ``open_entry_allowed`` override rather than
lifting the platform gate.

Usage:
    cd backend && .venv/Scripts/python.exe -m scripts.open_gate_ab
"""

from __future__ import annotations

import sys
import warnings
from collections import Counter
from dataclasses import replace
from datetime import time as dtime

import app.application.engine as eng_mod
from app.application.engine import EngineConfig, TradingEngine
from app.domains.execution.costs import IndianOptionsCostModel
from app.domains.execution.historical_feed import OptionChainHistoricalFeed
from app.domains.execution.paper_broker import PaperBroker
from app.domains.market.symbol import get_instrument
from app.domains.portfolio.portfolio import Portfolio
from app.domains.risk.limits import RiskLimits
from app.domains.risk.position_sizing import PositionSizer
from app.domains.risk.risk_engine import RiskEngine
from app.domains.strategy.credit_sellers import (
    BearCallSpreadStrategy,
    BullPutSpreadStrategy,
    IronCondorStrategy,
)
from app.domains.strategy.range_breakout import RangeBreakoutCreditStrategy
from app.domains.strategy.selector import default_selector
from app.domains.strategy.tb001 import TB001Strategy
from app.domains.strategy.tb007 import TB007Strategy

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATA = r"D:/alphaedge/strategy-lab/data/options"
CAP = 400_000.0
GATE_A = dtime(10, 15)
GATE_B = dtime(9, 15)

spec = get_instrument("NIFTY50")


def run(actor, gate):
    eng_mod.ENTRY_OPEN_CUTOFF = gate
    feed = OptionChainHistoricalFeed.from_dhan_dir(DATA, spec=spec, prefix="NIFTY50")
    kw = dict(
        feed=feed,
        broker=PaperBroker(cost_model=IndianOptionsCostModel(), tick_size=spec.tick_size),
        portfolio=Portfolio(starting_capital=CAP),
        risk_engine=RiskEngine(RiskLimits(max_daily_loss=0.04, max_drawdown=0.10)),
        sizer=PositionSizer(),
        config=EngineConfig(bar_minutes=1),
    )
    if hasattr(actor, "generate_signal"):
        engine = TradingEngine(strategy=actor, **kw)
    else:
        engine = TradingEngine(strategy=None, selector=actor, **kw)
    return list(engine.run().trades)


def stats(trades):
    n = len(trades)
    if n == 0:
        return "  0 tr"
    wins = [t for t in trades if t.pnl > 0]
    gp = sum(t.pnl for t in wins)
    gl = -sum(t.pnl for t in trades if t.pnl <= 0)
    net = sum(t.pnl for t in trades)
    early = [t for t in trades if t.entry_time.time() < GATE_A]
    pf = gp / gl if gl else float("inf")
    exits = dict(Counter(t.exit_reason for t in trades))
    return (
        f"{n:3} tr  WR {100 * len(wins) / n:3.0f}%  net {net:>8,.0f}  PF {pf:5.2f}"
        f"  | early(<10:15): {len(early)} tr net {sum(t.pnl for t in early):>8,.0f}"
        f"  {exits}"
    )


def ab(label, make_a, make_b):
    print(f"== {label} ==", flush=True)
    print(f"  A gate 10:15: {stats(run(make_a(), GATE_A))}", flush=True)
    print(f"  B gate 09:15: {stats(run(make_b(), GATE_B))}", flush=True)


def tb001_early():
    s = TB001Strategy()
    s.configuration.entry_time = "09:15:00"
    return s


def condor_early():
    s = IronCondorStrategy()
    s.configuration = replace(s.configuration, entry_after_min=0)
    return s


def bullput_early():
    s = BullPutSpreadStrategy()
    s.configuration = replace(s.configuration, entry_after_min=0)
    return s


def bearcall_early():
    s = BearCallSpreadStrategy()
    s.configuration = replace(s.configuration, entry_after_min=0)
    return s


def tb007_early():
    s = TB007Strategy()
    s.configuration.entry_time = "09:15:00"
    return s


def main() -> None:
    n_sessions = len(
        __import__("glob").glob(f"{DATA}/NIFTY50_OPT_*.csv")
    )
    print(f"Open-gate A/B on {n_sessions} NIFTY50 sessions\n", flush=True)
    ab("TB001 Iron Fly", TB001Strategy, tb001_early)
    ab("TB004 Iron Condor", IronCondorStrategy, condor_early)
    ab("TB005 Bull Put  <- the filed hypothesis", BullPutSpreadStrategy, bullput_early)
    ab("TB006 Bear Call", BearCallSpreadStrategy, bearcall_early)
    ab("TB007 Convexity Buy", TB007Strategy, tb007_early)
    ab("TB009 Range Breakout (control)", RangeBreakoutCreditStrategy, RangeBreakoutCreditStrategy)
    ab("AUTO composite", default_selector, default_selector)
    eng_mod.ENTRY_OPEN_CUTOFF = GATE_A  # restore


if __name__ == "__main__":
    main()
