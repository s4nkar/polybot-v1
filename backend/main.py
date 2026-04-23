"""
Polybot — FastAPI application.

Endpoints:
  POST   /api/bot/start    Start bot 1 or 2 as a background asyncio task
  POST   /api/bot/stop     Signal the running bot to stop
  GET    /api/bot/status    Current bot status + session summary
  GET    /api/trades        Recent trades for the active session
  GET    /api/trades/all    Paginated trade history across all sessions
  GET    /api/analytics     Aggregated analytics summary
  GET    /api/config        Global config (sensitive keys masked)
  POST   /api/config        Update global config
  WS     /ws/trades         Real-time trade-event stream
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bots.bot1 import run_bot1
from bots.bot2 import run_bot2
from db import supabase as db
from models.schemas import (
    AnalyticsSummary,
    Bot1Params,
    Bot2Params,
    BotStartRequest,
    BotStatus,
    BotStopRequest,
    ConfigResponse,
    ConfigUpdate,
    TradeListResponse,
    TradeRecord,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("polybot.log", mode="w", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── FastAPI app ───────────────────────────────────────────

app = FastAPI(title="Polybot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── App-level state ──────────────────────────────────────

class AppState:
    """Mutable state bag stored on app.state."""
    bot_task: asyncio.Task | None = None
    stop_event: asyncio.Event = asyncio.Event()
    running_bot_id: str | None = None
    session_id: str | None = None
    dry_run: bool = True
    trading_mode: str = "paper"
    started_at: datetime | None = None
    ws_clients: Set[WebSocket] = set()
    last_activity: str = ""
    round_number: int = 0


state = AppState()


# ── 24-hour auto-stop helper ─────────────────────────────

AUTO_STOP_SECONDS = 24 * 60 * 60  # 86 400 sec = 24 hours


async def _auto_stop_after(seconds: float, stop_event: asyncio.Event) -> None:
    """Wait *seconds*, then set stop_event to gracefully stop the bot."""
    try:
        await asyncio.sleep(seconds)
        if not stop_event.is_set():
            stop_event.set()
            logger.info("24-hour timer expired — bot auto-stopped")
    except asyncio.CancelledError:
        pass


async def _run_with_auto_stop(
    coro,
    stop_event: asyncio.Event,
    auto_stop_seconds: float = AUTO_STOP_SECONDS,
) -> None:
    """Run *coro* alongside a 24-hour watchdog timer."""
    timer_task = asyncio.create_task(
        _auto_stop_after(auto_stop_seconds, stop_event)
    )
    try:
        await coro
    finally:
        timer_task.cancel()


# ── WebSocket broadcast helper ───────────────────────────

async def broadcast(payload: Dict[str, Any]) -> None:
    """Send *payload* as JSON to every connected WebSocket client."""
    message = json.dumps(payload, default=str)
    dead: List[WebSocket] = []
    for ws in state.ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        state.ws_clients.discard(ws)


# ── Routes ────────────────────────────────────────────────

@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/bot/start")
async def start_bot(req: BotStartRequest) -> Dict[str, Any]:
    """Start a bot in a background task."""
    if state.bot_task and not state.bot_task.done():
        return {"ok": False, "error": "A bot is already running. Stop it first."}

    session_id = str(uuid.uuid4())
    state.stop_event = asyncio.Event()
    state.session_id = session_id
    state.running_bot_id = req.bot_id.value
    state.dry_run = req.dry_run
    state.trading_mode = req.trading_mode.value
    state.started_at = datetime.now(timezone.utc)
    state.last_activity = "Starting…"
    state.round_number = 0

    trading_mode = req.trading_mode.value

    def status_update(activity: str, round_num: int = 0):
        """Callback for bots to report their current activity."""
        state.last_activity = activity
        state.round_number = round_num

    if req.bot_id.value == "bot1":
        params = req.bot1_params or Bot1Params(market_slug="btc-5min")
        bot_coro = run_bot1(
            params=params,
            session_id=session_id,
            dry_run=req.dry_run,
            stop_event=state.stop_event,
            broadcast=broadcast,
            trading_mode=trading_mode,
            status_update=status_update,
        )
    else:
        params = req.bot2_params or Bot2Params(market_slug="btc-5min")
        bot_coro = run_bot2(
            params=params,
            session_id=session_id,
            dry_run=req.dry_run,
            stop_event=state.stop_event,
            broadcast=broadcast,
            trading_mode=trading_mode,
            status_update=status_update,
        )

    # Wrap in 24-hour auto-stop
    state.bot_task = asyncio.create_task(
        _run_with_auto_stop(bot_coro, state.stop_event)
    )

    logger.info(
        "Started %s — session=%s mode=%s dry_run=%s",
        req.bot_id.value, session_id, trading_mode, req.dry_run,
    )
    return {
        "ok": True,
        "bot_id": req.bot_id.value,
        "session_id": session_id,
        "dry_run": req.dry_run,
        "trading_mode": trading_mode,
    }


@app.post("/api/bot/stop")
async def stop_bot(req: BotStopRequest | None = None) -> Dict[str, Any]:
    """Signal the running bot to stop gracefully."""
    if not state.bot_task or state.bot_task.done():
        return {"ok": False, "error": "No bot is running."}

    state.stop_event.set()
    logger.info("Stop signal sent to %s", state.running_bot_id)
    return {"ok": True, "message": "Stop signal sent."}


@app.get("/api/bot/status")
async def bot_status() -> BotStatus:
    """Return current bot status and session summary."""
    running = state.bot_task is not None and not state.bot_task.done()

    if not state.session_id:
        return BotStatus(running=running)

    trades = db.get_session_trades(state.session_id)
    wins = sum(1 for t in trades if t.get("status") == "WIN")
    losses = sum(1 for t in trades if t.get("status") == "LOSS")
    total = len(trades)
    win_rate = (wins / total * 100) if total > 0 else 0.0
    pnl = sum(float(t.get("pnl_usd", 0) or 0) for t in trades)

    return BotStatus(
        bot_id=state.running_bot_id,
        running=running,
        session_id=state.session_id,
        dry_run=state.dry_run,
        trading_mode=state.trading_mode,
        total_trades=total,
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 2),
        session_pnl=round(pnl, 4),
        started_at=state.started_at,
        last_activity=state.last_activity,
        round_number=state.round_number,
    )


@app.get("/api/trades")
async def get_trades() -> List[Dict[str, Any]]:
    """Return trades for the current session."""
    if not state.session_id:
        return []
    return db.get_session_trades(state.session_id)


@app.get("/api/trades/all")
async def get_all_trades(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    mode: str = Query("all", regex="^(all|live|paper)$"),
) -> TradeListResponse:
    """Return paginated trade history across all sessions."""
    trading_mode = mode if mode != "all" else None
    trades, total = db.get_all_trades(limit=limit, offset=offset, trading_mode=trading_mode)
    return TradeListResponse(trades=trades, total=total, limit=limit, offset=offset)


@app.get("/api/analytics")
async def get_analytics(
    mode: str = Query("all", regex="^(all|live|paper)$"),
) -> AnalyticsSummary:
    """Return aggregated analytics across all trades."""
    trading_mode = mode if mode != "all" else None
    summary = db.get_analytics_summary(trading_mode=trading_mode)
    return AnalyticsSummary(**summary)


def _mask(value: str | None) -> str:
    """Mask a sensitive string: show first 4 and last 4 chars."""
    if not value or len(value) < 10:
        return "****" if value else ""
    return value[:4] + "****" + value[-4:]


@app.get("/api/config")
async def get_config() -> ConfigResponse:
    """Return global config with sensitive keys masked."""
    row = db.get_config()
    return ConfigResponse(
        polymarket_api_key=_mask(row.get("polymarket_api_key")),
        polymarket_wallet_address=_mask(row.get("polymarket_wallet_address")),
        telegram_bot_token=_mask(row.get("telegram_bot_token")),
        telegram_chat_id=row.get("telegram_chat_id", ""),
        telegram_enabled=row.get("telegram_enabled", True),
        default_dry_run=row.get("default_dry_run", True),
        default_amount_usd=float(row.get("default_amount_usd", 5.0)),
        environment=row.get("environment", "dev"),
    )


@app.post("/api/config")
async def update_config(req: ConfigUpdate) -> Dict[str, Any]:
    """Update global config — only supplied fields are changed."""
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"ok": False, "error": "No fields to update."}

    # Never persist the private key label in plain text in the API response
    db.update_config(updates)
    return {"ok": True, "updated": list(updates.keys())}


# ── WebSocket ─────────────────────────────────────────────

@app.websocket("/ws/trades")
async def ws_trades(ws: WebSocket) -> None:
    """Broadcast trade events to all connected clients."""
    await ws.accept()
    state.ws_clients.add(ws)
    logger.info("WebSocket client connected (%d total)", len(state.ws_clients))
    try:
        while True:
            # Keep connection alive — client can also send pings
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        state.ws_clients.discard(ws)
        logger.info("WebSocket client disconnected (%d remaining)", len(state.ws_clients))


# ── Entrypoint ────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="::", port=8000, reload=True)
