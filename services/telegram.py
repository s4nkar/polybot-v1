"""
Polybot — Telegram alert service.

Every function is fire-and-forget: failures are logged but never block
the calling bot loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# telegram package imported lazily in _get_bot()
_Bot = None
_TelegramError = None

_bot = None


def _get_bot():
    global _bot, _Bot, _TelegramError
    if _bot is None:
        if _Bot is None:
            try:
                from telegram import Bot as BotCls
                from telegram.error import TelegramError as TelegramErrorCls
                _Bot = BotCls
                _TelegramError = TelegramErrorCls
            except ImportError:
                logger.warning("python-telegram-bot not installed — Telegram alerts disabled")
                return None
        _bot = _Bot(token=settings.TELEGRAM_BOT_TOKEN)
    return _bot


async def send(message: str) -> None:
    """
    Send *message* to the configured Telegram chat.
    Fire-and-forget — exceptions are swallowed after logging.
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured — skipping message.")
        return
    try:
        bot = _get_bot()
        if bot is None:
            return
        await bot.send_message(
            chat_id=settings.TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("Telegram send error: %s", exc)


# ── Named message helpers ─────────────────────────────────


async def bot_started(bot_id: str, dry_run: bool, params: dict) -> None:
    mode = "🧪 DRY RUN" if dry_run else "🔴 LIVE"
    msg = (
        f"🤖 <b>Polybot {bot_id.upper()} Started</b>\n"
        f"Mode: {mode}\n"
        f"Params: {params}"
    )
    asyncio.create_task(send(msg))


async def trade_opened_bot1(
    side: str, entry_price: float, shares: float,
    amount_usd: float, signal_score: float, market_id: str,
    dry_run: bool,
) -> None:
    mode = "🧪 DRY" if dry_run else "🔴 LIVE"
    msg = (
        f"📈 <b>Bot1 Trade Opened</b> [{mode}]\n"
        f"Side: {side} | Entry: ${entry_price:.4f}\n"
        f"Shares: {shares:.2f} | Amount: ${amount_usd:.2f}\n"
        f"Signal Score: {signal_score:.4f}\n"
        f"Market: <code>{market_id}</code>"
    )
    asyncio.create_task(send(msg))


async def trade_opened_bot2(
    side: str, entry_price: float, shares: float,
    amount_usd: float, gap_pct: float, market_id: str,
    dry_run: bool,
) -> None:
    mode = "🧪 DRY" if dry_run else "🔴 LIVE"
    msg = (
        f"📈 <b>Bot2 Trade Opened</b> [{mode}]\n"
        f"Side: {side} | Entry: ${entry_price:.4f}\n"
        f"Shares: {shares:.2f} | Amount: ${amount_usd:.2f}\n"
        f"BTC Gap: {gap_pct:.4f}%\n"
        f"Market: <code>{market_id}</code>"
    )
    asyncio.create_task(send(msg))


async def trade_won(
    bot_id: str, entry_price: float, exit_price: float,
    pnl_usd: float, pnl_pct: float,
) -> None:
    msg = (
        f"✅ <b>{bot_id.upper()} WIN</b>\n"
        f"Entry: ${entry_price:.4f} → Exit: ${exit_price:.4f}\n"
        f"P&L: ${pnl_usd:+.4f} ({pnl_pct:+.2f}%)"
    )
    asyncio.create_task(send(msg))


async def trade_lost(
    bot_id: str, entry_price: float, exit_price: float,
    pnl_usd: float, pnl_pct: float,
) -> None:
    msg = (
        f"❌ <b>{bot_id.upper()} LOSS</b>\n"
        f"Entry: ${entry_price:.4f} → Exit: ${exit_price:.4f}\n"
        f"P&L: ${pnl_usd:+.4f} ({pnl_pct:+.2f}%)"
    )
    asyncio.create_task(send(msg))


async def trade_skipped(bot_id: str, reason: str) -> None:
    msg = f"⏭️ <b>{bot_id.upper()} Skipped</b>\nReason: {reason}"
    asyncio.create_task(send(msg))


async def bot_stopped(bot_id: str, total_trades: int, pnl_usd: float) -> None:
    msg = (
        f"🛑 <b>Polybot {bot_id.upper()} Stopped</b>\n"
        f"Total trades: {total_trades}\n"
        f"Session P&L: ${pnl_usd:+.4f}"
    )
    asyncio.create_task(send(msg))


async def api_error(bot_id: str, service: str, error: str) -> None:
    msg = (
        f"⚠️ <b>{bot_id.upper()} API Error</b>\n"
        f"Service: {service}\n"
        f"Error: {error}"
    )
    asyncio.create_task(send(msg))
