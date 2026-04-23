"""
Polybot — Polymarket service (FIXED VERSION).

Responsibilities:
  - Market discovery via Gamma REST API
  - Orderbook snapshots via CLOB REST API
  - Live price streaming via CLOB WebSocket
  - Order placement via py-clob-client SDK
  - Post-resolution outcome fetching

WebSocket endpoint:
  wss://ws-subscriptions-clob.polymarket.com/ws/market

  Subscribe message (send immediately after connect):
    {"assets_ids": ["<token_id>"], "type": "market"}

  Incoming message types handled:
    "book"         — full orderbook snapshot (bids + asks arrays)
    "price_change" — lightweight last-trade tick (price field)

FIXED: Prioritize book snapshots with real bid/ask over lightweight ticks
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger("services.polymarket")
logger.setLevel(logging.DEBUG)

# ── Lazy imports for live trading ─────────────────────────────────────────────

ClobClient = None
OrderArgs  = None
OrderType  = None

_clob_client = None


def _get_clob_client():
    """
    Lazily initialise the CLOB client.

    B5 fix: wraps init in a TypeError fallback for older py_clob_client
    versions that do not accept the `funder` keyword argument.
    """
    global _clob_client, ClobClient, OrderArgs, OrderType

    if _clob_client is None:
        if ClobClient is None:
            from py_clob_client.client import ClobClient as _CC
            from py_clob_client.clob_types import (
                OrderArgs as _OA,
                OrderType as _OT,
            )
            ClobClient = _CC
            OrderArgs  = _OA
            OrderType  = _OT

        try:
            _clob_client = ClobClient(
                host=settings.POLYMARKET_CLOB_API_URL,
                key=settings.POLYMARKET_PRIVATE_KEY,
                chain_id=settings.POLYMARKET_CHAIN_ID,
                funder=settings.POLYMARKET_WALLET_ADDRESS,
            )
        except TypeError:
            logger.warning(
                "py_clob_client does not accept 'funder' — initialising without it."
            )
            _clob_client = ClobClient(
                host=settings.POLYMARKET_CLOB_API_URL,
                key=settings.POLYMARKET_PRIVATE_KEY,
                chain_id=settings.POLYMARKET_CHAIN_ID,
            )

        try:
            _clob_client.set_api_creds(_clob_client.create_or_derive_api_creds())
        except Exception as exc:
            logger.warning("Could not derive CLOB API creds: %s", exc)

    return _clob_client


# ── Market discovery ──────────────────────────────────────────────────────────


async def get_active_markets(market_slug: str) -> List[Dict[str, Any]]:
    """
    Fetch active BTC 5-minute windows from the Polymarket Gamma API.

    Slug format: btc-updown-5m-{unix_timestamp}

    B1 fix: inner datetime variable renamed to `utc_now` (no float shadowing).
    B6 fix: both floor (current window) and ceil (next window) timestamps
            tried so boundary moments are never missed.

    Returns a list of enriched market dicts with timing fields attached.
    """
    now_ts         = time.time()
    window_seconds = 300

    floor_window = int(math.floor(now_ts / window_seconds) * window_seconds)
    ceil_window  = int(math.ceil(now_ts  / window_seconds) * window_seconds)

    timestamps_to_try = [
        floor_window,
        ceil_window,
        floor_window - window_seconds,
    ]

    # De-duplicate while preserving order.
    seen: set = set()
    unique_ts: List[int] = []
    for ts in timestamps_to_try:
        if ts not in seen:
            seen.add(ts)
            unique_ts.append(ts)

    base_url = settings.POLYMARKET_GAMMA_API_URL.rstrip("/")

    for ts in unique_ts:
        slug   = f"{market_slug}-{ts}"
        url    = f"{base_url}/events"
        params = {"slug": slug}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            events: List[Dict[str, Any]] = (
                data   if isinstance(data, list) else
                [data] if isinstance(data, dict) else
                []
            )
            if not events:
                continue

            all_markets: List[Dict[str, Any]] = []

            for event in events:
                event_end      = event.get("endDate", "")
                event_start    = event.get("startTime", "")
                clob_token_ids = event.get("clobTokenIds", [])
                event_markets  = event.get("markets", [])

                if not isinstance(event_markets, list):
                    event_markets = []

                for em in event_markets:
                    if not em.get("endDate"):
                        em["endDate"] = event_end
                    if not em.get("eventStartTime") and not em.get("startTime"):
                        em["eventStartTime"] = event_start

                    # B4 fix: only propagate event-level token IDs when
                    # there is exactly one child market.
                    if (
                        not em.get("clobTokenIds")
                        and clob_token_ids
                        and len(event_markets) == 1
                    ):
                        em["clobTokenIds"] = clob_token_ids

                all_markets.extend(event_markets)

                if event.get("condition_id") and not event_markets:
                    all_markets.append(event)

            valid_markets: List[Dict[str, Any]] = []

            for mkt in all_markets:
                if not mkt.get("acceptingOrders", False):
                    logger.debug("Skipping — acceptingOrders False")
                    continue
                if not mkt.get("active", False):
                    logger.debug("Skipping — active False")
                    continue
                if mkt.get("closed", True):
                    logger.debug("Skipping — closed True")
                    continue

                end_str   = mkt.get("endDate", "")
                start_str = (
                    mkt.get("eventStartTime", "") or mkt.get("startTime", "")
                )

                if not end_str:
                    logger.debug("Skipping — no endDate")
                    continue

                try:
                    utc_now  = datetime.now(timezone.utc)   # B1 fix
                    end_dt   = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                    secs_rem = max((end_dt - utc_now).total_seconds(), 0)

                    if start_str:
                        start_dt   = datetime.fromisoformat(
                            start_str.replace("Z", "+00:00")
                        )
                        elapsed    = max((utc_now - start_dt).total_seconds(), 0)
                        window_dur = (end_dt - start_dt).total_seconds()
                    else:
                        window_dur = 300.0
                        elapsed    = max(window_dur - secs_rem, 0)

                    mkt["seconds_remaining"] = secs_rem
                    mkt["elapsed"]           = elapsed
                    mkt["window_duration"]   = window_dur

                except Exception as exc:
                    logger.debug("Timing parse error: %s", exc)
                    continue

                valid_markets.append(mkt)

            if valid_markets:
                return valid_markets

        except Exception as exc:
            logger.warning(
                "get_active_markets error for slug '%s': %s", slug, exc
            )
            continue

    logger.info("No active markets found for '%s'", market_slug)
    return []


# ── Orderbook REST snapshot ───────────────────────────────────────────────────


async def get_orderbook(token_id: str) -> Dict[str, Any]:
    """
    Fetch a single orderbook snapshot for a token via REST.

    B3 fix: Polymarket returns bids ascending (lowest first).
            best_bid = bids[-1] (highest bid = best price to sell at).
            best_ask = asks[0]  (lowest ask  = best price to buy at).

    Used for:
      - Confirming exact entry price before placing a BUY.
      - Snapshotting best_bid at time-stop (SELL at best available price).
      - BOT_STOPPED fallback price.
    """
    logger.info("STREAM_ORDERBOOK_V3_LOADED")
    url    = f"{settings.POLYMARKET_CLOB_API_URL}/book"
    params = {"token_id": token_id}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        bids = data.get("bids", [])
        asks = data.get("asks", [])

        best_bid = float(bids[-1]["price"]) if bids else 0.0  # B3 fix
        best_ask = float(asks[0]["price"])  if asks else 0.0

        return {
            "bids":     bids,
            "asks":     asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
        }

    except Exception as exc:
        logger.error("get_orderbook error for %s: %s", token_id, exc)
        return {"bids": [], "asks": [], "best_bid": 0.0, "best_ask": 0.0}


# ── WebSocket live price stream ───────────────────────────────────────────────


async def stream_orderbook(
    token_id: str,
    on_price: Callable[[float, float], None],
    stop_event: asyncio.Event,
    reconnect_delay: float = 2.0,
) -> None:
    """
    Stream live orderbook updates via Polymarket CLOB WebSocket.

    FIXED: Prioritizes book snapshots with real bid/ask over lightweight ticks.
    
    Message types received:
      1. Book snapshot: {"bids": [...], "asks": [...], ...}
         → Extract best_bid/best_ask for accurate entry/exit
      
      2. Price changes: {"price_changes": [{"asset_id": "...", "price": "0.52"}]}
         → Lightweight ticks, use as fallback
      
      3. Last trade: {"event_type": "last_trade_price", "price": "0.52"}
         → Single trade, use as fallback
    
    Requires raw text "PING" every 10s to keep stream alive.
    """
    try:
        import websockets
    except ImportError:
        logger.error("websockets not installed. Run: pip install websockets")
        return

    ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    subscribe_msg = json.dumps({
        "assets_ids": [token_id],
        "type":       "market",
    })

    logger.info("WS stream starting — token_id=%s", token_id)

    while not stop_event.is_set():
        try:
            async with websockets.connect(
                ws_url,
                ping_interval=None,
                ping_timeout=None,
                close_timeout=5,
                open_timeout=10,
            ) as ws:
                await ws.send(subscribe_msg)
                logger.info("WS subscribed — token_id=%s", token_id)
                logger.warning(f"✓ SUBSCRIBED to token {token_id[:20]}...")

                async def _heartbeat():
                    while not stop_event.is_set():
                        await asyncio.sleep(10)
                        try:
                            await ws.send("PING")
                            logger.debug("WS PING — token=%s", token_id[:8])
                        except Exception:
                            break

                heartbeat_task = asyncio.create_task(_heartbeat())

                try:
                    tick_count = 0
                    async for raw in ws:
                        if stop_event.is_set():
                            break
                        tick_count += 1

                        if tick_count <= 3:
                            logger.warning(f"🔴 WS RAW #{tick_count}: {str(raw)[:600]}")

                        # Server echoes "PONG" for our "PING" — skip it
                        if raw == "PONG":
                            continue

                        try:
                            msg = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            continue

                        events = msg if isinstance(msg, list) else [msg]

                        for event in events:
                            # ── BOOK SNAPSHOT (highest priority) ────────────────
                            # Has real bid/ask prices, best for entry/exit decisions
                            if "bids" in event and "asks" in event:
                                bids = event.get("bids", [])
                                asks = event.get("asks", [])
                                try:
                                    best_bid = float(bids[-1]["price"]) if bids else 0.0
                                    # WS sends asks descending (highest first); best ask = last element
                                    best_ask = float(asks[-1]["price"]) if asks else 0.0
                                    if best_bid > 0.0 or best_ask > 0.0:
                                        logger.warning(f"📊 BOOK SNAPSHOT: bid={best_bid:.4f} ask={best_ask:.4f}")
                                        on_price(best_bid, best_ask)
                                except (ValueError, TypeError, KeyError) as e:
                                    logger.debug(f"Book snapshot parse error: {e}")
                                continue

                            # ── PRICE CHANGES (lightweight ticks) ──────────────
                            # Format: {"price_changes": [{"asset_id": "...", "price": "0.52"}]}
                            price_changes = event.get("price_changes")
                            if price_changes:
                                for change in price_changes:
                                    try:
                                        if change.get("asset_id", "") != token_id:
                                            continue
                                        # Prefer real book prices over individual fill price
                                        best_bid = float(change.get("best_bid") or 0)
                                        best_ask = float(change.get("best_ask") or 0)
                                        if best_bid > 0.0 or best_ask > 0.0:
                                            logger.debug(f"💰 price_changes: bid={best_bid:.4f} ask={best_ask:.4f}")
                                            on_price(best_bid, best_ask)
                                    except (ValueError, TypeError) as e:
                                        logger.debug(f"Price change parse error: {e}")
                                continue

                            # ── PRICE CHANGE / LAST TRADE PRICE ──────────────
                            etype = event.get("event_type", event.get("type", ""))
                            if etype in ("last_trade_price", "price_change"):
                                try:
                                    price = float(event.get("price") or 0)
                                    if price > 0.0:
                                        logger.warning(f"💰 TICK {etype}: price={price:.4f}")
                                        on_price(price, price)
                                except (ValueError, TypeError) as e:
                                    logger.debug(f"Price event parse error: {e}")

                finally:
                    heartbeat_task.cancel()
                    logger.warning(f"🔴 WS TICK STOPPED for token {token_id}")
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass

        except asyncio.CancelledError:
            logger.info("WS stream cancelled — token_id=%s", token_id)
            break

        except Exception as exc:
            if stop_event.is_set():
                break
            logger.warning(
                "WS disconnected — token_id=%s: %s — retry in %.0fs",
                token_id, exc, reconnect_delay,
            )
            await asyncio.sleep(reconnect_delay)

    logger.info("WS stream stopped — token_id=%s", token_id)


# ── Order placement ───────────────────────────────────────────────────────────


async def place_order(
    side: str,
    amount: float,
    price: float,
    token_id: str,
    dry_run: bool = True,
    size: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Place a GTC limit order on Polymarket.

    Parameters
    ----------
    side      : "BUY" or "SELL"
    amount    : USD notional — used to derive shares when `size` is None.
    price     : Token price, float 0–1.
    token_id  : Outcome token ID.
    dry_run   : If True, return a simulated result without hitting the API.
    size      : Exact share count.  When set, bypasses amount/price division.
                Always pass this for SELL orders (B2 fix) so the bot trades
                the exact shares it bought rather than a re-derived count.
    """
    if size is not None:
        shares = round(size, 4)
    elif price > 0:
        shares = round(amount / price, 4)
    else:
        shares = 0.0

    order_summary = {
        "side":       side,
        "price":      price,
        "size":       shares,
        "amount_usd": amount,
        "token_id":   token_id,
        "dry_run":    dry_run,
    }

    if dry_run:
        logger.info("[DRY RUN] %s", order_summary)
        return {**order_summary, "order_id": "dry-run-simulated", "status": "SIMULATED"}

    try:
        clob         = _get_clob_client()
        order_args   = OrderArgs(price=price, size=shares, side=side, token_id=token_id)
        signed_order = clob.create_order(order_args)
        result       = clob.post_order(signed_order, OrderType.GTC)

        logger.info("Order placed: %s", result)
        return {
            **order_summary,
            "order_id": result.get("orderID", result.get("id", "unknown")),
            "status":   "PLACED",
            "raw":      result,
        }

    except Exception as exc:
        logger.error("place_order error: %s", exc)
        return {**order_summary, "order_id": None, "status": "ERROR", "error": str(exc)}


# ── Post-resolution outcome ───────────────────────────────────────────────────


async def get_market_outcome(market_id: str, side: str) -> float:
    """
    Fetch the final resolved price for our side after a market closes.
    Returns 1.0 (win), 0.0 (loss), or 0.5 as a neutral fallback on error.
    """
    url = f"{settings.POLYMARKET_GAMMA_API_URL}/markets/{market_id}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        outcome_prices = data.get("outcomePrices", "[]")
        if isinstance(outcome_prices, str):
            outcome_prices = json.loads(outcome_prices)

        up_price   = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.5
        down_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.5
        result     = up_price if side == "UP" else down_price

        logger.info(
            "get_market_outcome — market=%s side=%s UP=%.4f DOWN=%.4f → %.4f",
            market_id, side, up_price, down_price, result,
        )
        return result

    except Exception as exc:
        logger.error("get_market_outcome error: %s", exc)
        return 0.5