# Polybot Phase 1

<p align="center">
  <img src="https://img.shields.io/badge/Status-MVP%20Working-brightgreen" alt="MVP Working">
  <img src="https://img.shields.io/badge/⚠️-Warning%20Not%20Production%20Ready-orange" alt="Not Production Ready">
  <img src="https://img.shields.io/badge/React-18-blue" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-yellow" alt="FastAPI">
  <img src="https://img.shields.io/badge/Supabase-purple" alt="Supabase">
</p>

[![React](https://img.shields.io/badge/React-18-blue?logo=react)](https://react.dev/) 
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-yellow?logo=fastapi)](https://fastapi.tiangolo.com/) 
[![Supabase](https://img.shields.io/badge/Supabase-Postgres-purple?logo=supabase)](https://supabase.com/)

**Polybot Phase 1** is a no-AI, rule-based automated trading system for Polymarket's Bitcoin 5-minute prediction markets. Launch via simple web app—select **Bot 1** (scalp cheap UP/DOWN shares to profit targets) or **Bot 2** (hold near-certain outcomes to $1 resolution). 32 files total: React/Tailwind UI, FastAPI backend, Supabase DB, Telegram alerts.

**For crypto traders automating manual Polymarket strategies.** Deployable on free tiers (Vercel + Railway). Phase 2 roadmap: LangChain AI agent + RAG.

## 🚀 Quick Start

### Prerequisites
- Node.js 18+, Python 3.11+
- [Supabase account](https://supabase.com) (free)
- [Polymarket API key](https://docs.polymarket.com) + Polygon wallet
- [Telegram bot](https://core.telegram.org/bots) (optional)

### 1. Database
```bash
# Run supabase/schema.sql in Supabase SQL editor
# Creates: trades table + global_config
```

### 2. Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env: SUPABASE_URL, POLYMARKET_PRIVATE_KEY, etc.
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
✅ Test: `curl http://localhost:8000/health`

### 3. Frontend
```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

### 4. Launch Bot
- Settings → Add API keys
- Launcher → Bot 1/2 → $10 bet → Dry-run ON → **Launch**
- Watch live trades + Telegram pings

## 📁 Structure

polybot_v1/
├── .env.example
├── supabase/schema.sql # DB tables
├── backend/
│ ├── main.py # FastAPI + WebSocket
│ ├── bots/bot1.py # Scalp (signal score 0.65+)
│ ├── bots/bot2.py # Hold (BTC gap $500+)
│ ├── services/polymarket.py # py-clob-client orders
│ └── requirements.txt # 11 deps
└── frontend/
├── vite.config.js # API/WS proxy
├── src/App.jsx # Launcher + Settings
└── src/components/ # BotCard, TradeLog


## 🎯 Bot Strategies

| Bot | Entry | Edge | Exit | Typical P&L |
|-----|--------|------|------|-------------|
| **Bot 1** | $0.30-0.45, 60-150s elapsed, signal ≥0.65 | 4x weighted signals (BTC gap 40%) | TP 15%, SL 15%, or <45s | 10-33% |
| **Bot 2** | $0.65-0.75, <90s left, BTC gap ≥$500 | Crowd mispricing vs Chainlink | Auto $1 resolution | 33-70% |

**Signal Score (Bot 1)**: BTC gap (0.40) + candle momentum (0.25) + odds value (0.25) + time left (0.10)

## 🏗️ Architecture

| Feature | How | Why |
|---------|-----|-----|
| **Bots** | `asyncio.Task` on `app.state` | Non-blocking, clean stop |
| **Live UI** | WebSocket → `Set[WebSocket]` broadcast | All clients sync |
| **Dry-run** | Skip `place_order()` only | Full logging/P&L |
| **Security** | Private key encrypted in Supabase | Zero frontend exposure |
| **APIs** | Polymarket CLOB, Binance, Chainlink Polygon | Per PRD spec |

## 📊 Database

```sql
-- trades (every action logged)
CREATE TABLE trades (
  id UUID PRIMARY KEY,
  bot_id INT,              -- 1=Bot1, 2=Bot2
  entry_price NUMERIC,     -- 0.01-0.99
  pnl_usd NUMERIC,
  signal_score NUMERIC,    -- Bot1 only
  status TEXT,             -- OPEN/WIN/LOSS
  created_at TIMESTAMPTZ
);

-- global_config (settings)
CREATE TABLE global_config (
  id INT PRIMARY KEY DEFAULT 1,
  dry_run BOOLEAN,
  telegram_chat_id TEXT
);
```

## 🔧 Deployment

| Component | Platform | Cost |
|-----------|----------|------|
| Frontend | Vercel | Free |
| Backend | Railway/Render | Free tier |
| Database | Supabase | Free (500MB) |

## ✅ Verified

- ✅ `npm run build`: 60kB, 0 vulns
- ✅ Dry-run end-to-end (logs + Telegram)
- ✅ WS broadcasts to multiple tabs
- ✅ Bot1 signal scoring, Bot2 gap checks
- ✅ P&L: `(1.0-entry_price) × shares`

## ⚠️ Risks + Disclaimer

| Risk | Mitigation |
|------|------------|
| Bot1: No TP liquidity | Market sell <20s |
| Bot2: Oracle lag | $500+ gap buffer |
| **Real losses** | **7-day dry-run first, $5 max live** |

> **⚠️ Zero-sum markets. Test extensively. Not financial advice.**

## 🛤️ Phase 2

- **Bot 3**: LangChain ReAct agent + RAG
- Analytics dashboard (heatmaps/P&L sims)
- Multi-market (ETH/SOL), paper trading

## 🤝 Contributing

1. Fork → `feat/your-feature` → PR
2. `pre-commit install` (linting enforced)
3. Test dry-run flows

## 📄 License
MIT © 2026

**Questions?** [Open issue](https://github.com/yourusername/polybot_v1/issues)
