#!/usr/bin/env python3
"""Smoke wrapper for the duel runner.

This intentionally requires --allow-placeholder-agents so local smoke tests do
not pretend Codex/Claude routing is live.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = REPO_ROOT / "benchmarks" / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test the duel runner.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8001")
    parser.add_argument("--allow-placeholder-agents", action="store_true")
    parser.add_argument("--max-steps", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.allow_placeholder_agents:
        raise RuntimeError("smoke_duel_runner.py requires --allow-placeholder-agents")

    synthetic_observation = {
        "participant_id": "player_1",
        "opponent_id": "player_2",
        "state_mode": "shared_full",
        "decision_interval_ms": 750,
        "state": {
            "player_1": {
                "opponent_relative_angle": 0,
                "opponent_distance": 300,
                "opponent_visible": True,
            }
        },
    }
    hook_check = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "agents" / "example_chase_agent.py")],
        input=json.dumps(synthetic_observation),
        text=True,
        capture_output=True,
        check=False,
    )
    if hook_check.returncode != 0:
        raise RuntimeError("example_chase_agent.py failed: " + hook_check.stderr)
    action = json.loads(hook_check.stdout)
    if action.get("participant_id") != "player_1":
        raise RuntimeError("example_chase_agent.py returned wrong participant_id")

    before = {path.name for path in RESULTS_ROOT.glob("run_*")} if RESULTS_ROOT.exists() else set()
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "doom_arena_duel_runner.py"),
        "--server-url",
        args.server_url,
        "--allow-placeholder-agents",
        "--player-1-agent-cmd",
        f"{sys.executable} {REPO_ROOT / 'scripts' / 'agents' / 'example_chase_agent.py'}",
        "--player-2-agent-cmd",
        f"{sys.executable} {REPO_ROOT / 'scripts' / 'agents' / 'example_noop_agent.py'}",
        "--max-steps",
        str(args.max_steps),
        "--no-open-browser",
        "--state-wait-timeout-seconds",
        "10",
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        time.sleep(0.1)
        after = {path.name for path in RESULTS_ROOT.glob("run_*")} if RESULTS_ROOT.exists() else set()
        new_runs = sorted(after - before)
        partial = []
        run_dir = None
        if new_runs:
            run_dir = RESULTS_ROOT / new_runs[-1]
            partial = [path.name for path in run_dir.iterdir()]
        if "arena_game_state.local.tsv has not been written yet" in completed.stderr and {"config.json", "events.jsonl"}.issubset(set(partial)):
            print(json.dumps({
                "ok": True,
                "status": "browser_required_for_state",
                "message": "Subprocess hook invocation passed and partial artifacts were written. Browser/WASM must be running for movement/state verification.",
                "partial_results_dir": str(run_dir) if run_dir is not None else "",
                "partial_artifacts": partial,
            }, indent=2))
            return 0
        raise RuntimeError(
            "duel runner smoke failed.\n"
            f"partial_artifacts={partial}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )

    results_dir = ""
    for line in completed.stdout.splitlines():
        if line.startswith("results_dir="):
            results_dir = line.split("=", 1)[1].strip()
            break
    if not results_dir:
        raise RuntimeError("duel runner did not print results_dir")

    run_dir = Path(results_dir)
    expected = [run_dir / "summary.json", run_dir / "events.jsonl", run_dir / "config.json"]
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        raise RuntimeError("duel runner did not write expected artifacts: " + ", ".join(missing))

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    print(json.dumps({"ok": True, "results_dir": str(run_dir), "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
