"""Score trades against goal.yaml — returns float in [-1, +1]."""
import math
from typing import List


def score(trades: List[dict], goal: dict) -> float:
    """
    Composite score: weighted average of return, drawdown, and Sharpe components.
    Returns a value in [-1, +1].
    """
    if not trades:
        return 0.0

    target_return = goal.get("target_return_30d", 0.05)
    max_drawdown = goal.get("max_drawdown", 0.08)
    min_sharpe = goal.get("min_sharpe", 1.2)
    failure_below = goal.get("failure_below", -0.04)

    pnl_values = [t.get("pnl_pct", 0) / 100 for t in trades]
    realised_return = sum(pnl_values)

    # Return component: sigmoid-scaled against target
    if realised_return >= target_return:
        return_score = min(1.0, realised_return / target_return)
    else:
        return_score = max(-1.0, (realised_return - target_return) / target_return)

    # Drawdown component
    cumulative = 0.0
    peak = 0.0
    max_dd_seen = 0.0
    for pnl in pnl_values:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd_seen:
            max_dd_seen = dd

    if max_dd_seen <= max_drawdown:
        dd_score = 1.0 - (max_dd_seen / max_drawdown)
    else:
        dd_score = -1.0 * min(1.0, (max_dd_seen - max_drawdown) / max_drawdown)

    # Sharpe component
    if len(pnl_values) > 1:
        mean_pnl = sum(pnl_values) / len(pnl_values)
        variance = sum((p - mean_pnl) ** 2 for p in pnl_values) / (len(pnl_values) - 1)
        std_pnl = math.sqrt(variance) if variance > 0 else 1e-9
        sharpe = (mean_pnl / std_pnl) * math.sqrt(252)
    else:
        sharpe = 0.0

    if sharpe >= min_sharpe:
        sharpe_score = min(1.0, sharpe / min_sharpe - 1.0 + 1.0)
    else:
        sharpe_score = max(-1.0, (sharpe - min_sharpe) / min_sharpe)

    composite = 0.5 * return_score + 0.3 * dd_score + 0.2 * sharpe_score

    # Hard floor
    if realised_return < failure_below:
        composite = min(composite, -0.8)

    return round(max(-1.0, min(1.0, composite)), 4)
