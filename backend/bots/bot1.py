"""
Polybot — Bot 1: WebSocket Scalper (28–30 cent entry).

Strategy
--------
  Entry condition:
    - Scan for the active 5-min BTC market once per minute (scanner loop).
    - Subscribe the UP and DOWN token IDs to a live WebSocket price stream.
    - Enter a trade the moment the best_ask of EITHER side crosses into the
      entry zone [entry_min, entry_max] (default 0.28–0.30).
    - Only one position is open at a time.  Once entered, ignore further
      WebSocket ticks until the position is fully closed.

  Exit conditions (all three active simultaneously):
    1. TAKE_PROFIT  — best_bid rises `take_profit_cents` above entry_price.
                      e.g. entry 0.29 + 0.11 cents = exit at 0.40.
    2. STOP_LOSS    — best_bid falls `stop_loss_cents` below entry_price.
                      e.g. entry 0.29 − 0.05 = exit at 0.24.
    3. TIME_STOP    — market has < `time_stop_seconds` remaining.
                      Place a SELL at the current best_bid immediately —
                      do NOT wait for settlement (per user preference).

  After exit: wait for the next 5-minute window and repeat.

Architecture
------------
  Two concurrent asyncio tasks per round:

    scanner_task   — runs every 60 s; fetches the active market from Gamma
                     API, extracts token IDs, starts/restarts the WS stream.

    ws_stream_task — calls polymarket.stream_orderbook() which pushes
                     (best_bid, best_ask) to _on_price_update() every time
                     the orderbook changes.

  _on_price_update() is a synchronous callback that:
    - If no position open: checks entry condition → schedules _enter_trade().
    - If position open:    checks TP / SL / time-stop → schedules _exit_trade().

  All state that crosses the callback/coroutine boundary is held in the
  BotState dataclass and protected by an asyncio.Lock so concurrent callbacks
  never corrupt it.

Parameters (Bot1Params fields used)
------------------------------------
  market_slug          — e.g. "btc-updown-5m"
  amount_usd           — USD per trade
  entry_min            — lower bound of entry zone (default 0.28)
  entry_max            — upper bound of entry zone (default 0.30)
  take_profit_cents    — cents above entry to take profit (default 0.11)
  stop_loss_cents      — cents below entry to cut loss  (default 0.05)
  time_stop_seconds    — seconds remaining before forced exit (default 45)
  max_rounds           — stop after N completed trades (0 = unlimited)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from db import supabase as db
from models.schemas import Bot1Params
from services import polymarket_v2 as polymarket, telegram

logger = logging.getLogger(__name__)


# ── Bot state ─────────────────────────────────────────────────────────────────


@dataclass
class BotState:
    """
    All mutable state for one bot session.

    Shared between the scanner loop, the WebSocket callback, and the
    trade-execution coroutines.  Protected by `lock`.
    """
    # Session / control
    session_id:    str             = ""
    bot_id:        str             = "bot1"
    dry_run:       bool            = True
    trading_mode:  str             = "paper"
    round_num:     int             = 0
    stop_event:    Optional[asyncio.Event] = None

    # Active market
    market_id:     str             = ""
    market_slug:   str             = ""
    end_date_str:  str             = ""
    up_token_id:   str             = ""
    down_token_id: str             = ""

    # Open position
    in_position:   bool            = False
    trade_id:      str             = ""
    side:          str             = ""          # "UP" or "DOWN"
    token_to_buy:  str             = ""
    entry_price:   float           = 0.0
    shares:        float           = 0.0
    target_price:  float           = 0.0
    stop_price:    float           = 0.0

    # Concurrency
    lock:          asyncio.Lock    = field(default_factory=asyncio.Lock)
    enter_task:    Optional[asyncio.Task] = None
    exit_task:     Optional[asyncio.Task] = None

    # Throttle — avoid firing entry/exit twice on back-to-back ticks
    entry_fired:   bool            = False
    exit_fired:    bool            = False

    # Callbacks
    broadcast:     Optional[Callable] = None
    status_update: Optional[Callable] = None

    window_start_time: float = 0.0
    trades_in_window: int = 0
    max_trades_per_window: int = 2


# ── Main entry point ──────────────────────────────────────────────────────────


async def run_bot1(
    params: Bot1Params,
    session_id: str,
    dry_run: bool,
    stop_event: asyncio.Event,
    broadcast: Optional[Callable] = None,
    trading_mode: str = "paper",
    status_update: Optional[Callable] = None,
) -> None:
    """
    Start Bot 1 — WebSocket Scalper.

    Spawns a scanner loop that refreshes the active market every 60 s and
    manages a WebSocket stream for real-time entry/exit detection.
    """
    state = BotState(
        session_id=session_id,
        dry_run=dry_run,
        trading_mode=trading_mode,
        stop_event=stop_event,
        broadcast=broadcast,
        status_update=status_update,
        market_slug=params.market_slug,
    )

    await telegram.bot_started(state.bot_id, dry_run, params.model_dump())
    logger.info("Bot1 started — session=%s dry_run=%s", session_id, dry_run)

    # The WS stream task is managed here; replaced whenever the market changes.
    ws_stop_event:  asyncio.Event        = asyncio.Event()
    ws_task:        Optional[asyncio.Task] = None

    last_telegram_skip = 0.0

    async def maybe_skip(reason: str) -> None:
        nonlocal last_telegram_skip
        import time
        ts = time.time()
        if ts - last_telegram_skip > 60:
            await telegram.trade_skipped(state.bot_id, reason)
            last_telegram_skip = ts
        logger.info("Bot1 skip: %s", reason)

    # ── Scanner loop — runs every 60 s ────────────────────────────────────────

    while not stop_event.is_set():

        if params.max_rounds and state.round_num >= params.max_rounds:
            logger.info("Bot1 reached max_rounds=%d — stopping.", params.max_rounds)
            break

        _status(state, f"Scanning for active market… (round {state.round_num + 1})")

        # ── Step 1: Discover the active market ────────────────────────────────
        try:
            markets = await polymarket.get_active_markets(params.market_slug)
        except Exception as exc:
            logger.error("Market scan error: %s", exc)
            await asyncio.sleep(10)
            continue

        if not markets:
            await maybe_skip("No active markets found")
            _status(state, "No active market — retrying in 15 s")
            await _interruptible_sleep(15, stop_event)
            continue

        market        = markets[0]
        new_market_id = market.get("condition_id", market.get("id", ""))

        if new_market_id != state.market_id:
            state.trades_in_window = 0  # Reset counter
            state.in_position = False
            state.entry_fired = False
            state.exit_fired = False
            logger.info(f"New market window detected — reset trade counter")

        # ── Step 2: Extract token IDs ──────────────────────────────────────────
        up_token_id, down_token_id = _extract_token_ids(market)

        if not up_token_id or not down_token_id:
            await maybe_skip(f"Could not extract token IDs from market {new_market_id}")
            await _interruptible_sleep(10, stop_event)
            continue

        # ── Step 3: Validate outcomePrices (skip resolved markets) ────────────
        up_price, down_price, prices_ok = _parse_outcome_prices(market)

        if not prices_ok:
            await maybe_skip("outcomePrices parse failed")
            await _interruptible_sleep(10, stop_event)
            continue

        if up_price >= 0.99 or up_price <= 0.01 or down_price >= 0.99 or down_price <= 0.01:
            await maybe_skip(
                f"Market looks resolved (UP={up_price:.4f} DOWN={down_price:.4f})"
            )
            await _interruptible_sleep(10, stop_event)
            continue

        seconds_remaining = market.get("seconds_remaining", 0.0)

        # Need at least time_stop_seconds + 60 s remaining to enter a new round.
        min_window = params.time_stop_seconds + 60
        if seconds_remaining < min_window:
            msg = (
                f"Market window too short ({seconds_remaining:.0f}s remaining, "
                f"need {min_window}s) — waiting for next window"
            )
            logger.info(msg)
            _status(state, msg)
            await _interruptible_sleep(max(5, int(seconds_remaining) + 5), stop_event)
            continue

        # ── Step 4: (Re)start WebSocket if market changed ─────────────────────
        market_changed = (new_market_id != state.market_id)

        if market_changed or ws_task is None or ws_task.done():
            # Tear down the old WS stream.
            if ws_task and not ws_task.done():
                ws_stop_event.set()
                try:
                    await asyncio.wait_for(ws_task, timeout=5.0)
                except Exception:
                    pass

            ws_stop_event.clear()

            # Update state for the new market.
            async with state.lock:
                state.market_id     = new_market_id
                state.end_date_str  = market.get("endDate", "")
                state.up_token_id   = up_token_id
                state.down_token_id = down_token_id
                # Reset position state when a new market starts.
                if not state.in_position:
                    state.entry_fired = False
                    state.exit_fired  = False

            # Subscribe UP token (price of UP implicitly gives DOWN via 1 - UP).
            # We also subscribe DOWN separately so we catch whichever hits entry.
            ws_task = asyncio.create_task(
                _run_dual_stream(
                    up_token_id=up_token_id,
                    down_token_id=down_token_id,
                    state=state,
                    params=params,
                    ws_stop_event=ws_stop_event,
                )
            )
            await asyncio.sleep(0)
            logger.info(
                "WS stream (re)started — market=%s UP=%s DOWN=%s",
                new_market_id, up_token_id, down_token_id,
            )
            _status(
                state,
                f"Watching market {new_market_id} — waiting for entry "
                f"({params.entry_min:.2f}–{params.entry_max:.2f})…",
            )

        # Sleep 60 s between scans, but break early if stop_event fires.
        await _interruptible_sleep(60, stop_event)

    # ── Teardown ──────────────────────────────────────────────────────────────
    ws_stop_event.set()
    if ws_task and not ws_task.done():
        try:
            await asyncio.wait_for(ws_task, timeout=5.0)
        except Exception:
            pass

    # ── Session summary ───────────────────────────────────────────────────────
    session_trades = db.get_session_trades(session_id)
    total_pnl      = sum(float(t.get("pnl_usd", 0) or 0) for t in session_trades)
    await telegram.bot_stopped(state.bot_id, len(session_trades), total_pnl)
    logger.info(
        "Bot1 stopped — session=%s trades=%d pnl=%.4f",
        session_id, len(session_trades), total_pnl,
    )


# ── Dual WebSocket stream ─────────────────────────────────────────────────────


async def _run_dual_stream(
    up_token_id: str,
    down_token_id: str,
    state: BotState,
    params: Bot1Params,
    ws_stop_event: asyncio.Event,
) -> None:
    """
    Run two concurrent WebSocket streams — one for each side (UP and DOWN).

    Both streams call the same _on_price_update callback so whichever side
    hits the entry zone first triggers the trade.
    """
    def make_callback(side: str) -> Callable:
        def _cb(best_bid: float, best_ask: float) -> None:
            _on_price_update(
                best_bid=best_bid,
                best_ask=best_ask,
                tick_side=side,
                state=state,
                params=params,
            )
        return _cb

    up_task   = asyncio.create_task(
        polymarket.stream_orderbook(
            token_id=up_token_id,
            on_price=make_callback("UP"),
            stop_event=ws_stop_event,
        )
    )
    down_task = asyncio.create_task(
        polymarket.stream_orderbook(
            token_id=down_token_id,
            on_price=make_callback("DOWN"),
            stop_event=ws_stop_event,
        )
    )
    await asyncio.sleep(0)
    await asyncio.gather(up_task, down_task, return_exceptions=True)


# ── Price update callback ─────────────────────────────────────────────────────


def _on_price_update(
    best_bid: float,
    best_ask: float,
    tick_side: str,
    state: BotState,
    params: Bot1Params,
) -> None:
    """
    Called on every WebSocket tick for either the UP or DOWN token.

    Synchronous — must not block.  Schedules async tasks for trade execution.

    Entry logic:
      - No position open AND entry not already fired this window.
      - best_ask of this side is within [entry_min, entry_max].
      - Market has enough time remaining (checked inside _enter_trade).

    Exit logic (all three monitored simultaneously):
      - best_bid >= target_price  → TAKE_PROFIT
      - best_bid <= stop_price    → STOP_LOSS
      - time remaining < time_stop_seconds → TIME_STOP
    """
    logger.debug(
        "WS tick — side=%s bid=%.4f ask=%.4f in_position=%s",
        tick_side, best_bid, best_ask, state.in_position,
    )

    if state.stop_event and state.stop_event.is_set():
        return

    loop = asyncio.get_event_loop()
    # Add this before 'in_zone = ...'
    logger.debug(f"DEBUG: Side {tick_side} Ask: {best_ask} | Zone: {params.entry_min}-{params.entry_max}")
    if not state.in_position:
        # ── Entry condition check ──────────────────────────────────────────
        if state.entry_fired:
            return  # already entering, wait for it to complete

        if state.trades_in_window >= state.max_trades_per_window:
            logger.info(f"Trade limit reached ({state.trades_in_window}/{state.max_trades_per_window}) in market {state.market_id}")
            return
        
        in_zone = params.entry_min <= best_ask <= params.entry_max

        if in_zone:
            state.in_position = True
            state.trades_in_window += 1
            state.side = tick_side
            state.entry_price = best_ask
            
            logger.warning(f"✅ ENTRY LOCKED! price={best_ask:.4f}")
            
            # NOW schedule the async task (optional, for DB insert)
            loop = asyncio.get_event_loop()
            state.enter_task  = loop.create_task(
                _enter_trade(
                    tick_side=tick_side,
                    indicative_ask=best_ask,
                    state=state,
                    params=params,
                )
            )

    else:
        # ── Position monitoring — only care about ticks for OUR token ─────
        if tick_side != state.side:
            return
        if state.exit_fired:
            return  # exit already in flight

        current_bid = best_bid

        # Check time remaining from end_date_str.
        secs_rem = _seconds_remaining(state.end_date_str)

        # Determine exit reason (check time-stop first — highest priority).
        exit_reason: Optional[str] = None

        if secs_rem < params.time_stop_seconds:
            exit_reason = "TIME_STOP"
        elif current_bid >= state.target_price:
            exit_reason = "TAKE_PROFIT"
        elif 0.0 < current_bid <= state.stop_price:
            exit_reason = "STOP_LOSS"

        if exit_reason:
            logger.info(
                "Exit condition — reason=%s bid=%.4f target=%.4f stop=%.4f secs_rem=%.0f",
                exit_reason, current_bid,
                state.target_price, state.stop_price, secs_rem,
            )
            state.exit_fired = True
            state.exit_task  = loop.create_task(
                _exit_trade(
                    exit_reason=exit_reason,
                    current_bid=current_bid,
                    state=state,
                    params=params,
                )
            )


# ── Trade execution ───────────────────────────────────────────────────────────


async def _enter_trade(
    tick_side: str,
    indicative_ask: float,
    state: BotState,
    params: Bot1Params,
) -> None:
    """
    Open a position.

    1. REST snapshot to get the exact live ask (WebSocket tick may be stale).
    2. Re-validate the ask is still inside the entry zone.
    3. Re-validate seconds remaining is sufficient.
    4. Place BUY order.
    5. Set TP / SL levels and mark position open.
    """
    try:
        logger.warning(f"🔴 _enter_trade START — waiting for lock...")
        async with state.lock:
            logger.warning(f"🔴 _enter_trade LOCK ACQUIRED")
            if state.in_position:
                logger.warning(f"🔴 _enter_trade EARLY RETURN — already in_position")
                # Another tick triggered entry simultaneously — ignore.
                return

            token_to_buy = (
                state.up_token_id if tick_side == "UP" else state.down_token_id
            )
            logger.warning(f"🔴 _enter_trade PROCEEDING — token={token_to_buy}")

            # Use indicative_ask from WS tick
            entry_price = indicative_ask

            # ── 3. Re-validate time ────────────────────────────────────────────
            secs_rem = _seconds_remaining(state.end_date_str)
            if secs_rem < params.time_stop_seconds + 30:
                logger.info(
                    "Entry cancelled — only %.0fs remaining (need %ds)",
                    secs_rem, params.time_stop_seconds + 30,
                )
                state.entry_fired = False
                return

            shares = round(params.amount_usd / entry_price, 4)

            # ── 4. Place BUY order ─────────────────────────────────────────────
            order_result = await polymarket.place_order(
                side="BUY",
                amount=params.amount_usd,
                price=entry_price,
                token_id=token_to_buy,
                dry_run=state.dry_run,
            )

            # ── 5. Compute TP / SL levels and update state ────────────────────
            # Fixed-cents strategy: TP and SL are absolute price levels derived
            # from exact entry price.  Clamped to valid binary range (0.02–0.98).
            target_price = min(entry_price + (params.take_profit_cents / 100), 0.98)
            stop_price = max(entry_price - (params.stop_loss_cents / 100), 0.02)

            trade_id = str(uuid.uuid4())
            now_iso  = datetime.now(timezone.utc).isoformat()

            state.in_position   = True
            state.trade_id      = trade_id
            state.side          = tick_side
            state.token_to_buy  = token_to_buy
            state.entry_price   = entry_price
            state.shares        = shares
            state.target_price  = target_price
            state.stop_price    = stop_price
            state.exit_fired    = False
            state.round_num    += 1

            trade_record = {
                "id":              trade_id,
                "session_id":      state.session_id,
                "bot_id":          state.bot_id,
                "market_id":       state.market_id,
                "market_slug":     state.market_slug,
                "side":            tick_side,
                "entry_price":     float(entry_price),
                "shares":          float(shares),
                "amount_usd":      float(params.amount_usd),
                "signal_score":    0.0,   # no signal scoring in this strategy
                "order_id":        order_result.get("order_id", ""),
                "token_id":        token_to_buy,
                "target_price":    float(target_price),
                "stop_price":      float(stop_price),
                "take_profit_cents": float(params.take_profit_cents),
                "stop_loss_cents":   float(params.stop_loss_cents),
                "dry_run":         state.dry_run,
                "trading_mode":    state.trading_mode,
                "status":          "OPEN",
                "opened_at":       now_iso,
                "created_at":      now_iso,
                "updated_at":      now_iso,
            }
            logger.warning(f"🔴 INSERTING TRADE: {trade_record}")
            db.insert_trade(trade_record)
            logger.warning(f"✅ TRADE INSERTED: {trade_id}")

            await telegram.trade_opened_bot1(
                side=tick_side,
                entry_price=entry_price,
                shares=shares,
                amount_usd=params.amount_usd,
                signal_score=0.0,
                market_id=state.market_id,
                dry_run=state.dry_run,
            )

            if state.broadcast:
                await state.broadcast({"type": "trade_opened", "trade": trade_record})

            _status(
                state,
                f"ENTERED {tick_side} @ {entry_price:.4f} | "
                f"TP {target_price:.4f} | SL {stop_price:.4f} | "
                f"{secs_rem:.0f}s left",
            )

            logger.info(
                "Trade opened — id=%s side=%s entry=%.4f TP=%.4f SL=%.4f",
                trade_id, tick_side, entry_price, target_price, stop_price,
            )
    except Exception as exc:
        logger.error(f"❌ CRITICAL ENTRY ERROR: {exc}", exc_info=True)
    finally:
        if not state.in_position:
            logger.warning(f"🔴 finally block — resetting entry_fired")
            state.entry_fired = False
async def _exit_trade(
    exit_reason: str,
    current_bid: float,
    state: BotState,
    params: Bot1Params,
) -> None:
    """
    Close an open position.

    Exit price is always the current best_bid (what the market will pay us).
    For TIME_STOP: take a fresh REST snapshot for the most accurate bid,
    then place a market SELL immediately — do NOT wait for settlement.
    For TAKE_PROFIT / STOP_LOSS: use the bid that triggered the exit.
    On BOT_STOPPED: fetch best_bid via REST as a final snapshot.
    """
    async with state.lock:
        if not state.in_position:
            return  # already closed

        trade_id     = state.trade_id
        side         = state.side
        token_to_buy = state.token_to_buy
        entry_price  = state.entry_price
        shares       = state.shares

        exit_price = current_bid

        # For TIME_STOP, get the freshest bid via REST before selling.
        if exit_reason == "TIME_STOP":
            try:
                ob         = await polymarket.get_orderbook(token_to_buy)
                fresh_bid  = ob["best_bid"]
                exit_price = fresh_bid if fresh_bid > 0.0 else current_bid
            except Exception as exc:
                logger.warning("TIME_STOP orderbook fetch failed: %s — using WS bid", exc)

        # Fallback: if exit_price still 0, use entry as a safe fallback.
        if exit_price <= 0.0:
            exit_price = entry_price

        # ── Place SELL order for non-dry-run exits that need a manual close ─
        # TIME_STOP: SELL immediately at best_bid (user preference: no settlement wait).
        # TAKE_PROFIT / STOP_LOSS: SELL at the bid that triggered the condition.
        # BOT_STOPPED: also SELL to avoid leaving dangling positions.
        needs_sell = exit_reason in ("TAKE_PROFIT", "STOP_LOSS", "TIME_STOP", "BOT_STOPPED")

        if not state.dry_run and needs_sell:
            await polymarket.place_order(
                side="SELL",
                amount=shares * exit_price,
                price=exit_price,
                token_id=token_to_buy,
                dry_run=False,
                size=shares,          # B2 fix: pass shares directly
            )

        # ── P&L ───────────────────────────────────────────────────────────
        pnl_usd = (exit_price - entry_price) * shares
        pnl_pct = (
            (exit_price - entry_price) / entry_price * 100
            if entry_price > 0 else 0.0
        )
        status = "WIN" if pnl_usd > 0 else "LOSS"

        trade_updates = {
            "exit_price":    float(exit_price),
            "pnl_usd":       round(float(pnl_usd), 4),
            "pnl_pct":       round(float(pnl_pct), 4),
            "status":        status,
            "closed_at":     datetime.now(timezone.utc).isoformat(),
            "error_message": exit_reason,
        }
        db.update_trade(trade_id, trade_updates)

        # ── Telegram alert ────────────────────────────────────────────────
        if status == "WIN":
            await telegram.trade_won(
                state.bot_id, entry_price, exit_price, pnl_usd, pnl_pct
            )
        else:
            await telegram.trade_lost(
                state.bot_id, entry_price, exit_price, pnl_usd, pnl_pct
            )

        if state.broadcast:
            await state.broadcast({
                "type":  "trade_closed",
                "trade": {**trade_updates, "id": trade_id},
            })

        _status(
            state,
            f"EXIT {exit_reason} | {side} | entry={entry_price:.4f} "
            f"exit={exit_price:.4f} | pnl={pnl_usd:+.4f} USD ({pnl_pct:+.2f}%)",
        )
        logger.info(
            "Trade closed — id=%s reason=%s exit=%.4f pnl=%.4f",
            trade_id, exit_reason, exit_price, pnl_usd,
        )

        # ── Reset position state ──────────────────────────────────────────
        state.in_position = False
        state.entry_fired = False
        state.exit_fired  = False
        state.trade_id    = ""
        state.side        = ""
        state.token_to_buy = ""
        state.entry_price  = 0.0
        state.shares       = 0.0
        state.target_price = 0.0
        state.stop_price   = 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_token_ids(market: Dict[str, Any]) -> tuple[str, str]:
    """
    Return (up_token_id, down_token_id) from a market dict.
    Tries the tokens array first; falls back to clobTokenIds.
    """
    tokens        = market.get("tokens", [])
    up_token_id   = ""
    down_token_id = ""

    for tok in tokens:
        outcome = (tok.get("outcome") or tok.get("name", "")).upper()
        if "UP" in outcome or "YES" in outcome:
            up_token_id = tok.get("token_id", "")
        elif "DOWN" in outcome or "NO" in outcome:
            down_token_id = tok.get("token_id", "")

    if not up_token_id or not down_token_id:
        raw = market.get("clobTokenIds", "[]")
        try:
            ids = json.loads(raw) if isinstance(raw, str) else raw
            if len(ids) >= 2:
                up_token_id   = ids[0]
                down_token_id = ids[1]
        except Exception:
            pass

    return up_token_id, down_token_id


def _parse_outcome_prices(
    market: Dict[str, Any],
) -> tuple[float, float, bool]:
    """
    Parse outcomePrices from a market dict.
    Returns (up_price, down_price, success_bool).
    """
    try:
        raw = market.get("outcomePrices", "[]")
        prices = json.loads(raw) if isinstance(raw, str) else raw
        if len(prices) >= 2:
            up   = float(prices[0])
            down = float(prices[1])
            if up == 0.0 and down == 0.0:
                return 0.0, 0.0, False
            return up, down, True
    except Exception:
        pass
    return 0.0, 0.0, False


def _seconds_remaining(end_date_str: str) -> float:
    """
    Compute seconds until market expiry from an ISO datetime string.
    Returns 0.0 if unparseable or already expired.
    """
    if not end_date_str:
        return 0.0
    try:
        end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        return max((end_dt - datetime.now(timezone.utc)).total_seconds(), 0.0)
    except Exception:
        return 0.0


def _status(state: BotState, msg: str) -> None:
    """Fire the optional status_update callback (non-blocking)."""
    if state.status_update:
        try:
            state.status_update(msg, state.round_num)
        except Exception:
            pass


async def _interruptible_sleep(seconds: float, stop_event: asyncio.Event) -> None:
    """
    Sleep for `seconds` but wake up immediately if stop_event is set.
    Checks every 2 s so the bot is responsive to shutdown signals.
    """
    elapsed = 0.0
    while elapsed < seconds and not stop_event.is_set():
        await asyncio.sleep(min(2.0, seconds - elapsed))
        elapsed += 2.0