"""
Polybot — Pydantic models for all API requests / responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────

class BotId(str, Enum):
    BOT1 = "bot1"
    BOT2 = "bot2"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    WIN = "WIN"
    LOSS = "LOSS"
    SKIP = "SKIP"


class Side(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class TradingMode(str, Enum):
    LIVE = "live"
    PAPER = "paper"


# ── Bot parameter models ─────────────────────────────────

class Bot1Params(BaseModel):
    """Parameters for Bot 1 — WebSocket Scalper (28–30 cent entry)."""
    market_slug: str = Field("btc-updown-5m", description="Polymarket market slug for BTC 5-min windows")
    amount_usd: float = Field(5.0, gt=0, description="Stake per trade in USD")
    entry_min: float = Field(0.28, ge=0.01, le=0.99, description="Lower bound of entry zone (token ask price)")
    entry_max: float = Field(0.30, ge=0.01, le=0.99, description="Upper bound of entry zone (token ask price)")
    take_profit_cents: float = Field(0.11, gt=0, description="Cents above entry price to take profit (e.g. 0.11 = exit at entry + 0.11)")
    stop_loss_cents: float = Field(0.05, gt=0, description="Cents below entry price to cut loss (e.g. 0.05 = exit at entry − 0.05)")
    time_stop_seconds: int = Field(45, gt=0, description="Force-exit SELL when seconds remaining < this value")
    max_rounds: Optional[int] = Field(None, ge=1, description="Stop after N completed trades (None = unlimited)")


class Bot2Params(BaseModel):
    """Parameters for Bot 2 — Hold to Resolution."""
    market_slug: str = Field(..., description="Polymarket market slug for BTC 5-min windows")
    amount_usd: float = Field(5.0, gt=0, description="Stake per trade in USD")
    min_gap_pct: float = Field(0.10, ge=0.0, description="Minimum BTC gap % to nearest $1000 level to enter")
    max_entry_price: float = Field(0.70, gt=0, le=1.0, description="Max price (odds) to pay")
    max_rounds: Optional[int] = Field(None, ge=1, description="Stop after N rounds (None = unlimited)")


# ── API request models ───────────────────────────────────

class BotStartRequest(BaseModel):
    """POST /api/bot/start body."""
    bot_id: BotId
    dry_run: bool = True
    trading_mode: TradingMode = TradingMode.PAPER
    bot1_params: Optional[Bot1Params] = None
    bot2_params: Optional[Bot2Params] = None


class BotStopRequest(BaseModel):
    """POST /api/bot/stop body."""
    bot_id: BotId


# ── Trade record ──────────────────────────────────────────

class TradeRecord(BaseModel):
    """Mirrors a row in the trades table."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    bot_id: str
    market_id: str
    market_slug: Optional[str] = None
    side: str
    entry_price: float
    exit_price: Optional[float] = None
    shares: float
    amount_usd: float
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    status: str = "OPEN"
    signal_score: Optional[float] = None
    btc_price_entry: Optional[float] = None
    btc_price_exit: Optional[float] = None
    dry_run: bool = True
    trading_mode: str = "paper"
    error_message: Optional[str] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── Config ────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    """POST /api/config body — all fields optional, only supplied ones are updated."""
    polymarket_api_key: Optional[str] = None
    polymarket_wallet_address: Optional[str] = None
    polymarket_private_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_enabled: Optional[bool] = None
    default_dry_run: Optional[bool] = None
    default_amount_usd: Optional[float] = None
    environment: Optional[str] = None


class ConfigResponse(BaseModel):
    """GET /api/config — sensitive keys are masked."""
    polymarket_api_key: str = ""
    polymarket_wallet_address: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_enabled: bool = True
    default_dry_run: bool = True
    default_amount_usd: float = 5.0
    environment: str = "dev"


# ── Bot status ────────────────────────────────────────────

class BotStatus(BaseModel):
    """GET /api/bot/status response."""
    bot_id: Optional[str] = None
    running: bool = False
    session_id: Optional[str] = None
    dry_run: bool = True
    trading_mode: str = "paper"
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    session_pnl: float = 0.0
    started_at: Optional[datetime] = None
    last_activity: str = ""
    round_number: int = 0


# ── Analytics ─────────────────────────────────────────────

class AnalyticsSummary(BaseModel):
    """GET /api/analytics response — aggregated trade statistics."""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    open_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl_per_trade: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    total_volume: float = 0.0


class TradeListResponse(BaseModel):
    """GET /api/trades/all response — paginated trade list."""
    trades: List[Dict[str, Any]] = []
    total: int = 0
    limit: int = 50
    offset: int = 0
