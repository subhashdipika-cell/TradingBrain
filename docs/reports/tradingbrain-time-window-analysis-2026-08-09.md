# TradingBrain Entry-Time Analysis — 2026-08-09

The current cost-adjusted strategy was replayed against the AlphaEdge Dhan
snapshots in `D:\alphaedge\strategy-lab\data\options`. Results below use
completed trades and 30-minute entry buckets.

## Results

| Instrument | Entry window | Trades | Net P&L | Win rate | Assessment |
|---|---|---:|---:|---:|---|
| NIFTY50 | 09:30–10:00 | 2 | -₹6,117.80 | 0% | No profitable window observed |
| BANKNIFTY | 10:00–10:30 | 1 | -₹2,995.81 | 0% | Negative, one trade |
| BANKNIFTY | 14:00–14:30 | 1 | ₹1,499.46 | 100% | Best observed, but one trade only |
| FINNIFTY | 11:00–11:30 | 1 | ₹275.47 | 100% | Best observed, but one trade only |

## Conclusion

There is not enough completed-trade history to establish a reliable profitable
time window. Nifty50 has no profitable bucket in this sample. BankNifty's
14:00–14:30 result and FinNifty's 11:00–11:30 result are single-trade
observations and must not be used as live entry filters yet.

The current one-entry-per-session rule means the replay contains only five
completed trades in total. A time-window filter should be promoted only after
each candidate window has materially more trades across multiple market
regimes and remains positive after costs in walk-forward test folds.
