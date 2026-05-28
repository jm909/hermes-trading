"""On-chain adapter — BTC metrics via free Blockchain.info endpoint."""
import os
import httpx

SCHEMA_VERSION = "onchain/v1"
GLASSNODE_API_KEY = os.getenv("GLASSNODE_API_KEY")


class SchemaError(Exception):
    pass


async def fetch() -> dict:
    # Free public endpoint — no key required
    url = "https://blockchain.info/stats?format=json"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        raw = resp.json()

    data = {
        "schema_version": SCHEMA_VERSION,
        "hash_rate": raw.get("hash_rate"),
        "difficulty": raw.get("difficulty"),
        "n_tx": raw.get("n_tx"),
        "total_fees_btc": raw.get("total_fees_btc"),
        "mempool_size": raw.get("mempool_size"),
    }

    if data["hash_rate"] is None:
        raise SchemaError("Missing hash_rate from blockchain.info")

    return data
