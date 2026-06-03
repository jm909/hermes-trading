"""Reflect on the last N closed trades and update strategy.yaml with one-variable change."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from hermes_trading.score import score as compute_score

STATE_DIR = Path(__file__).parent.parent / "state"
STRATEGY_FILE = STATE_DIR / "strategy.yaml"
TRADES_FILE = STATE_DIR / "trades.jsonl"
HYPOTHESES_FILE = STATE_DIR / "hypotheses.jsonl"
GOAL_FILE = STATE_DIR / "goal.yaml"
LAST_REFLECT_FILE = STATE_DIR / "last_reflect.json"
HISTORY_DIR = STATE_DIR / "history"


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


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def _next_version(current: str) -> str:
    try:
        n = int(str(current).lstrip("0") or "0")
    except ValueError:
        n = 0
    return f"{n + 1:02d}"


def _archive_strategy(strategy: dict, version: str) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        n = int(str(version).lstrip("0") or "0")
    except ValueError:
        n = 0
    dest = HISTORY_DIR / f"v{n:04d}.yaml"
    _save_yaml(dest, strategy)


def _exit_distribution(trades: list) -> dict:
    counts = {"sl": 0, "tp": 0, "timeout": 0, "other": 0}
    for t in trades:
        reason = str(t.get("exit_reason", "")).lower()
        if "sl" in reason or "stop" in reason:
            counts["sl"] += 1
        elif "tp" in reason or "profit" in reason or "take" in reason:
            counts["tp"] += 1
        elif "time" in reason or "expire" in reason:
            counts["timeout"] += 1
        else:
            counts["other"] += 1
    return counts


def _pick_hypothesis(score_val: float, trades: list, strategy: dict) -> tuple:
    """Returns (variable_path, old_value, new_value, rationale)."""
    exits = _exit_distribution(trades)
    total = len(trades) or 1
    sl_rate = exits["sl"] / total
    timeout_rate = exits["timeout"] / total

    entry = strategy.get("entry", {})
    threshold = int(entry.get("threshold", 30))
    sl_pct = float(strategy.get("stop_loss_pct", 1.0))
    tp_pct = float(strategy.get("take_profit_pct", 2.0))
    pos_size = float(strategy.get("position_size_r", 0.5))
    max_hold = float(strategy.get("max_hold_hours", 4.0))

    # Bad score + mostly SL hits -> entry threshold too aggressive, require deeper oversold
    if score_val < -0.2 and sl_rate > 0.5 and threshold < 45:
        new_val = min(threshold + 3, 45)
        return ("entry.threshold", threshold, new_val,
                f"SL hit rate {sl_rate:.0%}, score {score_val:.3f} — raising RSI threshold "
                f"{threshold}->{new_val} to require a stronger oversold signal before entry.")

    # Very bad score -> reduce position size for capital preservation
    if score_val < -0.4 and pos_size > 0.2:
        new_val = round(max(pos_size - 0.1, 0.2), 2)
        return ("position_size_r", pos_size, new_val,
                f"Score {score_val:.3f} below -0.4 — shrinking position size {pos_size}->{new_val} "
                f"to limit drawdown while diagnosis continues.")

    # High timeout rate + losing -> positions stalling, cut max hold time
    if timeout_rate > 0.4 and score_val < 0.1 and max_hold > 2.0:
        new_val = max(max_hold - 1.0, 2.0)
        return ("max_hold_hours", max_hold, new_val,
                f"Timeout rate {timeout_rate:.0%}, score {score_val:.3f} — reducing max hold "
                f"{max_hold}h->{new_val}h to cut losers that stall before hitting TP.")

    # Marginal score + high SL rate -> SL too tight, widen slightly
    if -0.2 <= score_val < 0.1 and sl_rate > 0.4 and sl_pct < 2.5:
        new_val = round(sl_pct + 0.25, 2)
        return ("stop_loss_pct", sl_pct, new_val,
                f"SL hit rate {sl_rate:.0%}, score {score_val:.3f} — widening SL {sl_pct}%->{new_val}% "
                f"to reduce shake-outs on valid setups.")

    # Good score -> widen TP to capture more of winning runs
    if score_val >= 0.3 and tp_pct < 4.0:
        new_val = round(tp_pct + 0.25, 2)
        return ("take_profit_pct", tp_pct, new_val,
                f"Score {score_val:.3f} is positive — widening TP {tp_pct}%->{new_val}% "
                f"to let winners run further.")

    # Positive score + TP already wide -> tighten entry for higher quality
    if score_val >= 0.2 and threshold > 25:
        new_val = threshold - 2
        return ("entry.threshold", threshold, new_val,
                f"Score {score_val:.3f} with TP at {tp_pct}% — lowering RSI threshold "
                f"{threshold}->{new_val} for higher-quality entry signals.")

    # Default: no dominant signal, nudge SL tighter to improve R:R
    if sl_pct > 0.75:
        new_val = round(sl_pct - 0.25, 2)
        return ("stop_loss_pct", sl_pct, new_val,
                f"No dominant pattern (score {score_val:.3f}) — tightening SL "
                f"{sl_pct}%->{new_val}% to improve R:R ratio.")

    new_val = round(tp_pct + 0.25, 2)
    return ("take_profit_pct", tp_pct, new_val,
            f"Baseline nudge (score {score_val:.3f}) — widening TP {tp_pct}%->{new_val}% to improve R:R.")


def _set_nested(obj: dict, dot_path: str, value) -> None:
    parts = dot_path.split(".")
    for part in parts[:-1]:
        obj = obj.setdefault(part, {})
    obj[parts[-1]] = value


def reflect() -> None:
    goal = _load_yaml(GOAL_FILE)
    reflect_every = int(goal.get("reflection_every", 5))

    last_count = 0
    if LAST_REFLECT_FILE.exists():
        try:
            last_count = json.loads(LAST_REFLECT_FILE.read_text(encoding="utf-8")).get("last_trade_count", 0)
        except Exception:
            pass

    trades = _load_jsonl(TRADES_FILE)
    new_trades = trades[last_count:]

    if len(new_trades) < reflect_every:
        print(f"Reflect: {len(new_trades)}/{reflect_every} new trades since last reflection — waiting.")
        return

    batch = new_trades[-reflect_every:]
    score_val = compute_score(batch, goal)

    strategy = _load_yaml(STRATEGY_FILE)
    old_version = str(strategy.get("version", "01"))

    var_path, old_val, new_val, rationale = _pick_hypothesis(score_val, batch, strategy)

    pnl_values = [t.get("pnl_pct", 0) / 100 for t in batch]
    realised_return = sum(pnl_values)
    peak, cumulative, max_dd = 0.0, 0.0, 0.0
    for p in pnl_values:
        cumulative += p
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)

    _archive_strategy(strategy, old_version)

    new_version = _next_version(old_version)
    _set_nested(strategy, var_path, new_val)
    strategy["version"] = new_version
    _save_yaml(STRATEGY_FILE, strategy)

    now = datetime.now(timezone.utc).isoformat()
    hypothesis = {
        "time": now,
        "from_version": old_version,
        "to_version": new_version,
        "variable_changed": var_path,
        "old_value": old_val,
        "new_value": new_val,
        "rationale": rationale,
        "realised_return": round(realised_return, 6),
        "max_drawdown": round(max_dd, 6),
        "score": score_val,
    }
    with open(HYPOTHESES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(hypothesis) + "\n")

    LAST_REFLECT_FILE.write_text(
        json.dumps({"last_trade_count": len(trades), "last_reflect_time": now}),
        encoding="utf-8",
    )

    print(f"Reflect v{old_version}->v{new_version}: {var_path} {old_val}->{new_val} (score {score_val:.4f})")
    print(f"Rationale: {rationale}")


fallback_reflect = reflect  # alias used by run.py


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fallback", action="store_true")
    parser.parse_args()
    reflect()


if __name__ == "__main__":
    main()
