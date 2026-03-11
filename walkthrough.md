# Polybot Phase 1 — Walkthrough

## What Was Built

A complete full-stack automated trading web application for Polymarket Bitcoin 5-minute prediction markets, consisting of **32 files** across backend, frontend, and database layers.

## Project Structure

```
polybot_v1/
├── .env.example
├── supabase/
│   └── schema.sql               # trades + global_config tables with indexes
├── backend/
│   ├── main.py                   # FastAPI app, 6 REST endpoints + WebSocket
│   ├── config.py                 # All env vars loaded via python-dotenv
│   ├── requirements.txt          # 11 Python dependencies
│   ├── bots/
│   │   ├── bot1.py               # Scalp to Target — 10-step loop
│   │   └── bot2.py               # Hold to Resolution — 9-step loop
│   ├── services/
│   │   ├── polymarket.py         # Market discovery, orderbook, order placement
│   │   ├── binance.py            # BTC price, klines, signal score (4 weights)
│   │   ├── chainlink.py          # BTC/USD from Polygon Chainlink oracle
│   │   └── telegram.py           # 8 named message functions, fire-and-forget
│   ├── db/
│   │   └── supabase.py           # CRUD for trades + global_config
│   └── models/
│       └── schemas.py            # 10 Pydantic models with validation
└── frontend/
    ├── package.json
    ├── vite.config.js            # Proxy /api → backend, /ws → WebSocket
    ├── tailwind.config.js        # Custom brand/surface palette
    ├── index.html
    └── src/
        ├── App.jsx               # Router with nav bar (Dashboard + Settings)
        ├── main.jsx
        ├── index.css
        ├── services/
        │   └── api.js            # All fetch calls + WebSocket factory
        ├── components/
        │   ├── BotCard.jsx       # Selectable card with running pulse
        │   ├── BotForm.jsx       # Dynamic form per bot with validation
        │   ├── TradeLog.jsx      # Color-coded trade table, auto-scroll
        │   └── SessionSummary.jsx # 5 stat cards with conditional coloring
        └── pages/
            ├── Launcher.jsx      # Dashboard: cards + form + live monitor
            └── Settings.jsx      # API keys, Telegram, defaults
```

## Key Architecture Decisions

| Decision | Rationale |
|---|---|
| Bot runs as `asyncio.Task` on `app.state` | Never blocks FastAPI; clean stop via `asyncio.Event` |
| WebSocket broadcasts to **all** clients | Stored in a `Set[WebSocket]`; dead connections cleaned up |
| Chainlink used for Bot 2, Binance for Bot 1 | Per PRD — Bot 2 needs on-chain reference price |
| Bot 2 never sells | Holds until market resolves; P&L = [(1.0 - entry) × shares](file:///d:/Projects/Vibe%20Code/polybot_v1/frontend/src/App.jsx#6-57) |
| Dry-run mode skips only [place_order](file:///d:/Projects/Vibe%20Code/polybot_v1/backend/services/polymarket.py#117-172) | All logging, Telegram, DB, and P&L calculation still run |
| Private key never logged/exposed | Masked with [_mask()](file:///d:/Projects/Vibe%20Code/polybot_v1/backend/main.py#183-188) in config GET endpoint |
| Signal score uses 4 weighted components | BTC gap 0.40, candle momentum 0.25, odds value 0.25, time 0.10 |

## How to Run

### Backend
```bash
cd backend
pip install -r requirements.txt
# Copy .env.example to .env and fill in real values
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install    # already done
npm run dev    # → http://localhost:5173
```

### Database
Run [supabase/schema.sql](file:///d:/Projects/Vibe%20Code/polybot_v1/supabase/schema.sql) in your Supabase SQL editor to create tables.

## Verification Results

| Check | Result |
|---|---|
| Frontend `npm install` | ✅ 134 packages, 0 vulnerabilities |
| Frontend `npm run build` | ✅ 60.68 kB, built in 1.14s |
| All 32 files generated | ✅ Confirmed via file listing |
| No TODOs or placeholders | ✅ Every function has working code |
| CORS configured for localhost:5173 | ✅ |
| Prices treated as 0–1 floats | ✅ All P&L calculations correctly handle cents |
