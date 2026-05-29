"""Entrypoint — parses goal.yaml and starts the loop + reflection cycle."""
import argparse
import asyncio
import pathlib
import subprocess
import sys
import traceback
import yaml

from hermes_trading.loop import run_loop
from hermes_trading.reflect import fallback_reflect

STATE_DIR = pathlib.Path("/app/state") if pathlib.Path("/app").exists() else pathlib.Path.home() / "hermes-trading" / "state"
GOAL_FILE = STATE_DIR / "goal.yaml"
REFLECTION_INTERVAL = 3600  # every hour


def load_goal() -> dict:
    with open(GOAL_FILE) as f:
        return yaml.safe_load(f)


def push_to_github():
    import os
    token = os.getenv("GIT_TOKEN")
    if not token:
        return
    try:
        repo = STATE_DIR.parent
        remote = f"https://{token}@github.com/jm909/hermes-trading.git"
        subprocess.run(["git", "config", "user.email", "bot@hermes-trading"], cwd=repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "hermes-bot"], cwd=repo, capture_output=True)
        subprocess.run(["git", "add", "state/"], cwd=repo, capture_output=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo, capture_output=True)
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", "reflect: strategy update"], cwd=repo, capture_output=True)
            subprocess.run(["git", "push", remote, "main"], cwd=repo, capture_output=True, timeout=30)
            print("[reflect] pushed to GitHub", flush=True)
    except Exception as e:
        print(f"[reflect] push failed: {e}", flush=True)


async def run_reflection_cycle():
    await asyncio.sleep(REFLECTION_INTERVAL)  # wait 1 hour before first reflection
    while True:
        try:
            print("[reflect] running hourly reflection...", flush=True)
            fallback_reflect()
            push_to_github()
        except Exception as exc:
            print(f"[reflect] error: {exc}", flush=True)
            traceback.print_exc()
        await asyncio.sleep(REFLECTION_INTERVAL)


async def run_all(asset, goal):
    await asyncio.gather(
        run_loop(asset=asset, goal=goal, state_dir=STATE_DIR),
        run_reflection_cycle(),
    )


def main():
    parser = argparse.ArgumentParser(description="Hermes Trading Worker")
    parser.add_argument("--asset", default=None)
    args = parser.parse_args()

    print(f"STATE_DIR={STATE_DIR} exists={STATE_DIR.exists()}", flush=True)

    try:
        goal = load_goal()
    except Exception as exc:
        print(f"FATAL: could not load goal.yaml: {exc}", flush=True)
        traceback.print_exc()
        sys.exit(1)

    asset = args.asset or goal["asset"]
    print(f"Booting hermes-trading worker — asset={asset} mode=paper", flush=True)
    print(f"Reflection cycle: every {REFLECTION_INTERVAL//60} minutes", flush=True)

    try:
        asyncio.run(run_all(asset=asset, goal=goal))
    except Exception as exc:
        print(f"FATAL: worker crashed: {exc}", flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
