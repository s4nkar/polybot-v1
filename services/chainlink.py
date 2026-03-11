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


def _init_web3():
    """Lazily create the Web3 instance and contract handle."""
    global _w3, _contract, _decimals, Web3
    if _w3 is None:
        if Web3 is None:
            from web3 import Web3 as _Web3
            Web3 = _Web3
        _w3 = Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL))
        address = Web3.to_checksum_address(settings.CHAINLINK_BTC_USD_ADDRESS)
        _contract = _w3.eth.contract(address=address, abi=AGGREGATOR_V3_ABI)
        try:
            _decimals = _contract.functions.decimals().call()
        except Exception:
            _decimals = 8  # Chainlink BTC/USD typically uses 8 decimals


async def get_btc_price() -> float:
    """
    Return the latest BTC/USD price from the Chainlink oracle on Polygon.

    NOTE: web3.py's contract calls are synchronous under the hood, so this
    function wraps them in an async interface for consistency with the rest
    of the codebase.  For production-grade apps consider using
    ``asyncio.to_thread`` to avoid blocking the event loop.
    """
    try:
        _init_web3()
        assert _contract is not None and _decimals is not None

        round_data = _contract.functions.latestRoundData().call()
        raw_price = round_data[1]  # int256 answer
        price = raw_price / (10 ** _decimals)

        logger.info("Chainlink BTC/USD price: %.2f", price)
        return float(price)
    except Exception as exc:
        logger.error("Chainlink get_btc_price error: %s", exc)
        raise
