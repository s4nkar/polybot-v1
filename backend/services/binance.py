"""
Polybot — Binance service: BTC spot price, kline data, and signal-score calculation.

Signal-score weights (from PRD):
  BTC gap       0.40
  Candle mom.   0.25
  Odds value    0.25
  Time remain.  0.10
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

BINANCE_TICKER_URL = "/api/v3/ticker/price"
BINANCE_KLINES_URL = "/api/v3/klines"


async def get_btc_price() -> float:
    """Return the current BTC/USDT spot price from Binance."""
    url = f"{settings.BINANCE_BASE_URL}{BINANCE_TICKER_URL}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"symbol": "BTCUSDT"})
            resp.raise_for_status()
            data = resp.json()
            price = float(data["price"])
            logger.debug("Binance BTC price: %.2f", price)
            return price
    except Exception as exc:
        logger.error("Binance get_btc_price error: %s", exc)
        raise


async def get_klines(
    interval: str = "1m",
    limit: int = 5,
    symbol: str = "BTCUSDT",
) -> List[Dict[str, Any]]:
    """
    Return recent OHLCV candles.

    Each dict contains: open, high, low, close, volume, close_time.
    """
    url = f"{settings.BINANCE_BASE_URL}{BINANCE_KLINES_URL}"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            raw = resp.json()

        candles: List[Dict[str, Any]] = []
        for k in raw:
            candles.append({
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
            })
        return candles
    except Exception as exc:
        logger.error("Binance get_klines error: %s", exc)
        return []


def calculate_signal_score(
    market_data: Dict[str, Any],
    btc_data: Dict[str, Any],
) -> float:
    """
    Compute a 0.0 – 1.0 signal score for a potential Bot 1 entry.

    *market_data* must contain:
        best_bid, best_ask, seconds_remaining

    *btc_data* must contain:
        current_price, klines (list of candle dicts)

    Weights:
        btc_gap_score      0.40
        candle_momentum     0.25
        odds_value          0.25
        time_remaining      0.10
    """

    # 1. BTC gap score — how far price deviates from round number
    current_price: float = btc_data.get("current_price", 0.0)
    if current_price > 0:
        round_price = round(current_price / 100) * 100
        gap_pct = abs(current_price - round_price) / current_price
        btc_gap_score = min(gap_pct * 10, 1.0)  # normalize: 0.1% gap → 1.0
    else:
        btc_gap_score = 0.0

    # 2. Candle momentum — average close > open ratio of recent candles
    klines: List[Dict[str, Any]] = btc_data.get("klines", [])
    if klines:
        bullish_count = sum(1 for c in klines if c["close"] > c["open"])
        candle_momentum = bullish_count / len(klines)
    else:
        candle_momentum = 0.5

    # 3. Odds value — cheaper asks = better value
    best_ask: float = market_data.get("best_ask", 1.0)
    odds_value = max(0.0, 1.0 - best_ask)  # ask of 0.30 → 0.70 score

    # 4. Time remaining — more time = better
    seconds_remaining: float = market_data.get("seconds_remaining", 0)
    time_score = min(seconds_remaining / 300, 1.0)  # 300 s window → 1.0

    # Weighted sum
    score = (
        btc_gap_score * 0.40
        + candle_momentum * 0.25
        + odds_value * 0.25
        + time_score * 0.10
    )

    score = round(min(max(score, 0.0), 1.0), 4)
    logger.info(
        "Signal score %.4f  (gap=%.2f, mom=%.2f, odds=%.2f, time=%.2f)",
        score, btc_gap_score, candle_momentum, odds_value, time_score,
    )
    return score
