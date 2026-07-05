# TradingBrain

TradingBrain is a desktop-first intelligent trading platform for strategy development, backtesting, risk management, and MetaTrader 5 execution.

---

## Technology Stack

- Python 3.14
- FastAPI
- PostgreSQL
- SQLAlchemy
- MetaTrader 5
- Next.js (React) Frontend (planned)

---

## Current Version

**v0.1.0-alpha**

---

## Current Status

- ✅ Backend foundation completed
- ✅ FastAPI application running
- ✅ Configuration management
- ✅ Structured logging
- ✅ Health API
- ⏳ PostgreSQL integration
- ⏳ MetaTrader 5 integration

---

## Project Roadmap

### Sprint 1
- Backend Foundation
- PostgreSQL
- MT5 Connectivity
- Market Data API

### Sprint 2
- Strategy Engine
- Risk Engine
- Trade Journal

### Sprint 3
- Backtesting
- Analytics
- Dashboard

---

## Running the Backend

From the `backend` directory:

```bash
uvicorn app.main:app --reload --port 8001
```

Open Swagger:

```
http://127.0.0.1:8001/docs
```

---

## Repository Structure

```
TradingBrain/
│
├── backend/
├── frontend/
├── docs/
├── scripts/
└── docker-compose.yml
```

---

## License

Private project.
