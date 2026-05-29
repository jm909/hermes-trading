"""Price adapter — RSI, OHLCV via ccxt (free public endpoints)."""
import os
import asyncio
from typing import Any

import ccxt.async_support as ccxt
import numpy as np

SCHEMA_VERSION = "price/v1"
ASSET = os.getenv("HERMES_ASSET", "BTC/USDT")
EXCHANGE_ID = os.getenv("HERMES_EXCHANGE", "kucoin")


class SchemaError(Exception):
    pass


def _compute_rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period + 1):])
    gains = deltas[deltas > 0].mean() if (deltas > 0).any() else 0.0
    losses = -deltas[deltas < 0].mean() if (deltas < 0).any() else 0.0
    if losses == 0:
        return 100.0
    rs = gains / losses
    return round(100 - (100 / (1 + rs)), 2)


async def fetch() -> dict:
    exchange_class = getattr(ccxt, EXCHANGE_ID)
    exchange_params: dict[str, Any] = {"enableRateLimit": True}

    api_key = os.getenv("EXCHANGE_API_KEY")
    api_secret = os.getenv("EXCHANGE_API_SECRET")
    if api_key and api_secret:
        exchange_params["apiKey"] = api_key
        exchange_params["secret"] = api_secret

    exchange = exchange_class(exchange_params)
    try:
        ohlcv = await exchange.fetch_ohlcv(ASSET, timeframe="1m", limit=30)
        if not ohlcv:
            raise SchemaError("Empty OHLCV response")

        closes = [candle[4] for candle in ohlcv]
        latest = ohlcv[-1]

        data = {
            "schema_version": SCHEMA_VERSION,
            "asset": ASSET,
            "open": latest[1],
            "high": latest[2],
            "low": latest[3],
            "close": latest[4],
            "volume": latest[5],
            "rsi_14": _compute_rsi(closes),
            "ts": latest[0],
        }

        required = ["schema_version", "asset", "close", "rsi_14"]
        for field in required:
            if field not in data:
                raise SchemaError(f"Missing field: {field}")

        return data
    finally:
        await exchange.close()
