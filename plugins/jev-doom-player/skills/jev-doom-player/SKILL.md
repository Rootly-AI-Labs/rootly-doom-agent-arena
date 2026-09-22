---
name: jev-doom-player
description: Prepare, run, resume, inspect, or stop one Jev-controlled Doom Agent Arena participant. Use for the Jev-only and Jev-hybrid benchmark baselines, not for ordinary manual Doom MCP control.
---

# Jev Doom Player

Operate exactly one participant through the plugin's five MCP tools. The sidecar owns that participant's plan sequence and controller token; never request, display, or pass the token yourself.

## Workflow

1. Call `prepare_jev_player` with `participant_id`, a distinctive one- or two-word `agent_name`, and the requested `control_mode`:
   - `jev_only` offers Jev only legal actionable plans and executes its returned choice regardless of confidence. It uses deterministic fallback only when Jev fails or its choice is invalid or stale.
   - `jev_hybrid` returns uncertain or novel decisions to you as a strategic handoff.
2. Call `run_jev_player` with the fixed strategic objective requested for the benchmark. The directive is included in Jev's filtered state in both modes. In `jev_only`, keep the same predeclared directive for the whole run and do not add adaptive host tactics; in `jev_hybrid`, it may be updated after a handoff. The call is bounded; `status=running` means call it again to continue waiting, not that a second controller should be started.
3. Only in `jev_hybrid`, when status is `awaiting_opus`, inspect the returned filtered handoff packet and call `resume_jev_player` with a concise directive. Supply `override_plan` only when the user asks for a specific plan or the handoff clearly requires one; the sidecar validates it before submission. Never call `resume_jev_player` for `jev_only`; an `awaiting_opus` result there is a controller bug.
4. Use `get_jev_player_status` for inspection. Call `stop_jev_player` when asked to stop or when abandoning the match.

Do not expose the regular Doom planning MCP server to the same participant while this sidecar is active. Do not reset the duel or take control of the other participant unless the user separately requests it. Treat match writes as real external actions and stay within the participant selected during preparation.
