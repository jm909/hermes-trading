"""Local web dashboard — serves trade data, strategy history, and metrics."""
import json
import pathlib
import yaml
from http.server import HTTPServer, BaseHTTPRequestHandler

STATE_DIR = pathlib.Path(__file__).parent.parent / "state"

HTML = """<!DOCTYPE html>
<html>
<head>
<title>Hermes Trading Dashboard</title>
<meta http-equiv="refresh" content="60">
<style>
body{font-family:monospace;background:#0d1117;color:#c9d1d9;padding:20px;margin:0}
h1{color:#58a6ff}h2{color:#79c0ff;border-bottom:1px solid #30363d;padding-bottom:8px}
table{border-collapse:collapse;width:100%;margin-bottom:30px}
th{background:#161b22;color:#79c0ff;padding:10px;text-align:left;border:1px solid #30363d}
td{padding:8px 10px;border:1px solid #21262d}
tr:nth-child(even){background:#161b22}
.pos{color:#3fb950}.neg{color:#f85149}.neutral{color:#8b949e}
.card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:15px;margin-bottom:20px;display:inline-block;min-width:180px;margin-right:15px}
.card h3{margin:0 0 8px 0;color:#8b949e;font-size:12px;text-transform:uppercase}
.card .val{font-size:28px;font-weight:bold}
</style>
</head>
<body>
<h1>Hermes Trading Dashboard</h1>
<p class="neutral">Auto-refreshes every 60 seconds &bull; Paper mode only</p>
{cards}
<h2>Recent Trades</h2>
{trades_table}
<h2>Strategy Evolution</h2>
{strategy_table}
<h2>Current Strategy</h2>
<pre style="background:#161b22;padding:15px;border-radius:6px">{strategy_yaml}</pre>
</body>
</html>"""

def load_trades():
    f = STATE_DIR / "trades.jsonl"
    if not f.exists(): return []
    lines = f.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(l) for l in lines if l]

def load_hypotheses():
    f = STATE_DIR / "hypotheses.jsonl"
    if not f.exists(): return []
    lines = f.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(l) for l in lines if l]

def load_strategy():
    f = STATE_DIR / "strategy.yaml"
    if not f.exists(): return {}, ""
    text = f.read_text(encoding="utf-8")
    return yaml.safe_load(text), text

def build_html():
    trades = load_trades()
    hypotheses = load_hypotheses()
    strategy, strategy_text = load_strategy()

    total_pnl = sum(t.get("pnl_pct", 0) for t in trades)
    wins = [t for t in trades if t.get("pnl_pct", 0) > 0]
    losses = [t for t in trades if t.get("pnl_pct", 0) <= 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0

    pnl_class = "pos" if total_pnl >= 0 else "neg"
    cards = f"""
    <div class="card"><h3>Total Trades</h3><div class="val">{len(trades)}</div></div>
    <div class="card"><h3>Total PnL</h3><div class="val {pnl_class}">{total_pnl:+.2f}%</div></div>
    <div class="card"><h3>Win Rate</h3><div class="val">{win_rate:.0f}%</div></div>
    <div class="card"><h3>Strategy Version</h3><div class="val">v{strategy.get('version','?')}</div></div>
    <div class="card"><h3>Reflections</h3><div class="val">{len(hypotheses)}</div></div>
    """

    rows = ""
    for t in reversed(trades[-50:]):
        pnl = t.get("pnl_pct", 0)
        cls = "pos" if pnl > 0 else "neg"
        rows += f"<tr><td>{t.get('ts','')[:19]}</td><td>{t.get('asset','')}</td><td>{t.get('direction','')}</td><td>${t.get('entry_price',0):,.0f}</td><td>${t.get('exit_price',0):,.0f}</td><td class='{cls}'>{pnl:+.2f}%</td><td>{t.get('exit_reason','')}</td><td>v{t.get('strategy_version','?')}</td></tr>"
    trades_table = f"<table><tr><th>Time</th><th>Asset</th><th>Dir</th><th>Entry</th><th>Exit</th><th>PnL</th><th>Reason</th><th>Strategy</th></tr>{rows}</table>" if trades else "<p class='neutral'>No trades yet.</p>"

    hrows = ""
    for h in reversed(hypotheses):
        hrows += f"<tr><td>{h.get('ts','')[:19]}</td><td>v{h.get('strategy_version_from','?')} -> v{h.get('strategy_version_to','?')}</td><td>{h.get('changed_var','')}</td><td>{h.get('old_val','')}</td><td>{h.get('new_val','')}</td><td>{h.get('rationale') or h.get('hypothesis','')}</td></tr>"
    strategy_table = f"<table><tr><th>Time</th><th>Version</th><th>Variable</th><th>Old</th><th>New</th><th>Rationale</th></tr>{hrows}</table>" if hypotheses else "<p class='neutral'>No reflections yet.</p>"

    return HTML.format(cards=cards, trades_table=trades_table, strategy_table=strategy_table, strategy_yaml=strategy_text)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = build_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(html))
        self.end_headers()
        self.wfile.write(html)
    def log_message(self, *args): pass

if __name__ == "__main__":
    port = 5432
    print(f"Dashboard running at http://localhost:{port} — auto-refreshes every 60s")
    HTTPServer(("", port), Handler).serve_forever()
