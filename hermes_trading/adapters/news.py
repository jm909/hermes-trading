"""News adapter — crypto headlines via free CryptoPanic or NewsAPI."""
import os
import httpx

SCHEMA_VERSION = "news/v1"
NEWS_API_KEY = os.getenv("NEWS_API_KEY")


class SchemaError(Exception):
    pass


async def fetch() -> dict:
    # Free public endpoint — CryptoPanic public feed (no key needed for public filter)
    url = "https://cryptopanic.com/api/v1/posts/?auth_token=public&currencies=BTC&public=true"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw = resp.json()

        results = raw.get("results", [])
        headlines = [r.get("title", "") for r in results[:5]]
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}

        for r in results[:20]:
            votes = r.get("votes", {})
            pos = votes.get("positive", 0)
            neg = votes.get("negative", 0)
            if pos > neg:
                sentiment_counts["positive"] += 1
            elif neg > pos:
                sentiment_counts["negative"] += 1
            else:
                sentiment_counts["neutral"] += 1

        data = {
            "schema_version": SCHEMA_VERSION,
            "headlines": headlines,
            "sentiment_positive": sentiment_counts["positive"],
            "sentiment_negative": sentiment_counts["negative"],
            "sentiment_neutral": sentiment_counts["neutral"],
        }

    except Exception:
        # Graceful degradation — return neutral sentiment if news feed is unavailable
        data = {
            "schema_version": SCHEMA_VERSION,
            "headlines": [],
            "sentiment_positive": 0,
            "sentiment_negative": 0,
            "sentiment_neutral": 1,
            "degraded": True,
        }

    return data
