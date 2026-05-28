"""Entrypoint — parses goal.yaml and starts the loop."""
import argparse
import asyncio
import pathlib
import yaml

from hermes_trading.loop import run_loop

STATE_DIR = pathlib.Path("/app/state") if pathlib.Path("/app").exists() else pathlib.Path.home() / "hermes-trading" / "state"
GOAL_FILE = STATE_DIR / "goal.yaml"


def load_goal() -> dict:
    with open(GOAL_FILE) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Hermes Trading Worker")
    parser.add_argument("--asset", default=None, help="Override asset from goal.yaml")
    args = parser.parse_args()

    goal = load_goal()
    asset = args.asset or goal["asset"]

    print(f"Booting hermes-trading worker — asset={asset} mode=paper")
    asyncio.run(run_loop(asset=asset, goal=goal, state_dir=STATE_DIR))


if __name__ == "__main__":
    main()
