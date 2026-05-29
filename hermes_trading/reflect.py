"""Reflection cycle — deterministic fallback (--fallback) or Hermes-driven (--hermes)."""
import argparse
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

import yaml

STATE_DIR = pathlib.Path("/app/state") if pathlib.Path("/app").exists() else pathlib.Path.home() / "hermes-trading" / "state"
STRATEGY_FILE = STATE_DIR / "strategy.yaml"
HYPOTHESES_FILE = STATE_DIR / "hypotheses.jsonl"
HISTORY_DIR = STATE_DIR / "history"
TRADES_FILE = STATE_DIR / "trades.jsonl"
GOAL_FILE = STATE_DIR / "goal.yaml"


def load_yaml(path: pathlib.Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def save_yaml(path: pathlib.Path, data: dict):
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def bump_version(version: str) -> str:
    try:
        n = int(version)
        return str(n + 1).zfill(2)
    except ValueError:
        return version + "_next"


def archive_strategy(strategy: dict):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    version = strategy.get("version", "00")
    archive_path = HISTORY_DIR / f"v{version.zfill(4)}.yaml"
    save_yaml(archive_path, strategy)


def append_hypothesis(hypothesis: dict):
    with open(HYPOTHESES_FILE, "a") as f:
        f.write(json.dumps(hypothesis) + "\n")


def load_recent_trades(n: int = 25) -> list:
    if not TRADES_FILE.exists():
        return []
    lines = TRADES_FILE.read_text().strip().splitlines()
    return [json.loads(l) for l in lines[-n:] if l]


def fallback_reflect():
    """Deterministic reflection — changes exactly ONE variable based on goal comparison."""
    strategy = load_yaml(STRATEGY_FILE)
    goal = load_yaml(GOAL_FILE)
    trades = load_recent_trades()

    if not trades:
        print("[reflect] No trades yet — nothing to reflect on.")
        return

    pnl_values = [t.get("pnl_pct", 0) for t in trades]
    realised_return = sum(pnl_values) / 100
    target = goal.get("target_return_30d", 0.05)
    max_dd = goal.get("max_drawdown", 0.08)

    # Compute max drawdown from trades
    cumulative = 0
    peak = 0
    max_drawdown_seen = 0
    for pnl in pnl_values:
        cumulative += pnl / 100
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_drawdown_seen:
            max_drawdown_seen = dd

    changed_var = None
    old_val = None
    new_val = None
    rationale = None

    if max_drawdown_seen > max_dd:
        # Drawdown too high — tighten stop loss
        old_val = strategy.get("stop_loss_pct", 2.0)
        new_val = round(old_val - 0.2, 2)
        strategy["stop_loss_pct"] = new_val
        changed_var = "stop_loss_pct"
        rationale = f"drawdown {max_drawdown_seen:.2%} > max {max_dd:.2%} — tightening stop"
    elif realised_return < target:
        # Return below target — loosen entry threshold
        old_val = strategy["entry"]["threshold"]
        new_val = old_val + 2
        strategy["entry"]["threshold"] = new_val
        changed_var = "entry.threshold"
        rationale = f"realised return {realised_return:.2%} < target {target:.2%} — loosening entry"
    else:
        print(f"[reflect] Strategy on-target (return={realised_return:.2%}, dd={max_drawdown_seen:.2%}) — no change needed.")
        return

    archive_strategy(strategy)
    old_version = strategy["version"]
    strategy["version"] = bump_version(old_version)
    save_yaml(STRATEGY_FILE, strategy)

    hypothesis = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": "fallback",
        "strategy_version_from": old_version,
        "strategy_version_to": strategy["version"],
        "changed_var": changed_var,
        "old_val": old_val,
        "new_val": new_val,
        "rationale": rationale,
        "trades_in_window": len(trades),
        "realised_return": round(realised_return, 4),
        "max_drawdown_seen": round(max_drawdown_seen, 4),
    }
    append_hypothesis(hypothesis)

    print(f"[reflect] v{old_version} -> v{strategy['version']}: {changed_var} {old_val} -> {new_val} ({rationale})")


def hermes_reflect():
    """Hermes-driven reflection — calls hermes subprocess with trade context."""
    strategy = load_yaml(STRATEGY_FILE)
    goal = load_yaml(GOAL_FILE)
    trades = load_recent_trades(25)

    if not trades:
        print("[reflect] No trades yet.")
        return

    prompt = f"""You are the brain of a self-improving trading agent.

Current strategy (v{strategy.get('version', '01')}):
{yaml.dump(strategy)}

Goal:
{yaml.dump(goal)}

Last {len(trades)} closed trades (newest last):
{json.dumps(trades, indent=2)}

Rules:
- Change exactly ONE variable in strategy.yaml.
- Output valid YAML block with ONLY the changed key and new value.
- Then one sentence: the hypothesis (what you expect to improve and why).

Format:
changed_var: <dotted.path>
new_val: <value>
hypothesis: <one sentence>
"""

    result = subprocess.run(
        ["hermes"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        print(f"[reflect] hermes exited {result.returncode}: {result.stderr[:500]}")
        sys.exit(1)

    output = result.stdout.strip()
    print(f"[reflect] Hermes output:\n{output}")

    # Parse hermes output
    lines = {l.split(":")[0].strip(): ":".join(l.split(":")[1:]).strip()
             for l in output.splitlines() if ":" in l}
    changed_var = lines.get("changed_var")
    new_val_raw = lines.get("new_val")
    hypothesis_text = lines.get("hypothesis", "")

    if not changed_var or new_val_raw is None:
        print("[reflect] Could not parse Hermes output — aborting.")
        sys.exit(1)

    # Apply the change (supports dotted paths like entry.threshold)
    try:
        new_val = float(new_val_raw) if "." in new_val_raw else int(new_val_raw)
    except ValueError:
        new_val = new_val_raw

    parts = changed_var.split(".")
    target = strategy
    for p in parts[:-1]:
        target = target[p]
    old_val = target[parts[-1]]
    target[parts[-1]] = new_val

    archive_strategy(strategy)
    old_version = strategy["version"]
    strategy["version"] = bump_version(old_version)
    save_yaml(STRATEGY_FILE, strategy)

    hypothesis = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": "hermes",
        "strategy_version_from": old_version,
        "strategy_version_to": strategy["version"],
        "changed_var": changed_var,
        "old_val": old_val,
        "new_val": new_val,
        "hypothesis": hypothesis_text,
        "trades_in_window": len(trades),
    }
    append_hypothesis(hypothesis)

    print(f"[reflect] v{old_version} -> v{strategy['version']}: {changed_var} {old_val} -> {new_val}")
    print(f"[reflect] Hypothesis: {hypothesis_text}")


def main():
    parser = argparse.ArgumentParser(description="Hermes reflect cycle")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fallback", action="store_true", help="Deterministic fallback reflection")
    group.add_argument("--hermes", action="store_true", help="Hermes-driven reflection")
    args = parser.parse_args()

    if args.fallback:
        fallback_reflect()
    else:
        hermes_reflect()


if __name__ == "__main__":
    main()
