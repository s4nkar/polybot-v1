"""
Polybot — Bot 2: Hold to Resolution.

Full execution loop (PRD section 4.3):
  1. Scan for eligible 5-min BTC windows (poll every 5 s)
  2. Get BTC price from Chainlink (NOT Binance)
  3. Check gap % — must exceed min_gap_pct
  4. Check odds — entry price must be ≤ max_entry_price
  5. Buy UP or DOWN tokens
  6. Wait for market resolution (never sell)
  7. Collect payout at resolution
  8. Log trade to DB
  9. Send Telegram alert
  Repeat until stop_event is set or max_rounds reached.

IMPORTANT:
  - Uses Chainlink for BTC price, not Binance.
  - Never places a sell order under any circumstances.
  - P&L: WIN  = (1.00 - entry_price) × shares
         LOSS = -(entry_price × shares)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from db import supabase as db
from models.schemas import Bot2Params
from services import chainlink, polymarket, telegram

logger = logging.getLogger(__name__)


async def run_bot2(
    params: Bot2Params,
    session_id: str,
    dry_run: bool,
    stop_event: asyncio.Event,
    broadcast: Optional[Callable] = None,
    trading_mode: str = "paper",
    status_update: Optional[Callable] = None,
) -> None:
    """
    Main loop for Bot 2 — Hold to Resolution.

    *broadcast* is an optional async callback to push trade updates to
    WebSocket clients.
    """
    bot_id = "bot2"
    round_num = 0

    await telegram.bot_started(bot_id, dry_run, params.model_dump())
    logger.info("Bot2 started — session=%s dry_run=%s", session_id, dry_run)

    while not stop_event.is_set():
        round_num += 1
        if params.max_rounds and round_num > params.max_rounds:
            logger.info("Bot2 reached max_rounds=%d — stopping.", params.max_rounds)
            break

        try:
            # ── Step 1: Scan for active markets ───────────────
            if status_update:
                status_update(f"Round {round_num}: Scanning for active markets…", round_num)
            markets = await polymarket.get_active_markets(params.market_slug)
            if not markets:
                logger.info("Bot2: No active markets — waiting 5 s")
                if status_update:
                    status_update(f"Round {round_num}: No active markets — waiting 5 s", round_num)
                await asyncio.sleep(5)
                continue

            market = markets[0]
            market_id = market.get("condition_id", market.get("id", "unknown"))
            tokens = market.get("tokens", [])

            # Determine UP/DOWN token IDs
            up_token_id = None
            down_token_id = None
            for tok in tokens:
                outcome = (tok.get("outcome") or tok.get("name", "")).upper()
                if "UP" in outcome or "YES" in outcome:
                    up_token_id = tok.get("token_id", "")
                elif "DOWN" in outcome or "NO" in outcome:
                    down_token_id = tok.get("token_id", "")

            if not up_token_id and not down_token_id:
                up_token_id = market_id
                down_token_id = market_id

            # ── Step 2: Get BTC price from Chainlink ──────────
            try:
                btc_price = await chainlink.get_btc_price()
            except Exception as exc:
                logger.error("Chainlink price error: %s", exc)
                if status_update:
                    status_update(f"Round {round_num}: Chainlink error — retrying in 5 s", round_num)
                await telegram.api_error(bot_id, "chainlink", str(exc))
                await asyncio.sleep(5)
                continue

            # ── Step 3: Calculate gap % ───────────────────────
            # Gap relative to the nearest $100 round number
            round_price = round(btc_price / 100) * 100
            gap_abs = abs(btc_price - round_price)
            gap_pct = (gap_abs / btc_price) * 100 if btc_price > 0 else 0.0

            if gap_pct < params.min_gap_pct:
                reason = f"Gap {gap_pct:.4f}% < min {params.min_gap_pct}%"
                logger.info("Bot2 skip: %s", reason)
                if status_update:
                    status_update(f"Round {round_num}: Skipped — {reason}", round_num)
                await telegram.trade_skipped(bot_id, reason)
                await asyncio.sleep(5)
                continue

            # Determine direction from BTC price relative to round
            side = "UP" if btc_price > round_price else "DOWN"
            token_to_buy = up_token_id if side == "UP" else down_token_id

            # ── Step 4: Check odds / entry price ──────────────
            order_book = await polymarket.get_orderbook(token_to_buy)
            entry_price = order_book["best_ask"]

            if entry_price <= 0 or entry_price > params.max_entry_price:
                reason = f"Entry price {entry_price:.4f} exceeds max {params.max_entry_price}"
                logger.info("Bot2 skip: %s", reason)
                await telegram.trade_skipped(bot_id, reason)
                await asyncio.sleep(5)
                continue

            shares = round(params.amount_usd / entry_price, 4)

            # ── Step 5: Place buy order ───────────────────────
            order_result = await polymarket.place_order(
                side="BUY",
                amount=params.amount_usd,
                price=entry_price,
                token_id=token_to_buy,
                dry_run=dry_run,
            )

            trade_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            trade_record = {
                "id": trade_id,
                "session_id": session_id,
                "bot_id": bot_id,
                "market_id": market_id,
                "market_slug": params.market_slug,
                "side": side,
                "entry_price": float(entry_price),
                "shares": float(shares),
                "amount_usd": float(params.amount_usd),
                "signal_score": None,
                "btc_price_entry": float(btc_price),
                "dry_run": dry_run,
                "trading_mode": trading_mode,
                "status": "OPEN",
                "opened_at": now,
                "created_at": now,
                "updated_at": now,
            }
            db.insert_trade(trade_record)

            await telegram.trade_opened_bot2(
                side=side,
                entry_price=entry_price,
                shares=shares,
                amount_usd=params.amount_usd,
                gap_pct=gap_pct,
                market_id=market_id,
                dry_run=dry_run,
            )

            if broadcast:
                await broadcast({"type": "trade_opened", "trade": trade_record})

            if status_update:
                status_update(f"Round {round_num}: Trade opened — {side} @ ${entry_price:.4f}, waiting for resolution…", round_num)

            # ── Step 6: Wait for resolution ───────────────────
            # Bot 2 holds until market resolves — poll every 5 s
            # In dry-run, simulate waiting 60 s then resolving based on probability.
            resolution_price: Optional[float] = None

            if dry_run:
                # Simulate waiting for resolution
                wait_seconds = 60
                elapsed = 0
                while elapsed < wait_seconds and not stop_event.is_set():
                    await asyncio.sleep(5)
                    elapsed += 5

                # Simulate resolution: if entry_price < 0.5, likely a
                # good-value bet → simulate WIN, else LOSS
                import random
                win_probability = 1.0 - entry_price  # cheaper entry = higher win prob
                won = random.random() < win_probability
                resolution_price = 1.0 if won else 0.0
            else:
                # Live: poll market status until resolved
                while not stop_event.is_set():
                    await asyncio.sleep(5)
                    try:
                        updated_markets = await polymarket.get_active_markets(params.market_slug)
                        # Check if our market is still active
                        still_active = any(
                            m.get("condition_id") == market_id or m.get("id") == market_id
                            for m in updated_markets
                        )
                        if not still_active:
                            # Market resolved — check final price
                            ob = await polymarket.get_orderbook(token_to_buy)
                            final_price = ob.get("best_bid", 0.0)
                            # If price ≈ 1.0 we won, if ≈ 0.0 we lost
                            resolution_price = 1.0 if final_price > 0.5 else 0.0
                            break
                    except Exception as poll_exc:
                        logger.warning("Resolution poll error: %s", poll_exc)

            if resolution_price is None:
                # Bot was stopped before resolution
                resolution_price = 0.0
                logger.info("Bot2 stopped before resolution — treating as loss")

            # ── Step 7–8: Calculate P&L and log ───────────────
            if resolution_price >= 0.5:
                # WIN
                pnl_usd = (1.0 - entry_price) * shares
                exit_price = 1.0
                status = "WIN"
            else:
                # LOSS
                pnl_usd = -(entry_price * shares)
                exit_price = 0.0
                status = "LOSS"

            pnl_pct = (pnl_usd / params.amount_usd * 100) if params.amount_usd > 0 else 0.0

            btc_price_exit = 0.0
            try:
                btc_price_exit = await chainlink.get_btc_price()
            except Exception:
                pass

            trade_updates = {
                "exit_price": float(exit_price),
                "pnl_usd": round(float(pnl_usd), 4),
                "pnl_pct": round(float(pnl_pct), 4),
                "status": status,
                "btc_price_exit": float(btc_price_exit),
                "closed_at": datetime.now(timezone.utc).isoformat(),
            }
            db.update_trade(trade_id, trade_updates)

            # ── Step 9: Telegram alert ────────────────────────
            if status == "WIN":
                await telegram.trade_won(bot_id, entry_price, exit_price, pnl_usd, pnl_pct)
            else:
                await telegram.trade_lost(bot_id, entry_price, exit_price, pnl_usd, pnl_pct)

            if broadcast:
                trade_record.update(trade_updates)
                await broadcast({"type": "trade_closed", "trade": trade_record})

            # Wait 5 minutes before next trade round
            logger.info("Bot2 waiting 5 min before next round…")
            for _ in range(60):  # 60 × 5s = 300s, checking stop_event every 5s
                if stop_event.is_set():
                    break
                await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info("Bot2 task cancelled.")
            break
        except Exception as exc:
            logger.error("Bot2 loop error: %s", exc)
            await telegram.api_error(bot_id, "bot2_loop", str(exc))
            await asyncio.sleep(5)

    # ── Session complete ──────────────────────────────────
    session_trades = db.get_session_trades(session_id)
    total_pnl = sum(float(t.get("pnl_usd", 0) or 0) for t in session_trades)
    await telegram.bot_stopped(bot_id, len(session_trades), total_pnl)
    logger.info("Bot2 stopped — session=%s trades=%d pnl=%.4f", session_id, len(session_trades), total_pnl)
