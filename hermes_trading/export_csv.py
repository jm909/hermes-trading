"""Export trades.jsonl, hypotheses.jsonl, and strategy.yaml to CSV for Google Sheets."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

STATE_DIR = Path(__file__).parent.parent / "state"
STRATEGY_FILE = STATE_DIR / "strategy.yaml"
TRADES_FILE = STATE_DIR / "trades.jsonl"
HYPOTHESES_FILE = STATE_DIR / "hypotheses.jsonl"
HEARTBEAT_FILE = STATE_DIR / "heartbeat.json"

TRADES_CSV = STATE_DIR / "trades.csv"
HYPOTHESES_CSV = STATE_DIR / "hypotheses.csv"
STRATEGY_CSV = STATE_DIR / "strategy.csv"

TRADES_HEADERS = [
    "Time Opened", "Time Closed", "Asset", "Direction",
    "Entry Price", "Exit Price", "PnL %", "Est PnL USD",
    "Exit Reason", "Held (mins)", "Entry RSI", "Entry Trend", "Strategy",
]

HYPOTHESES_HEADERS = [
    "Time", "From Version", "To Version", "Variable Changed",
    "Old Value", "New Value", "Rationale", "Realised Return", "Max Drawdown",
]


def _load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def export_trades() -> None:
    records = _load_jsonl(TRADES_FILE)
    with open(TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(TRADES_HEADERS)
        for r in records:
            writer.writerow([
                r.get("ts_open", ""),
                r.get("ts_close", ""),
                r.get("asset", "BTC/USDT"),
                r.get("direction", ""),
                r.get("entry_price", ""),
                r.get("exit_price", ""),
                r.get("pnl_pct", ""),
                r.get("pnl_usd", ""),
                r.get("exit_reason", ""),
                r.get("held_minutes", ""),
                r.get("entry_rsi", ""),
                r.get("entry_trend", ""),
                r.get("strategy_version", ""),
            ])
    print(f"Exported {len(records)} trades -> {TRADES_CSV}")


def export_hypotheses() -> None:
    records = _load_jsonl(HYPOTHESES_FILE)
    with open(HYPOTHESES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HYPOTHESES_HEADERS)
        for r in records:
            writer.writerow([
                r.get("time", ""),
                r.get("from_version", ""),
                r.get("to_version", ""),
                r.get("variable_changed", ""),
                r.get("old_value", ""),
                r.get("new_value", ""),
                r.get("rationale", ""),
                r.get("realised_return", ""),
                r.get("max_drawdown", ""),
            ])
    print(f"Exported {len(records)} hypotheses -> {HYPOTHESES_CSV}")


def export_strategy() -> None:
    with open(STRATEGY_FILE, encoding="utf-8") as f:
        strategy = yaml.safe_load(f) or {}

    version = strategy.get("version", "?")
    entry = strategy.get("entry", {})
    rows = [
        ("Version", version, "Current strategy version"),
        ("Indicator", str(entry.get("indicator", "RSI")).upper(), "Entry signal indicator"),
        ("RSI Threshold", entry.get("threshold", ""), "Enter long when RSI below this"),
        ("Direction", str(entry.get("direction", "both")).upper(), "Trade direction"),
        ("EMA Trend Filter", strategy.get("ema_trend_filter", ""), "Only enter if price above EMA20"),
        ("Stop Loss", f"{strategy.get('stop_loss_pct', '')} pct", "Exit if loss exceeds this"),
        ("Take Profit", f"{strategy.get('take_profit_pct', '')} pct", "Exit if gain exceeds this"),
        ("Short Threshold", entry.get("short_threshold", ""), "Enter short when RSI above this"),
        ("Max Hold", f"{strategy.get('max_hold_hours', '')}h", "Force-close after this time"),
        ("Position Size", f"{strategy.get('position_size_r', '')}R", "Risk per trade"),
    ]

    with open(STRATEGY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Parameter", "Value", "Description"])
        writer.writerows(rows)
    print(f"Exported strategy v{version} -> {STRATEGY_CSV}")


def export_heartbeat() -> None:
    heartbeat = {
        "last_export": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
    }
    HEARTBEAT_FILE.write_text(json.dumps(heartbeat, indent=2), encoding="utf-8")


def main() -> None:
    export_trades()
    export_hypotheses()
    export_strategy()
    export_heartbeat()


if __name__ == "__main__":
    main()
