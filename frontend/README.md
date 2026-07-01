# TradingBrain Frontend

A Vite + React + TypeScript dashboard for running TB001 backtests and viewing
results (summary metrics, equity curve, trade log, full text report).

- Dev server: **http://localhost:5174** (fixed via `strictPort`)
- Talks to the backend at **http://localhost:8200/api/v1** (configurable via
  `VITE_API_BASE_URL` in `.env`)

## Setup

```bash
cd frontend
npm install
cp .env.example .env   # adjust VITE_API_BASE_URL if the backend moves
npm run dev            # http://localhost:5174
```

The backend must be running on port 8200 (its CORS allow-list already trusts
`http://localhost:5174`):

```bash
cd ../backend
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8200 --reload
```

## Scripts

| Script | Purpose |
|--------|---------|
| `npm run dev` | Dev server on 5174 |
| `npm run build` | Type-check (`tsc -b`) + production build to `dist/` |
| `npm run preview` | Serve the production build on 5174 |
| `npm run typecheck` | Type-check only |

## What it shows

- **Backend health badge** (polls `/health` every 10s).
- **Backtest form**: symbol, sessions, bar size, capital, implied vs realized
  vol, seed.
- **Summary cards**: net P&L (post-cost), return, win rate, profit factor,
  drawdown, Sharpe, **total transaction costs**, gross P&L (pre-cost).
- **Equity curve** (dependency-free SVG) and a **trade log**.
- Collapsible **full text report**.

All backtest P&L is **net of realistic NSE F&O costs** (brokerage, STT,
exchange, SEBI, GST, stamp duty) — see `backend/app/domains/execution/costs.py`.
