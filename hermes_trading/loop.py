"""24/7 async trading loop — pulls data, evaluates strategy, logs outcomes."""
import asyncio
import json
import os
import pathlib
import subprocess
import time
import traceback
from datetime import datetime, timezone

import yaml

from hermes_trading.adapters.price import fetch as fetch_price
from hermes_trading.adapters.onchain import fetch as fetch_onchain
from hermes_trading.adapters.news import fetch as fetch_news
from hermes_trading.adapters.macro import fetch as fetch_macro
from hermes_trading.score import score

HEARTBEAT_INTERVAL = 60  # seconds
MAX_CONSECUTIVE_FAILURES = 5
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2  # seconds


class CircuitBreakerOpen(Exception):
    pass


async def _fetch_with_retry(fetch_fn, name: str) -> dict:
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return await fetch_fn()
        except Exception as exc:
            if attempt == RETRY_ATTEMPTS - 1:
                raise
            delay = RETRY_BASE_DELAY ** (attempt + 1)
            print(f"[{name}] attempt {attempt + 1} failed ({exc}), retrying in {delay}s")
            await asyncio.sleep(delay)


def _load_strategy(state_dir: pathlib.Path) -> dict:
    strategy_file = state_dir / "strategy.yaml"
    with open(strategy_file) as f:
        return yaml.safe_load(f)


def _evaluate_entry(price_data: dict, strategy: dict) -> bool:
    indicator = strategy["entry"]["indicator"]
    threshold = strategy["entry"]["threshold"]
    direction = strategy["entry"]["direction"]

    if indicator == "rsi":
        rsi = price_data.get("rsi_14")
        if rsi is None:
            return False
        if direction == "long":
            return rsi < threshold
        else:
            return rsi > threshold
    return False


def _write_heartbeat(state_dir: pathlib.Path, status: str, consecutive_failures: int):
    hb = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "consecutive_failures": consecutive_failures,
    }
    with open(state_dir / "heartbeat.json", "w") as f:
        json.dump(hb, f)


def _append_trade(state_dir: pathlib.Path, trade: dict):
    with open(state_dir / "trades.jsonl", "a") as f:
        f.write(json.dumps(trade) + "\n")
    _push_file_to_github(state_dir / "trades.jsonl", "state/trades.jsonl", "worker: trade logged")


def _push_file_to_github(local_path: pathlib.Path, repo_path: str, message: str):
    import base64
    import urllib.request
    token = os.getenv("GIT_TOKEN")
    if not token:
        return
    try:
        content = local_path.read_bytes()
        encoded = base64.b64encode(content).decode()
        # Get current SHA
        url = f"https://api.github.com/repos/jm909/hermes-trading/contents/{repo_path}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "hermes-bot"}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                sha = json.loads(resp.read())["sha"]
        except Exception:
            sha = None
        body = {"message": message, "content": encoded}
        if sha:
            body["sha"] = sha
        data = json.dumps(body).encode()
        req2 = urllib.request.Request(url, data=data, headers=headers, method="PUT")
        with urllib.request.urlopen(req2, timeout=15) as resp:
            resp.read()
        print(f"[github] {repo_path} pushed", flush=True)
    except Exception as e:
        print(f"[github] push failed: {e}", flush=True)


async def run_loop(asset: str, goal: dict, state_dir: pathlib.Path):
    consecutive_failures = 0
    open_position = None

    while True:
        loop_start = time.monotonic()
        try:
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                raise CircuitBreakerOpen(f"Circuit open after {consecutive_failures} consecutive failures")

            price_data, onchain_data, news_data, macro_data = await asyncio.gather(
                _fetch_with_retry(fetch_price, "price"),
                _fetch_with_retry(fetch_onchain, "onchain"),
                _fetch_with_retry(fetch_news, "news"),
                _fetch_with_retry(fetch_macro, "macro"),
            )

            strategy = _load_strategy(state_dir)
            current_price = price_data.get("close", 0)

            # Close open position if stop-loss, take-profit, or time limit hit
            if open_position is not None:
                entry_price = open_position["entry_price"]
                entry_ts = open_position["entry_ts"]
                stop_loss_pct = strategy.get("stop_loss_pct", 2.0)
                take_profit_pct = strategy.get("take_profit_pct", 1.0)
                max_hold_hours = strategy.get("max_hold_hours", 2.0)
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                held_hours = (time.monotonic() - open_position["entry_monotonic"]) / 3600

                exit_reason = None
                if pnl_pct <= -stop_loss_pct:
                    exit_reason = "stop_loss"
                elif pnl_pct >= take_profit_pct:
                    exit_reason = "take_profit"
                elif held_hours >= max_hold_hours:
                    exit_reason = "time_exit"

                if exit_reason:
                    trade = {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "asset": asset,
                        "direction": open_position["direction"],
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": round(pnl_pct, 4),
                        "exit_reason": exit_reason,
                        "strategy_version": strategy.get("version", "01"),
                    }
                    _append_trade(state_dir, trade)
                    print(f"[trade] CLOSED {exit_reason} pnl={pnl_pct:.2f}%", flush=True)
                    open_position = None

            # Open new position if entry fires and no position open
            if open_position is None and _evaluate_entry(price_data, strategy):
                direction = strategy["entry"]["direction"]
                position_size_r = strategy.get("position_size_r", 0.5)
                open_position = {
                    "direction": direction,
                    "entry_price": current_price,
                    "entry_ts": datetime.now(timezone.utc).isoformat(),
                    "entry_monotonic": time.monotonic(),
                    "position_size_r": position_size_r,
                }
                print(f"[trade] OPEN {direction} @ {current_price}", flush=True)

            consecutive_failures = 0
            _write_heartbeat(state_dir, "ok", 0)
            print(f"[tick] rsi={price_data.get('rsi_14')} close={price_data.get('close')} position={'open' if open_position else 'none'}")

        except CircuitBreakerOpen as exc:
            print(f"[circuit-breaker] {exc} — sleeping 300s before reset")
            _write_heartbeat(state_dir, "circuit_open", consecutive_failures)
            await asyncio.sleep(300)
            consecutive_failures = 0
            continue

        except Exception as exc:
            consecutive_failures += 1
            print(f"[loop] error ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {exc}")
            traceback.print_exc()
            _write_heartbeat(state_dir, "error", consecutive_failures)

        elapsed = time.monotonic() - loop_start
        sleep_for = max(0, HEARTBEAT_INTERVAL - elapsed)
        await asyncio.sleep(sleep_for)
