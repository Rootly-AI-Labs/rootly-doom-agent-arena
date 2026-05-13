# Control Architecture

Doom Agent Arena splits control between LLM tactical decisions and Doom-side real-time execution.

## High-Level MCP Agent Control

Codex and Claude do not drive frame-level controls. They send short-lived tactical policies with:

```text
set_participant_intent
```

Normal MCP tools:

```text
get_participant_observation
set_participant_intent
stop_participant_intent
get_match_result
get_duel_events
```

Supported intents:

```text
engage_opponent
strafe_attack
hold
search
```

Supported styles:

```text
balanced
aggressive
evasive
cautious
```

Optional tactical fields:

```text
strafe_direction: left | right | alternate | auto
movement_bias: direct | circle | evasive | cautious
fire_policy: hold_fire | only_when_aligned | burst_when_aligned | suppressive
distance_policy: close | maintain | kite
replan_if: lost_los, stuck, low_health, target_far, target_close
sequence_number
decision_cadence_ms
```

Typical fast-mode payload:

```json
{
  "participant_id": "player_1",
  "controller_token": "...",
  "intent": "strafe_attack",
  "style": "aggressive",
  "target_id": "player_2",
  "preferred_distance": 600,
  "aggression": 0.7,
  "duration_ms": 2500,
  "sequence_number": 1,
  "decision_cadence_ms": 750,
  "strafe_direction": "auto",
  "movement_bias": "circle",
  "fire_policy": "only_when_aligned",
  "distance_policy": "maintain",
  "replan_if": ["lost_los", "stuck", "low_health"]
}
```

## Doom-Side Low-Level Autopilot

Doom consumes the latest valid intent every tick and handles:

- movement
- strafing
- turning
- aiming
- firing gates
- line of sight checks
- distance management
- stuck recovery
- fallback to no movement when no active intent exists

The LLM does not send raw `forward`, `strafe`, `turn`, or `attack` commands during normal play.

## Sequence Numbers

Agents increment `sequence_number` every decision. Higher sequence numbers override older intents immediately. If sequence numbers are missing or tied, Doom falls back to issued-time freshness.

Expired intents do not reactivate.

## Ready Gate

The duel starts in:

```text
waiting_for_agents
```

Doom freezes both participants until both players have active intents. Once both first intents exist, the match changes to:

```text
combat
```

This keeps one agent from acting before the other is connected.

## Low-Level Debug Fallback

Low-level participant controls still exist for debugging:

```text
set_participant_input
stop_participant
```

They are hidden from MCP by default. For local debugging only, expose them with:

```powershell
$env:DOOM_ARENA_EXPOSE_LOW_LEVEL_MCP="1"
```

Normal comparisons should not use them.

## Local Rolling Controller

The orchestrator can run a local scripted rolling controller for smoke testing:

```powershell
py scripts\start_doom_arena_duel.py --keep-server --rolling-control
```

This is not a real Codex-vs-Claude comparison. Real comparison runs should omit `--rolling-control`.
