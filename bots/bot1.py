"""
Polybot — Bot 1: Scalp to Target.

Full execution loop (PRD section 4.2):
  1. Scan for active 5-min BTC windows
  2. Fetch Binance BTC price + klines
  3. Calculate signal score (weighted)
  4. Apply entry filter (score ≥ threshold)
  5. Buy UP or DOWN tokens on Polymarket
  6. Monitor position — poll orderbook every 3 s
  7. Exit at take-profit target
  8. Exit at stop-loss OR < 45 s remaining
  9. Log trade to DB
  10. Send Telegram alert
  Repeat until stop_event is set or max_rounds reached.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from db import supabase as db
from models.schemas import Bot1Params
from services import binance, polymarket, telegram

logger = logging.getLogger(__name__)


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
    Main loop for Bot 1 — Scalp to Target.

    *broadcast* is an optional async callback to push trade updates to
    WebSocket clients.
    """
    bot_id = "bot1"
    round_num = 0

    await telegram.bot_started(bot_id, dry_run, params.model_dump())
    logger.info("Bot1 started — session=%s dry_run=%s", session_id, dry_run)

    while not stop_event.is_set():
        round_num += 1
        if params.max_rounds and round_num > params.max_rounds:
            logger.info("Bot1 reached max_rounds=%d — stopping.", params.max_rounds)
            break

        try:
            # ── Step 1: Scan for active markets ───────────────
            if status_update:
                status_update(f"Round {round_num}: Scanning for active markets…", round_num)
            markets = await polymarket.get_active_markets(params.market_slug)
            if not markets:
                logger.info("No active markets found — waiting 10 s")
                if status_update:
                    status_update(f"Round {round_num}: No active markets found — waiting 10 s", round_num)
                await telegram.trade_skipped(bot_id, "No active markets")
                await asyncio.sleep(10)
                continue

            market = markets[0]  # Pick the nearest upcoming window
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
                # Fallback: use condition_id directly
                up_token_id = market_id
                down_token_id = market_id

            # ── Step 2: Fetch BTC data from Binance ───────────
            btc_price = await binance.get_btc_price()
            klines = await binance.get_klines(interval="1m", limit=5)

            # ── Step 3: Get orderbook + compute signal score ──
            order_book = await polymarket.get_orderbook(up_token_id or market_id)

            # Approximate seconds remaining (default 300 for a 5-min window)
            end_date_str = market.get("end_date_iso", "")
            seconds_remaining = 300.0
            if end_date_str:
                try:
                    end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    seconds_remaining = max((end_dt - datetime.now(timezone.utc)).total_seconds(), 0)
                except Exception:
                    pass

            market_data = {
                "best_bid": order_book["best_bid"],
                "best_ask": order_book["best_ask"],
                "seconds_remaining": seconds_remaining,
            }
            btc_data = {
                "current_price": btc_price,
                "klines": klines,
            }

            signal_score = binance.calculate_signal_score(market_data, btc_data)

            # ── Step 4: Entry filter (optional) ──────────────
            if params.use_score_threshold and signal_score < params.score_threshold:
                reason = f"Signal score {signal_score:.4f} < threshold {params.score_threshold}"
                logger.info("Bot1 skip: %s", reason)
                if status_update:
                    status_update(f"Round {round_num}: Skipped — {reason}", round_num)
                await telegram.trade_skipped(bot_id, reason)
                await asyncio.sleep(5)
                continue

            # Decide side: buy UP if recent candles are bullish, else DOWN
            bullish = sum(1 for c in klines if c["close"] > c["open"])
            side = "UP" if bullish >= len(klines) / 2 else "DOWN"
            token_to_buy = up_token_id if side == "UP" else down_token_id
            entry_price = order_book["best_ask"]

            if entry_price <= 0 or entry_price >= 1:
                await telegram.trade_skipped(bot_id, f"Invalid entry price {entry_price}")
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
                "signal_score": float(signal_score),
                "btc_price_entry": float(btc_price),
                "dry_run": dry_run,
                "trading_mode": trading_mode,
                "status": "OPEN",
                "opened_at": now,
                "created_at": now,
                "updated_at": now,
            }
            db.insert_trade(trade_record)

            await telegram.trade_opened_bot1(
                side=side,
                entry_price=entry_price,
                shares=shares,
                amount_usd=params.amount_usd,
                signal_score=signal_score,
                market_id=market_id,
                dry_run=dry_run,
            )

            if broadcast:
                await broadcast({"type": "trade_opened", "trade": trade_record})

            if status_update:
                status_update(f"Round {round_num}: Trade opened — {side} @ ${entry_price:.4f}", round_num)

            # ── Step 6–8: Monitor position ────────────────────
            target_price = entry_price * (1 + params.target_profit_pct / 100)
            stop_price = entry_price * (1 - params.stop_loss_pct / 100)

            exit_price: Optional[float] = None
            exit_reason = ""

            while not stop_event.is_set():
                await asyncio.sleep(3)  # poll every 3 seconds

                try:
                    ob = await polymarket.get_orderbook(token_to_buy)
                    current_price = ob["best_bid"]
                except Exception as exc:
                    logger.warning("Orderbook poll error: %s", exc)
                    continue

                # Recalculate seconds remaining
                if end_date_str:
                    try:
                        end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                        seconds_remaining = max(
                            (end_dt - datetime.now(timezone.utc)).total_seconds(), 0
                        )
                    except Exception:
                        seconds_remaining -= 3

                # Win — take profit
                if current_price >= target_price:
                    exit_price = current_price
                    exit_reason = "TARGET_HIT"
                    break

                # Loss — stop loss
                if current_price <= stop_price:
                    exit_price = current_price
                    exit_reason = "STOP_LOSS"
                    break

                # Loss — time stop
                if seconds_remaining < params.time_stop_seconds:
                    exit_price = current_price
                    exit_reason = "TIME_STOP"
                    break

            # If stopped mid-monitor, use last known price
            if exit_price is None:
                try:
                    ob = await polymarket.get_orderbook(token_to_buy)
                    exit_price = ob["best_bid"]
                except Exception:
                    exit_price = entry_price  # fallback
                exit_reason = "BOT_STOPPED"

            # ── Step 9: Calculate P&L and log ─────────────────
            pnl_usd = (exit_price - entry_price) * shares
            pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
            status = "WIN" if pnl_usd > 0 else "LOSS"

            btc_price_exit = 0.0
            try:
                btc_price_exit = await binance.get_btc_price()
            except Exception:
                pass

            trade_updates = {
                "exit_price": float(exit_price),
                "pnl_usd": round(float(pnl_usd), 4),
                "pnl_pct": round(float(pnl_pct), 4),
                "status": status,
                "btc_price_exit": float(btc_price_exit),
                "closed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": exit_reason,
            }
            db.update_trade(trade_id, trade_updates)

            # Sell order on exit (only if not dry_run and we have tokens)
            if not dry_run and exit_reason != "BOT_STOPPED":
                await polymarket.place_order(
                    side="SELL",
                    amount=shares * exit_price,
                    price=exit_price,
                    token_id=token_to_buy,
                    dry_run=False,
                )

            # ── Step 10: Telegram alert ───────────────────────
            if status == "WIN":
                await telegram.trade_won(bot_id, entry_price, exit_price, pnl_usd, pnl_pct)
            else:
                await telegram.trade_lost(bot_id, entry_price, exit_price, pnl_usd, pnl_pct)

            if broadcast:
                trade_record.update(trade_updates)
                await broadcast({"type": "trade_closed", "trade": trade_record})

            # Wait 5 minutes before next trade round
            if status_update:
                status_update(f"Round {round_num}: Waiting 5 min before next round…", round_num)
            logger.info("Bot1 waiting 5 min before next round…")
            for _ in range(60):  # 60 × 5s = 300s, checking stop_event every 5s
                if stop_event.is_set():
                    break
                await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info("Bot1 task cancelled.")
            break
        except Exception as exc:
            logger.error("Bot1 loop error: %s", exc)
            await telegram.api_error(bot_id, "bot1_loop", str(exc))
            await asyncio.sleep(5)

    # ── Session complete ──────────────────────────────────
    session_trades = db.get_session_trades(session_id)
    total_pnl = sum(float(t.get("pnl_usd", 0) or 0) for t in session_trades)
    await telegram.bot_stopped(bot_id, len(session_trades), total_pnl)
    logger.info("Bot1 stopped — session=%s trades=%d pnl=%.4f", session_id, len(session_trades), total_pnl)
