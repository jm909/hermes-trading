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
        dst.write_text("Time Opened,Time Closed,Asset,Direction,Entry Price,Exit Price,PnL %,Est PnL USD,Exit Reason,Held (mins),Entry RSI,Entry Trend,Strategy\n", encoding="utf-8")
        return
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Time Opened", "Time Closed", "Asset", "Direction", "Entry Price",
                    "Exit Price", "PnL %", "Est PnL USD", "Exit Reason",
                    "Held (mins)", "Entry RSI", "Entry Trend", "Strategy"])
        for r in rows:
            # Support both old format (ts) and new format (ts_open/ts_close)
            opened = r.get("ts_open") or r.get("ts", "")
            closed = r.get("ts_close") or r.get("ts", "")
            w.writerow([
                opened[:19].replace("T", " ") if opened else "",
                closed[:19].replace("T", " ") if closed else "",
                r.get("asset", "BTC/USDT"),
                r.get("direction", "").upper(),
                r.get("entry_price", ""),
                r.get("exit_price", ""),
                f"{r.get('pnl_pct', 0):+.4f}%",
                r.get("pnl_usd", ""),
                r.get("exit_reason", "").replace("_", " ").title(),
                r.get("held_minutes", ""),
                r.get("entry_rsi", ""),
                r.get("entry_trend", ""),
                f"v{r.get('strategy_version', '?')}",
            ])
    print(f"Exported {len(rows)} trades to trades.csv")


def export_hypotheses():
    src = STATE_DIR / "hypotheses.jsonl"
    dst = STATE_DIR / "hypotheses.csv"
    if not src.exists():
        return
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l]
    if not rows:
        dst.write_text("Time,From Version,To Version,Variable Changed,Old Value,New Value,Rationale,Realised Return,Max Drawdown\n", encoding="utf-8")
        return
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Time", "From Version", "To Version", "Variable Changed",
                    "Old Value", "New Value", "Rationale", "Realised Return %", "Max Drawdown %"])
        for r in rows:
            ret = r.get("realised_return", "")
            dd  = r.get("max_drawdown_seen", "")
            w.writerow([
                r.get("ts", "")[:19].replace("T", " "),
                f"v{r.get('strategy_version_from', '?')}",
                f"v{r.get('strategy_version_to', '?')}",
                r.get("changed_var", ""),
                r.get("old_val", ""),
                r.get("new_val", ""),
                r.get("rationale") or r.get("hypothesis", ""),
                f"{float(ret)*100:+.2f}%" if ret != "" else "",
                f"{float(dd)*100:.2f}%" if dd != "" else "",
            ])
    print(f"Exported {len(rows)} reflections to hypotheses.csv")


def export_strategy():
    src = STATE_DIR / "strategy.yaml"
    dst = STATE_DIR / "strategy.csv"
    if not src.exists():
        return
    s = yaml.safe_load(src.read_text(encoding="utf-8"))
    entry = s.get("entry", {})
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Parameter", "Value", "Description"])
        w.writerow(["Version",          s.get("version", "?"),             "Current strategy version"])
        w.writerow(["Indicator",        entry.get("indicator", "rsi").upper(), "Entry signal indicator"])
        w.writerow(["RSI Threshold",    entry.get("threshold", "?"),       "Enter long when RSI below this"])
        w.writerow(["Direction",        entry.get("direction", "long").upper(), "Trade direction"])
        w.writerow(["EMA Trend Filter", s.get("ema_trend_filter", True),   "Only enter if price above EMA20"])
        w.writerow(["Stop Loss",        f"{s.get('stop_loss_pct', '?')}%", "Exit if loss exceeds this"])
        w.writerow(["Take Profit",      f"{s.get('take_profit_pct', '?')}%", "Exit if gain exceeds this"])
        w.writerow(["Max Hold",         f"{s.get('max_hold_hours', '?')}h", "Force-close after this time"])
        w.writerow(["Position Size",    f"{s.get('position_size_r', '?')}R", "Risk per trade"])
    print("Exported strategy to strategy.csv")


if __name__ == "__main__":
    export_trades()
    export_hypotheses()
    export_strategy()
