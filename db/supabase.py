"""
Polybot — Supabase client and all database operations.

Falls back to an in-memory store when Supabase credentials are not configured,
so the app can run locally without a database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config import settings

logger = logging.getLogger(__name__)

# ── Detect Supabase availability ──────────────────────────

_USE_SUPABASE = bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)

if _USE_SUPABASE:
    try:
        from supabase import create_client, Client
    except ImportError:
        logger.warning("supabase-py not installed — falling back to in-memory DB")
        _USE_SUPABASE = False

# ── Supabase client singleton ────────────────────────────

_client = None


def _get_client():
    global _client
    if _client is None and _USE_SUPABASE:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _client


# ── In-memory fallback store ─────────────────────────────

class _MemoryDB:
    """Simple in-memory store that mimics the Supabase trade/config tables."""

    def __init__(self):
        self.trades: List[Dict[str, Any]] = []
        self.config: Dict[str, Any] = {
            "id": 1,
            "telegram_enabled": True,
            "default_dry_run": True,
            "default_amount_usd": 5.0,
            "environment": "dev",
        }

    def insert_trade(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        self.trades.append(dict(trade_data))
        return trade_data

    def update_trade(self, trade_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        for t in self.trades:
            if t.get("id") == trade_id:
                t.update(updates)
                return t
        return updates

    def get_session_trades(self, session_id: str) -> List[Dict[str, Any]]:
        result = [t for t in self.trades if t.get("session_id") == session_id]
        result.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return result

    def get_all_trades(
        self, limit: int = 50, offset: int = 0, trading_mode: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        filtered = self.trades
        if trading_mode:
            filtered = [t for t in filtered if t.get("trading_mode") == trading_mode]
        filtered.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        total = len(filtered)
        return (filtered[offset : offset + limit], total)

    def get_config(self) -> Dict[str, Any]:
        return dict(self.config)

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        self.config.update(updates)
        return dict(self.config)


_memdb = _MemoryDB()

if not _USE_SUPABASE:
    logger.info("Supabase not configured — using in-memory database (data will not persist across restarts)")


# ── Trade operations ──────────────────────────────────────


def insert_trade(trade_data: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a new trade row and return the created record."""
    if not _USE_SUPABASE:
        return _memdb.insert_trade(trade_data)

    client = _get_client()
    try:
        result = client.table("trades").insert(trade_data).execute()
        logger.info("Inserted trade %s", trade_data.get("id", "unknown"))
        return result.data[0] if result.data else trade_data
    except Exception as exc:
        logger.error("Failed to insert trade: %s", exc)
        raise


def update_trade(trade_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing trade row by its UUID."""
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    if not _USE_SUPABASE:
        return _memdb.update_trade(trade_id, updates)

    client = _get_client()
    try:
        result = (
            client.table("trades")
            .update(updates)
            .eq("id", trade_id)
            .execute()
        )
        logger.info("Updated trade %s with %s", trade_id, list(updates.keys()))
        return result.data[0] if result.data else updates
    except Exception as exc:
        logger.error("Failed to update trade %s: %s", trade_id, exc)
        raise


def get_session_trades(session_id: str) -> List[Dict[str, Any]]:
    """Return all trades belonging to *session_id*, newest first."""
    if not _USE_SUPABASE:
        return _memdb.get_session_trades(session_id)

    client = _get_client()
    try:
        result = (
            client.table("trades")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.error("Failed to fetch session trades: %s", exc)
        return []


def get_all_trades(
    limit: int = 50,
    offset: int = 0,
    trading_mode: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return paginated trades across all sessions, newest first.

    Returns (trades_list, total_count).
    """
    if not _USE_SUPABASE:
        return _memdb.get_all_trades(limit, offset, trading_mode)

    client = _get_client()
    try:
        query = client.table("trades").select("*", count="exact")
        if trading_mode and trading_mode in ("live", "paper"):
            query = query.eq("trading_mode", trading_mode)
        query = query.order("created_at", desc=True)
        query = query.range(offset, offset + limit - 1)
        result = query.execute()
        total = result.count if result.count is not None else len(result.data or [])
        return (result.data or [], total)
    except Exception as exc:
        logger.error("Failed to fetch all trades: %s", exc)
        return ([], 0)


def get_analytics_summary(trading_mode: Optional[str] = None) -> Dict[str, Any]:
    """Compute aggregated analytics from the trades table.

    Returns a dict matching the AnalyticsSummary model.
    """
    if not _USE_SUPABASE:
        trades_list, _ = _memdb.get_all_trades(limit=999999, trading_mode=trading_mode)
        trades = trades_list
    else:
        client = _get_client()
        try:
            query = client.table("trades").select("*")
            if trading_mode and trading_mode in ("live", "paper"):
                query = query.eq("trading_mode", trading_mode)
            result = query.execute()
            trades = result.data or []
        except Exception as exc:
            logger.error("Failed to compute analytics: %s", exc)
            return {}

    total = len(trades)
    wins = sum(1 for t in trades if t.get("status") == "WIN")
    losses = sum(1 for t in trades if t.get("status") == "LOSS")
    open_trades = sum(1 for t in trades if t.get("status") == "OPEN")
    win_rate = (wins / total * 100) if total > 0 else 0.0

    pnl_values = [float(t.get("pnl_usd", 0) or 0) for t in trades]
    total_pnl = sum(pnl_values)
    closed_pnl = [p for p in pnl_values if p != 0]
    avg_pnl = (total_pnl / len(closed_pnl)) if closed_pnl else 0.0
    best_pnl = max(pnl_values) if pnl_values else 0.0
    worst_pnl = min(pnl_values) if pnl_values else 0.0
    total_volume = sum(float(t.get("amount_usd", 0) or 0) for t in trades)

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "open_trades": open_trades,
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 4),
        "avg_pnl_per_trade": round(avg_pnl, 4),
        "best_trade_pnl": round(best_pnl, 4),
        "worst_trade_pnl": round(worst_pnl, 4),
        "total_volume": round(total_volume, 4),
    }


# ── Config operations ─────────────────────────────────────


def get_config() -> Dict[str, Any]:
    """Return the single global_config row (id = 1)."""
    if not _USE_SUPABASE:
        return _memdb.get_config()

    client = _get_client()
    try:
        result = (
            client.table("global_config")
            .select("*")
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        # Return sensible defaults when no row exists yet
        return {
            "telegram_enabled": True,
            "default_dry_run": True,
            "default_amount_usd": 5.0,
            "environment": "dev",
        }
    except Exception as exc:
        logger.error("Failed to fetch global config: %s", exc)
        return {}


def update_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update the global_config row. upsert-style: create if missing."""
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    if not _USE_SUPABASE:
        return _memdb.update_config(updates)

    client = _get_client()
    try:
        # Try to update the first row
        existing = get_config()
        if existing.get("id"):
            result = (
                client.table("global_config")
                .update(updates)
                .eq("id", existing["id"])
                .execute()
            )
        else:
            result = (
                client.table("global_config")
                .insert(updates)
                .execute()
            )
        logger.info("Updated global config with keys: %s", list(updates.keys()))
        return result.data[0] if result.data else updates
    except Exception as exc:
        logger.error("Failed to update global config: %s", exc)
        raise
