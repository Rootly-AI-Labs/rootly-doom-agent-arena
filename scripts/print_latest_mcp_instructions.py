#!/usr/bin/env python3
"""Print latest Doom Arena MCP instruction files and paste-ready prompts."""

from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = REPO_ROOT / "benchmarks" / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print latest Doom Arena MCP instruction paths.")
    parser.add_argument("--print-prompts", action="store_true", help="Print paste-ready Codex/Claude prompt text.")
    return parser.parse_args()


def latest_run_dir() -> Path:
    candidates = [path for path in RESULTS_ROOT.glob("run_*") if path.is_dir()]
    if not candidates:
        raise RuntimeError(f"No run directories found under {RESULTS_ROOT}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def require_file(path: Path) -> Path:
    if not path.exists():
        raise RuntimeError(f"Missing expected file: {path}")
    return path


def main() -> int:
    args = parse_args()
    run_dir = latest_run_dir()
    player_1 = require_file(run_dir / "player_1_mcp_instructions.md")
    player_2 = require_file(run_dir / "player_2_mcp_instructions.md")
    tokens = require_file(run_dir / "controller_tokens.json")
    config = require_file(run_dir / "config.json")

    print(f"latest_run_dir={run_dir}")
    print(f"player_1_mcp_instructions={player_1}")
    print(f"player_2_mcp_instructions={player_2}")
    print(f"controller_tokens={tokens}")
    print(f"config={config}")

    if args.print_prompts:
        print("\n--- Paste into Codex ---")
        print(
            "You are controlling player_1 in Doom Arena Duel. "
            f"Read and follow these instructions exactly: {player_1}. "
            "Run the MCP loop using your assigned instructions until the match finishes."
        )
        print("\n--- Paste into Claude ---")
        print(
            "You are controlling player_2 in Doom Arena Duel. "
            f"Read and follow these instructions exactly: {player_2}. "
            "Run the MCP loop using your assigned instructions until the match finishes."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
