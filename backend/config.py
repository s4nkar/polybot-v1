"""
Polybot — centralised configuration loaded from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # reads ../.env or .env in the working directory


class Settings:
    """Immutable bag of every env-var the app ever reads."""

    # ── Supabase ──────────────────────────────────────────
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # ── Polymarket ────────────────────────────────────────
    POLYMARKET_API_KEY: str = os.getenv("POLYMARKET_API_KEY", "")
    POLYMARKET_WALLET_ADDRESS: str = os.getenv("POLYMARKET_WALLET_ADDRESS", "")
    POLYMARKET_PRIVATE_KEY: str = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    POLYMARKET_CLOB_API_URL: str = os.getenv("POLYMARKET_CLOB_API_URL", "https://gamma-api.polymarket.com")
    POLYMARKET_GAMMA_API_URL: str = os.getenv("POLYMARKET_GAMMA_API_URL", "https://gamma-api.polymarket.com")
    POLYMARKET_CHAIN_ID: int = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))

    # ── Binance ───────────────────────────────────────────
    BINANCE_BASE_URL: str = os.getenv("BINANCE_BASE_URL", "https://api.binance.com")

    # ── Chainlink (Polygon) ───────────────────────────────
    POLYGON_RPC_URL: str = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
    CHAINLINK_BTC_USD_ADDRESS: str = os.getenv(
        "CHAINLINK_BTC_USD_ADDRESS",
        "0xc907E116054Ad103354f2D350FD2514433D57F6F",
    )

    # ── Telegram ──────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # ── App ───────────────────────────────────────────────
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "dev")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "prod"


settings = Settings()
