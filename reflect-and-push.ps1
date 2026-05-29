Set-Location 'C:\Users\User\hermes-trading'
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','User') + ';' + [System.Environment]::GetEnvironmentVariable('Path','Machine')
uv run python -m hermes_trading.reflect --fallback 2>> 'C:\Users\User\hermes-trading\state\reflect.log'
uv run python -m hermes_trading.export_csv 2>> 'C:\Users\User\hermes-trading\state\reflect.log'
git add state/strategy.yaml state/hypotheses.jsonl state/trades.jsonl state/heartbeat.json state/trades.csv state/hypotheses.csv state/strategy.csv
$diff = git diff --cached --name-only
if ($diff) {
    git commit -m 'Auto-reflect: strategy update'
    git push origin main
}