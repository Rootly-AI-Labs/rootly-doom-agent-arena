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
2. Only the latest neutral planner, `flat_v3`, is supported. Call `run_jev_player` with `max_run_ms` (normally 45000). The shared game prompt is supplied automatically in both modes. The call is bounded; `status=running` means call it again, not prepare again. No additional strategy-text input exists.
3. Only in `jev_hybrid`, when status is `awaiting_opus`, inspect the filtered handoff and call `resume_jev_player` with an optional validated `override_plan` and `max_run_ms`. Resuming without an override lets Jev reconsider without extra guidance. Never call resume for `jev_only`. Preserve the existing preparation; do not downgrade or re-prepare to change tool arguments.
4. Use `get_jev_player_status` for inspection. Call `stop_jev_player` when asked to stop or when abandoning the match.

Do not expose the regular Doom planning MCP server to the same participant while this sidecar is active. Do not reset the duel or take control of the other participant unless the user separately requests it. Treat match writes as real external actions and stay within the participant selected during preparation.
