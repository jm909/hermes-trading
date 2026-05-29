"""Local web dashboard — serves trade data, strategy history, and metrics."""
import json
import pathlib
import yaml
from http.server import HTTPServer, BaseHTTPRequestHandler

STATE_DIR = pathlib.Path(__file__).parent.parent / "state"

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes Trading Dashboard</title>
<meta http-equiv="refresh" content="60">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0a0e1a;
    color: #e2e8f0;
    min-height: 100vh;
  }
  header {
    background: linear-gradient(135deg, #1a1f35 0%, #0f1628 100%);
    border-bottom: 1px solid #2d3748;
    padding: 24px 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  header h1 {
    font-size: 26px;
    font-weight: 700;
    color: #fff;
    letter-spacing: -0.5px;
  }
  header h1 span { color: #4f9eff; }
  .badge {
    background: #1a3a2a;
    color: #4ade80;
    border: 1px solid #22543d;
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: 600;
  }
  .badge.paper { background: #1a2a3a; color: #60a5fa; border-color: #1e4070; }
  .container { max-width: 1400px; margin: 0 auto; padding: 32px 40px; }
  .cards {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 16px;
    margin-bottom: 40px;
  }
  .card {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 12px;
    padding: 20px 24px;
    transition: border-color 0.2s;
  }
  .card:hover { border-color: #374151; }
  .card-label {
    font-size: 12px;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 10px;
  }
  .card-value {
    font-size: 36px;
    font-weight: 700;
    color: #f9fafb;
    line-height: 1;
  }
  .card-value.pos { color: #34d399; }
  .card-value.neg { color: #f87171; }
  .card-value.blue { color: #60a5fa; }
  .card-sub {
    font-size: 12px;
    color: #6b7280;
    margin-top: 6px;
  }
  section { margin-bottom: 40px; }
  section h2 {
    font-size: 18px;
    font-weight: 600;
    color: #f1f5f9;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 1px solid #1f2937;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  section h2 .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #4f9eff;
    display: inline-block;
  }
  .table-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid #1f2937; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  thead th {
    background: #111827;
    color: #9ca3af;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 14px 16px;
    text-align: left;
    border-bottom: 1px solid #1f2937;
    white-space: nowrap;
  }
  tbody tr { border-bottom: 1px solid #111827; transition: background 0.15s; }
  tbody tr:hover { background: #111827; }
  tbody td { padding: 13px 16px; color: #d1d5db; vertical-align: middle; }
  tbody tr:last-child { border-bottom: none; }
  .pos { color: #34d399; font-weight: 600; }
  .neg { color: #f87171; font-weight: 600; }
  .tag {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
  }
  .tag.long { background: #1a3a2a; color: #34d399; }
  .tag.short { background: #3a1a1a; color: #f87171; }
  .tag.sl { background: #2a1a1a; color: #f87171; }
  .tag.tp { background: #1a2a1a; color: #34d399; }
  .strategy-box {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 20px 24px;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
  }
  .strategy-item { }
  .strategy-key { font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
  .strategy-val { font-size: 20px; font-weight: 700; color: #f9fafb; }
  .empty { color: #4b5563; font-size: 15px; padding: 32px; text-align: center; background: #111827; border-radius: 10px; border: 1px dashed #1f2937; }
  footer { text-align: center; color: #374151; font-size: 12px; padding: 24px; border-top: 1px solid #111827; margin-top: 20px; }
</style>
</head>
<body>
<header>
  <h1><span>Hermes</span> Trading Dashboard</h1>
  <div style="display:flex;gap:10px;align-items:center">
    <span class="badge paper">PAPER MODE</span>
    <span class="badge">LIVE</span>
  </div>
</header>
<div class="container">
  CARDS_PLACEHOLDER
  <section>
    <h2><span class="dot"></span>Recent Trades</h2>
    TRADES_PLACEHOLDER
  </section>
  <section>
    <h2><span class="dot" style="background:#a78bfa"></span>Strategy Evolution</h2>
    REFLECTIONS_PLACEHOLDER
  </section>
  <section>
    <h2><span class="dot" style="background:#fbbf24"></span>Current Strategy</h2>
    STRATEGY_PLACEHOLDER
  </section>
</div>
<footer>Auto-refreshes every 60 seconds &bull; BTC/USDT &bull; Hermes Trading Agent</footer>
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
    strategy, _ = load_strategy()

    total_pnl = sum(t.get("pnl_pct", 0) for t in trades)
    wins = [t for t in trades if t.get("pnl_pct", 0) > 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0
    pnl_class = "pos" if total_pnl >= 0 else "neg"

    cards = f"""
    <div class="cards">
      <div class="card">
        <div class="card-label">Total Trades</div>
        <div class="card-value blue">{len(trades)}</div>
        <div class="card-sub">{len(wins)} wins / {len(trades)-len(wins)} losses</div>
      </div>
      <div class="card">
        <div class="card-label">Total PnL</div>
        <div class="card-value {pnl_class}">{total_pnl:+.2f}%</div>
        <div class="card-sub">paper mode</div>
      </div>
      <div class="card">
        <div class="card-label">Win Rate</div>
        <div class="card-value {'pos' if win_rate >= 50 else 'neg'}">{win_rate:.0f}%</div>
        <div class="card-sub">of closed trades</div>
      </div>
      <div class="card">
        <div class="card-label">Strategy</div>
        <div class="card-value blue">v{strategy.get('version','?')}</div>
        <div class="card-sub">RSI &lt; {strategy.get('entry',{}).get('threshold','?')}</div>
      </div>
      <div class="card">
        <div class="card-label">Reflections</div>
        <div class="card-value blue">{len(hypotheses)}</div>
        <div class="card-sub">variables evolved</div>
      </div>
    </div>"""

    if trades:
        rows = ""
        for t in reversed(trades[-50:]):
            pnl = t.get("pnl_pct", 0)
            cls = "pos" if pnl > 0 else "neg"
            direction = t.get("direction", "")
            reason = t.get("exit_reason", "")
            dir_tag = f'<span class="tag {direction}">{direction.upper()}</span>'
            reason_tag = f'<span class="tag sl">STOP LOSS</span>' if "stop" in reason else f'<span class="tag tp">{reason.upper()}</span>'
            rows += f"""<tr>
              <td style="color:#6b7280">{t.get('ts','')[:19].replace('T',' ')}</td>
              <td><strong>{t.get('asset','')}</strong></td>
              <td>{dir_tag}</td>
              <td>${t.get('entry_price',0):,.2f}</td>
              <td>${t.get('exit_price',0):,.2f}</td>
              <td class="{cls}">{pnl:+.2f}%</td>
              <td>{reason_tag}</td>
              <td style="color:#6b7280">v{t.get('strategy_version','?')}</td>
            </tr>"""
        trades_html = f'<div class="table-wrap"><table><thead><tr><th>Time</th><th>Asset</th><th>Direction</th><th>Entry</th><th>Exit</th><th>PnL</th><th>Reason</th><th>Strategy</th></tr></thead><tbody>{rows}</tbody></table></div>'
    else:
        trades_html = '<div class="empty">No trades yet — waiting for RSI signal</div>'

    if hypotheses:
        hrows = ""
        for h in reversed(hypotheses):
            old_v = h.get('strategy_version_from','?')
            new_v = h.get('strategy_version_to','?')
            hrows += f"""<tr>
              <td style="color:#6b7280">{h.get('ts','')[:19].replace('T',' ')}</td>
              <td><span style="color:#a78bfa">v{old_v}</span> &rarr; <span style="color:#60a5fa">v{new_v}</span></td>
              <td><code style="background:#1f2937;padding:2px 8px;border-radius:4px;font-size:13px">{h.get('changed_var','')}</code></td>
              <td style="color:#f87171">{h.get('old_val','')}</td>
              <td style="color:#34d399">{h.get('new_val','')}</td>
              <td style="color:#9ca3af;font-size:13px">{h.get('rationale') or h.get('hypothesis','')}</td>
            </tr>"""
        reflections_html = f'<div class="table-wrap"><table><thead><tr><th>Time</th><th>Version</th><th>Variable</th><th>Old</th><th>New</th><th>Rationale</th></tr></thead><tbody>{hrows}</tbody></table></div>'
    else:
        reflections_html = '<div class="empty">No reflections yet</div>'

    entry = strategy.get("entry", {})
    strategy_html = f"""<div class="strategy-box">
      <div class="strategy-item"><div class="strategy-key">Indicator</div><div class="strategy-val">{entry.get('indicator','rsi').upper()}</div></div>
      <div class="strategy-item"><div class="strategy-key">Threshold</div><div class="strategy-val">{entry.get('threshold','?')}</div></div>
      <div class="strategy-item"><div class="strategy-key">Direction</div><div class="strategy-val" style="color:#34d399">{entry.get('direction','?').upper()}</div></div>
      <div class="strategy-item"><div class="strategy-key">Stop Loss</div><div class="strategy-val" style="color:#f87171">{strategy.get('stop_loss_pct','?')}%</div></div>
      <div class="strategy-item"><div class="strategy-key">Position Size</div><div class="strategy-val">{strategy.get('position_size_r','?')}R</div></div>
      <div class="strategy-item"><div class="strategy-key">Version</div><div class="strategy-val" style="color:#60a5fa">v{strategy.get('version','?')}</div></div>
    </div>"""

    return (HTML
            .replace("CARDS_PLACEHOLDER", cards)
            .replace("TRADES_PLACEHOLDER", trades_html)
            .replace("REFLECTIONS_PLACEHOLDER", reflections_html)
            .replace("STRATEGY_PLACEHOLDER", strategy_html))


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
