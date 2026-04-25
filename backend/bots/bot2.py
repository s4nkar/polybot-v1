"""
Polybot — Bot 2: Hold to Resolution.

Strategy
--------
  1. Scan for active 5-min BTC market once per minute (scanner loop).
  2. Validate market is not resolved and has enough time remaining.
  3. Get BTC price from Chainlink.
  4. Check gap % against nearest $100 round number — must exceed min_gap_pct.
  5. Check best_ask odds — must be ≤ max_entry_price.
  6. Place BUY order.
  7. Sleep until market window closes (end_date).
  8. Poll get_market_outcome() for the resolved outcome price.
  9. Calculate P&L, update DB, send Telegram alert.
  Repeat until stop_event is set or max_rounds reached.

IMPORTANT:
  - Uses Chainlink for BTC price, not Binance.
  - Never places a sell order under any circumstances.
  - P&L: WIN  = (1.00 - entry_price) × shares
         LOSS = -(entry_price × shares)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from db import supabase as db
from models.schemas import Bot2Params
from services import chainlink, polymarket_v2 as polymarket, telegram

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
    bot_id    = "bot2"
    round_num = 0

    await telegram.bot_started(bot_id, dry_run, params.model_dump())
    logger.info("Bot2 started — session=%s dry_run=%s", session_id, dry_run)

    last_telegram_skip = 0.0

    async def maybe_skip(reason: str) -> None:
        nonlocal last_telegram_skip
        import time
        ts = time.time()
        if ts - last_telegram_skip > 60:
            await telegram.trade_skipped(bot_id, reason)
            last_telegram_skip = ts
        logger.warning("Bot2 skip: %s", reason)

    while not stop_event.is_set():

        if params.max_rounds and round_num >= params.max_rounds:
            logger.info("Bot2 reached max_rounds=%d — stopping.", params.max_rounds)
            break

        _status(status_update, f"Scanning for active market… (round {round_num + 1})", round_num)

        # ── Step 1: Discover the active market ────────────────────────────────
        try:
            markets = await polymarket.get_active_markets(params.market_slug)
        except Exception as exc:
            logger.error("Market scan error: %s", exc)
            await _interruptible_sleep(10, stop_event)
            continue

        if not markets:
            await maybe_skip("No active markets found")
            _status(status_update, "No active market — retrying in 15 s", round_num)
            await _interruptible_sleep(15, stop_event)
            continue

        market    = markets[0]
        market_id = market.get("condition_id", market.get("id", ""))

        # ── Step 2: Extract token IDs ──────────────────────────────────────────
        up_token_id, down_token_id = _extract_token_ids(market)

        if not up_token_id or not down_token_id:
            await maybe_skip(f"Could not extract token IDs from market {market_id}")
            await _interruptible_sleep(10, stop_event)
            continue

        # ── Step 3: Validate outcomePrices (skip resolved markets) ────────────
        up_price, down_price, prices_ok = _parse_outcome_prices(market)

        if prices_ok and (up_price >= 0.99 or up_price <= 0.01 or down_price >= 0.99 or down_price <= 0.01):
            await maybe_skip(
                f"Market looks resolved (UP={up_price:.4f} DOWN={down_price:.4f})"
            )
            await _interruptible_sleep(10, stop_event)
            continue

        # ── Step 4: Validate time remaining ───────────────────────────────────
        seconds_remaining = market.get("seconds_remaining", 0.0)

        # Need at least 60 s to enter — otherwise resolution could come before
        # the order even settles.
        if seconds_remaining < 60:
            msg = (
                f"Market window too short ({seconds_remaining:.0f}s remaining, "
                f"need 60s) — waiting for next window"
            )
            logger.warning(msg)
            _status(status_update, msg, round_num)
            await _interruptible_sleep(max(5, int(seconds_remaining) + 5), stop_event)
            continue

        # ── Step 5: Get BTC price from Chainlink ──────────────────────────────
        try:
            btc_price = await chainlink.get_btc_price()
        except Exception as exc:
            logger.error("Chainlink price error: %s", exc)
            _status(status_update, "Chainlink error — retrying in 5 s", round_num)
            await telegram.api_error(bot_id, "chainlink", str(exc))
            await _interruptible_sleep(5, stop_event)
            continue

        # ── Step 6: Calculate gap % ───────────────────────────────────────────
        # Round to nearest $1000 — gives a max gap of ~$500 (~0.5% at $95k BTC),
        # which is a workable range for the min_gap_pct filter.
        round_price = round(btc_price / 1000) * 1000
        gap_abs     = abs(btc_price - round_price)
        gap_pct     = (gap_abs / btc_price) * 100 if btc_price > 0 else 0.0

        logger.warning(
            "Bot2 gap check — BTC=%.2f round=%.0f gap=%.4f%% min=%.4f%%",
            btc_price, round_price, gap_pct, params.min_gap_pct,
        )

        if gap_pct < params.min_gap_pct:
            reason = f"Gap {gap_pct:.4f}% < min {params.min_gap_pct}%"
            await maybe_skip(reason)
            _status(status_update, f"Skipped — {reason}", round_num)
            await _interruptible_sleep(5, stop_event)
            continue

        side         = "UP" if btc_price > round_price else "DOWN"
        token_to_buy = up_token_id if side == "UP" else down_token_id

        # ── Step 7: Check odds / entry price ──────────────────────────────────
        try:
            order_book = await polymarket.get_orderbook(token_to_buy)
        except Exception as exc:
            logger.error("Orderbook fetch error: %s", exc)
            await _interruptible_sleep(5, stop_event)
            continue

        entry_price = order_book["best_ask"]

        logger.warning(
            "Bot2 entry check — side=%s ask=%.4f max=%.4f",
            side, entry_price, params.max_entry_price,
        )

        if entry_price <= 0 or entry_price > params.max_entry_price:
            reason = f"Entry price {entry_price:.4f} exceeds max {params.max_entry_price}"
            await maybe_skip(reason)
            await _interruptible_sleep(5, stop_event)
            continue

        shares = round(params.amount_usd / entry_price, 4)

        # ── Step 8: Place BUY order ────────────────────────────────────────────
        logger.info("Placing BUY order — token=%s price=%.4f", token_to_buy, entry_price)
        order_result = await polymarket.place_order(
            side="BUY",
            amount=params.amount_usd,
            price=entry_price,
            token_id=token_to_buy,
            dry_run=dry_run,
        )

        round_num += 1
        trade_id  = str(uuid.uuid4())
        now       = datetime.now(timezone.utc).isoformat()

        trade_record = {
            "id":              trade_id,
            "session_id":      session_id,
            "bot_id":          bot_id,
            "market_id":       market_id,
            "market_slug":     params.market_slug,
            "side":            side,
            "entry_price":     float(entry_price),
            "shares":          float(shares),
            "amount_usd":      float(params.amount_usd),
            "signal_score":    None,
            "order_id":        order_result.get("order_id", ""),
            "token_id":        token_to_buy,
            "btc_price_entry": float(btc_price),
            "dry_run":         dry_run,
            "trading_mode":    trading_mode,
            "status":          "OPEN",
            "opened_at":       now,
            "created_at":      now,
            "updated_at":      now,
        }

        try:
            db.insert_trade(trade_record)
        except Exception as db_exc:
            logger.error("DB insert failed: %s", db_exc)

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

        _status(
            status_update,
            f"ENTERED {side} @ {entry_price:.4f} | BTC={btc_price:.0f} gap={gap_pct:.3f}% | "
            f"waiting {seconds_remaining:.0f}s for resolution…",
            round_num,
        )
        logger.info(
            "Trade opened — id=%s side=%s entry=%.4f BTC=%.2f gap=%.4f%%",
            trade_id, side, entry_price, btc_price, gap_pct,
        )

        # ── Step 9: Wait for resolution ────────────────────────────────────────
        resolution_price: Optional[float] = None

        if dry_run:
            import random
            # In dry-run cap wait to 30 s so testing stays fast.
            wait_secs = min(seconds_remaining, 30.0)
            await _interruptible_sleep(wait_secs, stop_event)
            win_prob         = 1.0 - entry_price  # cheaper entry → higher win prob
            resolution_price = 1.0 if random.random() < win_prob else 0.0
        else:
            # Sleep until the market window closes, then poll for outcome.
            secs_to_wait = max(seconds_remaining + 5, 5.0)
            logger.info("Bot2 waiting %.0fs for market to close…", secs_to_wait)
            _status(status_update, f"Waiting {secs_to_wait:.0f}s for market to close…", round_num)
            await _interruptible_sleep(secs_to_wait, stop_event)

            if not stop_event.is_set():
                # Poll get_market_outcome up to 60 s post-close for settlement.
                for attempt in range(12):
                    try:
                        outcome = await polymarket.get_market_outcome(market_id, side)
                        if outcome >= 0.99:
                            resolution_price = 1.0
                            break
                        elif outcome <= 0.01:
                            resolution_price = 0.0
                            break
                        logger.info(
                            "Bot2 outcome not yet settled (%.4f) — retry %d/12",
                            outcome, attempt + 1,
                        )
                    except Exception as exc:
                        logger.warning("get_market_outcome error: %s", exc)
                    await _interruptible_sleep(5, stop_event)
                    if stop_event.is_set():
                        break

                # Fallback: read orderbook — resolved markets show bid near 0 or 1.
                if resolution_price is None and not stop_event.is_set():
                    try:
                        ob        = await polymarket.get_orderbook(token_to_buy)
                        final_bid = ob.get("best_bid", 0.0)
                        resolution_price = 1.0 if final_bid > 0.5 else 0.0
                        logger.info(
                            "Bot2 resolution fallback via orderbook: bid=%.4f → %.1f",
                            final_bid, resolution_price,
                        )
                    except Exception:
                        resolution_price = 0.0

        if resolution_price is None:
            resolution_price = 0.0
            logger.info("Bot2 stopped before resolution — treating as loss")

        # ── Step 10: Calculate P&L ────────────────────────────────────────────
        if resolution_price >= 0.5:
            pnl_usd    = (1.0 - entry_price) * shares
            exit_price = 1.0
            status     = "WIN"
        else:
            pnl_usd    = -(entry_price * shares)
            exit_price = 0.0
            status     = "LOSS"

        pnl_pct = (pnl_usd / params.amount_usd * 100) if params.amount_usd > 0 else 0.0

        btc_price_exit = 0.0
        try:
            btc_price_exit = await chainlink.get_btc_price()
        except Exception:
            pass

        trade_updates = {
            "exit_price":     float(exit_price),
            "pnl_usd":        round(float(pnl_usd), 4),
            "pnl_pct":        round(float(pnl_pct), 4),
            "status":         status,
            "btc_price_exit": float(btc_price_exit),
            "closed_at":      datetime.now(timezone.utc).isoformat(),
        }
        try:
            db.update_trade(trade_id, trade_updates)
        except Exception as db_exc:
            logger.error("DB update failed: %s", db_exc)

        # ── Step 11: Telegram alert ────────────────────────────────────────────
        if status == "WIN":
            await telegram.trade_won(bot_id, entry_price, exit_price, pnl_usd, pnl_pct)
        else:
            await telegram.trade_lost(bot_id, entry_price, exit_price, pnl_usd, pnl_pct)

        if broadcast:
            await broadcast({"type": "trade_closed", "trade": {**trade_record, **trade_updates}})

        _status(
            status_update,
            f"EXIT {status} | {side} | entry={entry_price:.4f} "
            f"pnl={pnl_usd:+.4f} USD ({pnl_pct:+.2f}%)",
            round_num,
        )
        logger.info("Trade closed — id=%s status=%s pnl=%.4f", trade_id, status, pnl_usd)

        # Brief pause before scanning for the next window.
        await _interruptible_sleep(5, stop_event)

    # ── Session complete ───────────────────────────────────────────────────────
    session_trades = db.get_session_trades(session_id)
    total_pnl      = sum(float(t.get("pnl_usd", 0) or 0) for t in session_trades)
    await telegram.bot_stopped(bot_id, len(session_trades), total_pnl)
    logger.info(
        "Bot2 stopped — session=%s trades=%d pnl=%.4f",
        session_id, len(session_trades), total_pnl,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_token_ids(market: Dict[str, Any]) -> tuple[str, str]:
    """Return (up_token_id, down_token_id) from a market dict."""
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


def _parse_outcome_prices(market: Dict[str, Any]) -> tuple[float, float, bool]:
    """Parse outcomePrices. Returns (up_price, down_price, success_bool)."""
    try:
        raw    = market.get("outcomePrices", "[]")
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


def _status(cb: Optional[Callable], msg: str, round_num: int) -> None:
    """Fire the optional status_update callback (non-blocking)."""
    if cb:
        try:
            cb(msg, round_num)
        except Exception:
            pass


async def _interruptible_sleep(seconds: float, stop_event: asyncio.Event) -> None:
    """Sleep for `seconds` but wake immediately if stop_event fires."""
    elapsed = 0.0
    while elapsed < seconds and not stop_event.is_set():
        await asyncio.sleep(min(2.0, seconds - elapsed))
        elapsed += 2.0
