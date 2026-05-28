"""Macro adapter — DXY / fear-greed index via free public endpoints."""
import httpx

SCHEMA_VERSION = "macro/v1"


class SchemaError(Exception):
    pass


async def fetch() -> dict:
    # Fear & Greed index — free, no key
    fg_url = "https://api.alternative.me/fng/?limit=1&format=json"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(fg_url)
            resp.raise_for_status()
            raw = resp.json()

        entry = raw.get("data", [{}])[0]
        data = {
            "schema_version": SCHEMA_VERSION,
            "fear_greed_value": int(entry.get("value", 50)),
            "fear_greed_label": entry.get("value_classification", "Neutral"),
        }

    except Exception:
        # Graceful degradation
        data = {
            "schema_version": SCHEMA_VERSION,
            "fear_greed_value": 50,
            "fear_greed_label": "Neutral",
            "degraded": True,
        }

    return data
