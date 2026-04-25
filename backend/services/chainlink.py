"""
Polybot — Chainlink price-feed service.

Reads BTC/USD from the Chainlink aggregator deployed on Polygon mainnet.
Address: 0xc907E116054Ad103354f2D350FD2514433D57F6F
"""

from __future__ import annotations

import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# web3 is imported lazily inside _init_web3() to avoid startup crash
# when the package is not installed
Web3 = None

# Minimal ABI — only latestRoundData() and decimals() are needed.
AGGREGATOR_V3_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"internalType": "uint80", "name": "roundId", "type": "uint80"},
            {"internalType": "int256", "name": "answer", "type": "int256"},
            {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
            {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
            {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [
            {"internalType": "uint8", "name": "", "type": "uint8"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

_w3: Optional[Web3] = None
_contract = None
_decimals: Optional[int] = None
_active_rpc: Optional[str] = None

# Ordered list of free public Polygon RPCs tried in sequence on failure.
_FALLBACK_RPCS = [
    "https://rpc.ankr.com/polygon",
    "https://polygon-bor-rpc.publicnode.com",
    "https://1rpc.io/matic",
    "https://polygon-rpc.com",
]


def _init_web3(rpc_url: Optional[str] = None):
    """Lazily create the Web3 instance and contract handle."""
    global _w3, _contract, _decimals, Web3, _active_rpc
    url = rpc_url or settings.POLYGON_RPC_URL
    if Web3 is None:
        from web3 import Web3 as _Web3
        Web3 = _Web3
    _w3 = Web3(Web3.HTTPProvider(url))
    _active_rpc = url
    address = Web3.to_checksum_address(settings.CHAINLINK_BTC_USD_ADDRESS)
    _contract = _w3.eth.contract(address=address, abi=AGGREGATOR_V3_ABI)
    try:
        _decimals = _contract.functions.decimals().call()
    except Exception:
        _decimals = 8  # Chainlink BTC/USD uses 8 decimals


async def get_btc_price() -> float:
    """
    Return the latest BTC/USD price from the Chainlink oracle on Polygon.

    Tries the configured POLYGON_RPC_URL first, then falls back through
    _FALLBACK_RPCS if the primary endpoint returns an error or 401.
    """
    global _w3, _contract, _decimals, _active_rpc

    rpcs_to_try: list[str] = []
    if settings.POLYGON_RPC_URL not in _FALLBACK_RPCS:
        rpcs_to_try.append(settings.POLYGON_RPC_URL)
    rpcs_to_try.extend(_FALLBACK_RPCS)

    # If we already have a working RPC cached, try it first.
    if _active_rpc and _active_rpc in rpcs_to_try:
        rpcs_to_try.remove(_active_rpc)
        rpcs_to_try.insert(0, _active_rpc)

    last_exc: Optional[Exception] = None

    for rpc_url in rpcs_to_try:
        try:
            _init_web3(rpc_url)
            assert _contract is not None and _decimals is not None
            round_data = _contract.functions.latestRoundData().call()
            raw_price  = round_data[1]
            price      = raw_price / (10 ** _decimals)
            logger.info("Chainlink BTC/USD = %.2f (via %s)", price, rpc_url)
            return float(price)
        except Exception as exc:
            logger.warning("Chainlink RPC %s failed: %s — trying next", rpc_url, exc)
            # Reset cached client so next iteration reinitialises cleanly.
            _w3 = _contract = _decimals = _active_rpc = None
            last_exc = exc

    logger.error("All Chainlink RPCs failed. Last error: %s", last_exc)
    raise RuntimeError(f"Chainlink unavailable: {last_exc}") from last_exc
