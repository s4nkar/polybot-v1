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
    Fetch active BTC 5-minute windows matching *market_slug*.

    Returns a list of market dicts, each with at minimum:
      - token_id (condition_id)
      - question
      - end_date_iso
      - outcomes  [{name, token_id, price}]
    """
    url = f"{settings.POLYMARKET_CLOB_API_URL}/markets"
    params: Dict[str, Any] = {"closed": False, "limit": 20}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        # The CLOB API returns a list directly or a wrapper object
        markets_raw: List[Dict[str, Any]] = data if isinstance(data, list) else data.get("data", data.get("markets", []))

        # Filter to the ones whose question / slug contain our target slug
        slug_lower = market_slug.lower()
        matched: List[Dict[str, Any]] = []
        for mkt in markets_raw:
            question = (mkt.get("question") or "").lower()
            condition_id = mkt.get("condition_id", "")
            if slug_lower in question or slug_lower in condition_id.lower():
                matched.append(mkt)

        logger.info("Found %d active markets matching '%s'", len(matched), market_slug)
        return matched
    except Exception as exc:
        logger.error("get_active_markets error: %s", exc)
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
