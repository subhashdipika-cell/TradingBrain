# TB007 Weekly Backtest — Scheduler

A Windows Task Scheduler job reruns the Convexity Buy (TB007) strategy across
**all** accumulated Dhan option-chain snapshots every week and appends a dated
read to the Trading_Mind wiki, so the sample grows and there is a standing
answer to "is the edge real yet?".

## What runs

`TB007_WeeklyBacktest.bat` (repo root) → `backend/scripts/tb007_backtest_report.py`

For each index (NIFTY50, BANKNIFTY, SENSEX) it runs three configs, net of all
NSE charges, on ₹10L capital:

| Config | Structure |
|--------|-----------|
| `directional` | long CALL/PUT on the squeeze-break (2% risk) |
| `straddle` | delta-neutral ATM straddle, intraday (3% risk) |
| `straddle-hold2` | straddle held up to 2 sessions overnight (3% risk) |

## Outputs

- `E:/Obsidian/Trading_Mind/wiki/strategies/tb007-backtest-tracker.md` — human read (trend table, newest first, + per-run detail). Same-day re-runs are idempotent (replace, not duplicate).
- `E:/Obsidian/Trading_Mind/data/tb007_backtest_history.csv` — machine-readable trend log for charting.
- `backend/scripts/logs/tb007_report.log` — run log.

## Data-freshness guard

Each run compares the newest option-chain session to the run date and to the
previous run's session count, and stamps a **Data status** banner at the top of
the tracker page (and a `Freshness:` line per run):

- ✅ **FRESH** — newest session ≤ 1 trading day old and new sessions arrived.
- ⚠️ **WATCH** — newest session 2–3 trading days old (a holiday or one-off miss).
- 🛑 **STALE** — newest session ≥ 4 trading days old, **or no new sessions since
  the last run**. This is the "collector stopped" alarm: it stops a dead Dhan
  collector from masquerading as "no new signal". A STALE run also prints
  `*** WARNING: STALE ***` to the log and records `freshness=STALE` in the CSV.

If you see STALE, check the AlphaEdge Dhan options collector (token expiry,
scheduled task, market-hours run) — the backtest numbers are stale, not the
strategy. Thresholds live in `STALE_TRADING_DAYS` / `WATCH_TRADING_DAYS`.

## The scheduled task

- **Name:** `TB007 Weekly Backtest`
- **Schedule:** weekly, Sundays 09:00 (data is unchanged over the weekend, so Sunday captures the full prior week)
- **Runs as:** current user, when logged on (no admin required)

### Manage it

```bat
:: run now
schtasks /Run /TN "TB007 Weekly Backtest"

:: inspect
schtasks /Query /TN "TB007 Weekly Backtest" /FO LIST /V

:: change the day/time (e.g. Saturday 20:00)
schtasks /Change /TN "TB007 Weekly Backtest" /ST 20:00
schtasks /Create /TN "TB007 Weekly Backtest" /TR "D:\Projects\TradingBrain\TB007_WeeklyBacktest.bat" /SC WEEKLY /D SAT /ST 20:00 /F

:: remove
schtasks /Delete /TN "TB007 Weekly Backtest" /F
```

Run the `.bat` manually any time — it is safe and idempotent for the day.

## Notes

- If the machine is off at the scheduled time, the run is skipped; it catches up the following week (or run the `.bat` manually). To run even when not logged on, recreate the task with `/RU <user> /RP <password> /RL LIMITED`.
- The report reads data from `D:/alphaedge/strategy-lab/data/options` (the AlphaEdge Dhan options collector). Keep that collector running so the sample keeps growing.
- Convex strategies need a large sample — the tracker's own header says read the trend, not any single week.
