"""
Polybot — Polymarket service: market discovery, orderbook, and order placement.

Uses the official py-clob-client SDK for order signing and the REST API for
market queries.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# py_clob_client is only needed for live order placement — import lazily
ClobClient = None
OrderArgs = None
OrderType = None

# ── CLOB client singleton ────────────────────────────────

_clob_client: Optional[ClobClient] = None


def _get_clob_client():
    """Lazily initialise the CLOB client — requires a private key."""
    global _clob_client, ClobClient, OrderArgs, OrderType
    if _clob_client is None:
        # Lazy import — only needed for live trading
        if ClobClient is None:
            from py_clob_client.client import ClobClient as _ClobClient
            from py_clob_client.clob_types import OrderArgs as _OrderArgs, OrderType as _OrderType
            ClobClient = _ClobClient
            OrderArgs = _OrderArgs
            OrderType = _OrderType

        _clob_client = ClobClient(
            host=settings.POLYMARKET_CLOB_API_URL,
            key=settings.POLYMARKET_API_KEY,
            chain_id=settings.POLYMARKET_CHAIN_ID,
            funder=settings.POLYMARKET_WALLET_ADDRESS,
            private_key=settings.POLYMARKET_PRIVATE_KEY,
        )
        try:
            _clob_client.set_api_creds(_clob_client.create_or_derive_api_creds())
        except Exception as exc:
            logger.warning("Could not derive CLOB API creds: %s", exc)
    return _clob_client


# ── Public helpers ────────────────────────────────────────


async def get_active_markets(market_slug: str) -> List[Dict[str, Any]]:
    """
    Fetch active BTC 5-minute windows from the Polymarket gamma API.

    Uses the events endpoint with slug format: btc-updown-5m-{unix_timestamp}
    where the timestamp is rounded to the nearest upcoming 5-minute window.

    Returns a list of market dicts from the event.
    """
    import time
    import math

    now = time.time()
    window_seconds = 300  # 5 minutes

    # Compute the current and next few 5-min window timestamps
    current_window = int(math.floor(now / window_seconds) * window_seconds)

    timestamps_to_try = [
    current_window,                         # current window — try first
    current_window - window_seconds,        # just-ended window (edge case)
    current_window + window_seconds,        # upcoming window
    ]

    base_url = settings.POLYMARKET_GAMMA_API_URL.rstrip("/")

    for ts in timestamps_to_try:
        slug = f"{market_slug}-{ts}"
        url = f"{base_url}/events"
        params = {"slug": slug}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            # The gamma events API returns a list of events
            events: List[Dict[str, Any]] = data if isinstance(data, list) else [data] if isinstance(data, dict) else []

            if not events:
                continue

            # Each event contains a "markets" array — extract them
            # Also propagate event-level timing fields to market objects
            all_markets: List[Dict[str, Any]] = []
            for event in events:
                event_end = event.get("endDate", "")
                event_start = event.get("startTime", "")

                event_markets = event.get("markets", [])
                if isinstance(event_markets, list):
                    for em in event_markets:
                        # Market-level fields take priority; fall back
                        # to event-level if missing
                        if not em.get("endDate"):
                            em["endDate"] = event_end
                        if not em.get("eventStartTime") and not em.get("startTime"):
                            em["eventStartTime"] = event_start
                    all_markets.extend(event_markets)
                # Also include the event itself if it has a condition_id
                if event.get("condition_id") and not event_markets:
                    all_markets.append(event)

            # ── Filter markets by state and timing window ──
            from datetime import datetime, timezone

            valid_markets: List[Dict[str, Any]] = []
            for mkt in all_markets:
                # Must be accepting orders, active, and not closed
                if not mkt.get("acceptingOrders", False):
                    logger.debug("Skipping market — acceptingOrders is False")
                    continue
                if not mkt.get("active", False):
                    logger.debug("Skipping market — active is False")
                    continue
                if mkt.get("closed", True):
                    logger.debug("Skipping market — market is closed")
                    continue

                # ── Compute timing from full ISO datetime fields ──
                end_str = mkt.get("endDate", "")
                start_str = (
                    mkt.get("eventStartTime", "")
                    or mkt.get("startTime", "")
                )

                if not end_str:
                    logger.debug("Skipping market — no endDate field")
                    continue

                try:
                    now = datetime.now(timezone.utc)
                    end_dt = datetime.fromisoformat(
                        end_str.replace("Z", "+00:00")
                    )

                    secs_rem = max((end_dt - now).total_seconds(), 0)

                    if start_str:
                        start_dt = datetime.fromisoformat(
                            start_str.replace("Z", "+00:00")
                        )
                        elapsed = max((now - start_dt).total_seconds(), 0)
                        window_dur = (end_dt - start_dt).total_seconds()
                    else:
                        # Fallback: assume 300s window
                        window_dur = 300.0
                        elapsed = max(window_dur - secs_rem, 0)

                    # # Only accept markets mid-window (elapsed 60–270s)
                    # if elapsed < 60 or elapsed > 270:
                    #     logger.debug(
                    #         "Skipping market — elapsed=%.0f outside [60, 270]",
                    #         elapsed,
                    #     )
                    #     continue

                    # Attach computed timing so bot doesn't recalculate
                    mkt["seconds_remaining"] = secs_rem
                    mkt["elapsed"] = elapsed
                    mkt["window_duration"] = window_dur

                except Exception as exc:
                    logger.debug("Could not parse timing for market: %s", exc)
                    continue  # skip unparseable markets

                valid_markets.append(mkt)

            if valid_markets:
                logger.info(
                    "Found %d valid markets (of %d total) for slug '%s' (ts=%d)",
                    len(valid_markets), len(all_markets), slug, ts,
                )
                return valid_markets

        except Exception as exc:
            logger.warning("get_active_markets error for slug '%s': %s", slug, exc)
            continue

    logger.info("No active markets found for '%s' across %d windows", market_slug, len(timestamps_to_try))
    return []


async def get_orderbook(token_id: str) -> Dict[str, Any]:
    """
    Fetch the current orderbook for a token.

    Returns dict with 'bids', 'asks', 'best_bid', 'best_ask' keys.
    Prices are floats between 0 and 1 (e.g. 0.55 = 55 cents).
    """
    url = f"{settings.POLYMARKET_CLOB_API_URL}/book"
    params = {"token_id": token_id}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        bids = data.get("bids", [])
        asks = data.get("asks", [])

        best_bid = float(bids[0]["price"]) if bids else 0.0
        best_ask = float(asks[0]["price"]) if asks else 1.0

        return {
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
        }
    except Exception as exc:
        logger.error("get_orderbook error for %s: %s", token_id, exc)
        return {"bids": [], "asks": [], "best_bid": 0.0, "best_ask": 1.0}


async def place_order(
    side: str,
    amount: float,
    price: float,
    token_id: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Place a limit order on Polymarket.

    *side*:  "BUY" or "SELL"
    *amount*: how many shares (computed as usd_amount / price)
    *price*:  float 0–1
    *token_id*: the specific outcome token id
    *dry_run*: if True, skip the actual API call and return a simulated result.

    Returns a dict with order details or simulated result.
    """
    shares = round(amount / price, 4) if price > 0 else 0.0
    order_summary = {
        "side": side,
        "price": price,
        "size": shares,
        "amount_usd": amount,
        "token_id": token_id,
        "dry_run": dry_run,
    }

    if dry_run:
        logger.info("[DRY RUN] Simulated order: %s", order_summary)
        return {**order_summary, "order_id": "dry-run-simulated", "status": "SIMULATED"}

    try:
        clob = _get_clob_client()

        order_args = OrderArgs(
            price=price,
            size=shares,
            side=side,
            token_id=token_id,
        )

        signed_order = clob.create_order(order_args)
        result = clob.post_order(signed_order, OrderType.GTC)

        logger.info("Order placed: %s", result)
        return {
            **order_summary,
            "order_id": result.get("orderID", result.get("id", "unknown")),
            "status": "PLACED",
            "raw": result,
        }
    except Exception as exc:
        logger.error("place_order error: %s", exc)
        return {**order_summary, "order_id": None, "status": "ERROR", "error": str(exc)}
