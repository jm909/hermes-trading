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


def _evaluate_entry(price_data: dict, strategy: dict) -> str | None:
    """Returns 'long', 'short', or None."""
    indicator = strategy["entry"]["indicator"]
    long_threshold  = strategy["entry"].get("threshold", 30)
    short_threshold = strategy["entry"].get("short_threshold", 70)
    mode = strategy["entry"].get("direction", "both")  # long | short | both
    use_trend_filter = strategy.get("ema_trend_filter", True)

    if indicator != "rsi":
        return None

    rsi = price_data.get("rsi_14")
    if rsi is None:
        return None

    above_ema = price_data.get("above_ema20", True)

    # Long signal: RSI oversold + uptrend
    if mode in ("long", "both"):
        if rsi < long_threshold:
            if not use_trend_filter or above_ema:
                return "long"

    # Short signal: RSI overbought + downtrend
    if mode in ("short", "both"):
        if rsi > short_threshold:
            if not use_trend_filter or not above_ema:
                return "short"

    return None


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


def _save_position(state_dir: pathlib.Path, position: dict | None):
    f = state_dir / "open_position.json"
    if position is None:
        f.unlink(missing_ok=True)
    else:
        f.write_text(json.dumps(position), encoding="utf-8")


def _load_position(state_dir: pathlib.Path) -> dict | None:
    f = state_dir / "open_position.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


async def run_loop(asset: str, goal: dict, state_dir: pathlib.Path):
    consecutive_failures = 0
    open_position = _load_position(state_dir)
    if open_position:
        print(f"[startup] restored open {open_position['direction'].upper()} @ {open_position['entry_price']} from disk", flush=True)

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
                direction = open_position["direction"]
                stop_loss_pct = strategy.get("stop_loss_pct", 1.0)
                take_profit_pct = strategy.get("take_profit_pct", 2.0)
                max_hold_hours = strategy.get("max_hold_hours", 4.0)
                entry_dt = datetime.fromisoformat(open_position["entry_ts"])
                held_hours = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 3600

                # PnL flipped for shorts
                if direction == "short":
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100
                else:
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100

                exit_reason = None
                if pnl_pct <= -stop_loss_pct:
                    exit_reason = "stop_loss"
                elif pnl_pct >= take_profit_pct:
                    exit_reason = "take_profit"
                elif held_hours >= max_hold_hours:
                    exit_reason = "time_exit"

                if exit_reason:
                    held_mins = round(held_hours * 60, 1)
                    trade = {
                        "ts_open": open_position["entry_ts"],
                        "ts_close": datetime.now(timezone.utc).isoformat(),
                        "asset": asset,
                        "direction": open_position["direction"],
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": round(pnl_pct, 4),
                        "pnl_usd": round((current_price - entry_price) * open_position.get("position_size_r", 0.5), 2),
                        "exit_reason": exit_reason,
                        "held_minutes": held_mins,
                        "entry_rsi": open_position.get("entry_rsi"),
                        "entry_trend": open_position.get("entry_trend"),
                        "strategy_version": strategy.get("version", "01"),
                    }
                    _append_trade(state_dir, trade)
                    print(f"[trade] CLOSED {exit_reason} pnl={pnl_pct:.2f}%", flush=True)
                    open_position = None
                    _save_position(state_dir, None)

            # Open new position if entry fires and no position open
            signal = _evaluate_entry(price_data, strategy) if open_position is None else None
            if signal:
                position_size_r = strategy.get("position_size_r", 0.5)
                open_position = {
                    "direction": signal,
                    "entry_price": current_price,
                    "entry_ts": datetime.now(timezone.utc).isoformat(),
                    "entry_rsi": price_data.get("rsi_14"),
                    "entry_trend": "UP" if price_data.get("above_ema20") else "DOWN",
                    "position_size_r": position_size_r,
                }
                _save_position(state_dir, open_position)
                print(f"[trade] OPEN {signal.upper()} @ {current_price}", flush=True)

            consecutive_failures = 0
            _write_heartbeat(state_dir, "ok", 0)
            trend = "UP" if price_data.get("above_ema20") else "DOWN"
            print(f"[tick] rsi={price_data.get('rsi_14')} close={price_data.get('close')} ema20={price_data.get('ema20')} trend={trend} position={'open' if open_position else 'none'}", flush=True)

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
