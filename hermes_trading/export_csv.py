"""Export JSONL state files to CSV for Google Sheets IMPORTDATA."""
import csv
import json
import pathlib
import yaml

STATE_DIR = pathlib.Path(__file__).parent.parent / "state"


def export_trades():
    src = STATE_DIR / "trades.jsonl"
    dst = STATE_DIR / "trades.csv"
    if not src.exists():
        return
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l]
    if not rows:
        return
    keys = ["ts", "asset", "direction", "entry_price", "exit_price", "pnl_pct", "exit_reason", "strategy_version"]
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"Exported {len(rows)} trades to trades.csv")


def export_hypotheses():
    src = STATE_DIR / "hypotheses.jsonl"
    dst = STATE_DIR / "hypotheses.csv"
    if not src.exists():
        return
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l]
    if not rows:
        return
    keys = ["ts", "mode", "strategy_version_from", "strategy_version_to", "changed_var", "old_val", "new_val", "rationale", "realised_return", "max_drawdown_seen"]
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"Exported {len(rows)} reflections to hypotheses.csv")


def export_strategy():
    src = STATE_DIR / "strategy.yaml"
    dst = STATE_DIR / "strategy.csv"
    if not src.exists():
        return
    s = yaml.safe_load(src.read_text(encoding="utf-8"))
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "value"])
        w.writerow(["version", s.get("version")])
        w.writerow(["entry.indicator", s.get("entry", {}).get("indicator")])
        w.writerow(["entry.threshold", s.get("entry", {}).get("threshold")])
        w.writerow(["entry.direction", s.get("entry", {}).get("direction")])
        w.writerow(["stop_loss_pct", s.get("stop_loss_pct")])
        w.writerow(["position_size_r", s.get("position_size_r")])
    print("Exported strategy to strategy.csv")


if __name__ == "__main__":
    export_trades()
    export_hypotheses()
    export_strategy()
