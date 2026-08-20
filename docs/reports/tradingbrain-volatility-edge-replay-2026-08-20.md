# AUTO volatility-edge replay — 2026-08-20

The production AUTO selector was compared with its prior structure-only routing
on identical seeded paths. Both sides used `PaperBroker`, 0.05% simulated
slippage, and the full Indian options cost model (brokerage, STT, exchange,
SEBI, GST, and stamp charges). Results are net of those costs.

| Scenario | Selector | Trades | Expectancy/trade | Net P&L | Costs |
|---|---:|---:|---:|---:|---:|
| cheap-volatility | Prior AUTO | 12 | Rs -457.81 | Rs -5,493.74 | Rs 2,370.49 |
| cheap-volatility | Vol-edge AUTO | 0 | Rs 0.00 | Rs 0.00 | Rs 0.00 |
| cheap-volatility | Impact | -12 | Rs +457.81 | - | - |
| rich-high-volatility | Prior AUTO | 10 | Rs -218.64 | Rs -2,186.38 | Rs 2,004.38 |
| rich-high-volatility | Vol-edge AUTO | 11 | Rs -200.13 | Rs -2,201.44 | Rs 2,230.69 |
| rich-high-volatility | Impact | +1 | Rs +18.51 | - | - |

Across both regimes, trade count fell from 22 to 11 and net expectancy improved
from Rs -349.10 to Rs -200.13 per trade. The cheap-volatility path was rejected
entirely. In the rich high-volatility path, the gate admitted one more trade
because high/extreme IV now routes to the defined-risk Iron Condor instead of
standing aside; expectancy improved, although it remained negative after costs.

This is deterministic synthetic replay, not forward or profitability evidence.
It tests selection behavior and cost drag. The explicit event-risk branch is
covered by unit tests because the synthetic feed contains no point-in-time event
calendar. AUTO remains blocked in `LIVE` execution mode and the Dhan forward
path continues to use simulated `PAPER` fills only.

Reproduce from `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.application.volatility_edge_replay
```
