#!/usr/bin/env python3
"""Launch an isolated, recorded Codex controller for one arena smoke match."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from doom_arena_duel_prompts import shared_game_prompt


REPO = Path(__file__).resolve().parents[1]
NORMAL_TOOLS = [
    "set_participant_ready", "wait_for_match_start", "get_participant_observation",
    "set_participant_plan", "get_match_result", "stop_participant_intent",
]
JEV_TOOLS = [
    "prepare_jev_player", "run_jev_player", "resume_jev_player",
    "get_jev_player_status", "stop_jev_player",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--participant", choices=["player_1", "player_2"], required=True)
    parser.add_argument("--mode", choices=["regular", "jev_only"], default="regular")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt-file", type=Path)
    source.add_argument("--round-dir", type=Path, help="Round files; Jev receives a fixed token-free prompt")
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    log_dir = args.log_dir.resolve()
    if not log_dir.is_relative_to(REPO / "benchmarks" / "results"):
        parser.error("--log-dir must be inside benchmarks/results")
    if args.round_dir and args.mode == "jev_only":
        skill = (REPO / "plugins/jev-doom-player/skills/jev-doom-player/SKILL.md").read_text(encoding="utf-8")
        prompt = (
            shared_game_prompt() + "\n\nJEV HOST INTERFACE\n"
            f"Use these supplied Jev skill instructions:\n{skill}\n\n"
            f"Control only {args.participant} for exactly one current match. "
            f"Call prepare_jev_player exactly once with participant_id={args.participant}, "
            "agent_name=Jev Solo, control_mode=jev_only. "
            "Call run_jev_player with max_run_ms=45000. "
            "The controller sends the shared game instructions directly to Jev. "
            "If running, repeat without adding strategy until finished or failed. "
            "Never call resume_jev_player or author adaptive tactics. Never request, display or pass a controller token. "
            "Never reset the duel or control the other player. Use only the Jev MCP tools. "
            "Record actual terminal run_id, winner and reason. A transient state_not_ready or controller error is not a match result."
        )
    elif args.round_dir:
        prompt = (args.round_dir / f"{args.participant}_mcp_instructions.md").read_text(encoding="utf-8-sig")
        prompt += "\n\n" + (args.round_dir / "map_reference.md").read_text(encoding="utf-8-sig")
    else:
        prompt = args.prompt_file.read_text(encoding="utf-8-sig")
    codex = shutil.which("codex.exe") or shutil.which("codex")
    if not codex:
        parser.error("codex executable not found")
    if os.name == "nt" and not codex.lower().endswith(".exe"):
        native = Path(codex).parent / "node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
        if not native.is_file():
            parser.error("Native codex.exe required to preserve TOML argument quoting")
        codex = str(native)
    server = "jev-doom-player" if args.mode == "jev_only" else "doom-arena"
    script = (REPO / "plugins/jev-doom-player/scripts/jev_doom_mcp.py"
              if args.mode == "jev_only" else REPO / "scripts/doom_arena_mcp.py")
    config = {
        "model_reasoning_effort": "medium",
        "service_tier": "default",
        "approval_policy": "never",
        f"mcp_servers.{server}.command": sys.executable,
        f"mcp_servers.{server}.args": [str(script)],
        f"mcp_servers.{server}.cwd": str(REPO),
        f"mcp_servers.{server}.startup_timeout_sec": 20,
        f"mcp_servers.{server}.tool_timeout_sec": 120,
        f"mcp_servers.{server}.default_tools_approval_mode": "auto",
        f"mcp_servers.{server}.enabled_tools": JEV_TOOLS if args.mode == "jev_only" else NORMAL_TOOLS,
        f"mcp_servers.{server}.env.DOOM_ARENA_REPO_ROOT": str(REPO),
        f"mcp_servers.{server}.env.DOOM_ARENA_BASE_URL": args.base_url,
    }
    for tool in JEV_TOOLS if args.mode == "jev_only" else NORMAL_TOOLS:
        config[f"mcp_servers.{server}.tools.{tool}.approval_mode"] = "approve"
    command = [codex, "exec", "--ignore-user-config", "--disable", "plugins",
               "-s", "read-only", "-m", args.model, "-C", str(REPO), "--json"]
    for key, value in config.items():
        command.extend(["-c", key + "=" + json.dumps(value)])
    command.append("-")
    env = os.environ.copy()
    # The MCP gets the mode from prepare, never an inherited competing player.
    env.pop("JEV_DOOM_CONTROL_MODE", None)
    env.pop("JEV_DOOM_TELEMETRY_PATH", None)
    log_dir.mkdir(parents=True, exist_ok=True)
    prefix = log_dir / args.participant
    metadata = {"model": args.model, "participant": args.participant, "mode": args.mode}
    with prefix.with_suffix(".stdout.jsonl").open("xb") as stdout, prefix.with_suffix(".stderr.log").open("xb") as stderr:
        result = subprocess.run(command, input=prompt.encode("utf-8"), stdout=stdout,
                                stderr=stderr, cwd=REPO, env=env, check=False)
    metadata["exit_code"] = result.returncode
    prefix.with_suffix(".launch.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
