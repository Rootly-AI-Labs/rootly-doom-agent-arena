# Control Architecture

Doom Agent Arena splits control between LLM tactical decisions and Doom-side real-time execution.

## High-Level MCP Agent Control

The two chat agents do not drive frame-level controls. They send short-lived tactical policies with:

```text
set_participant_intent
```

Normal MCP tools:

```text
set_participant_ready
wait_for_match_start
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
                 | hold_direction | switch_if_hit
movement_bias: direct | circle | evasive | cautious
fire_policy: hold_fire | only_when_aligned | burst_when_aligned | suppressive
distance_policy: close | maintain | kite
aim_tolerance: optional degrees
fire_burst_ms: optional burst length for burst_when_aligned
min_fire_alignment: optional stricter aim gate in degrees
min_distance / max_distance: optional spacing bounds
retreat_if_closer_than / push_if_farther_than: optional explicit spacing triggers
los_lost_action: turn_left | turn_right | advance_last_seen | hold_angle | sweep
stuck_recovery_strategy: back_up | turn_left | turn_right | strafe_out | default
movement_primitive: advance | retreat | strafe_left | strafe_right
                  | circle_left | circle_right | hold_position
turn_policy: auto | turn_to_enemy | sweep_left | sweep_right | hold_angle | face_last_seen
navigation_target: none | opponent | last_seen_enemy | center | left_lane | right_lane | keep_distance
fire_mode: auto | hold_fire | fire_when_aligned | single_shot | burst | suppressive
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
  "duration_ms": 25000,
  "sequence_number": 1,
  "decision_cadence_ms": 750,
  "strafe_direction": "auto",
  "movement_bias": "circle",
  "fire_policy": "only_when_aligned",
  "distance_policy": "maintain",
  "aim_tolerance": 10,
  "fire_burst_ms": 250,
  "min_fire_alignment": 8,
  "min_distance": 350,
  "max_distance": 900,
  "retreat_if_closer_than": 300,
  "push_if_farther_than": 1000,
  "los_lost_action": "sweep",
  "stuck_recovery_strategy": "strafe_out",
  "turn_policy": "turn_to_enemy",
  "navigation_target": "opponent",
  "fire_mode": "fire_when_aligned",
  "replan_if": ["lost_los", "stuck", "low_health"]
}
```

`movement_primitive` is intentionally omitted in the normal example. It is a one-policy override for cases where the current observation specifically calls for exact primitive movement. Repeating a primitive such as `circle_left` or `circle_right` after losing line of sight can create spin or reacquire failures; on lost LOS, prefer `search`, `fire_policy=hold_fire`, and `navigation_target=last_seen_enemy`.

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
- stale-intent continuation when a chatbot response is slow
- fallback to no movement only when there is no retained MCP intent, or after intents are manually cleared

The LLM does not send raw `forward`, `strafe`, `turn`, or `attack` commands during normal play.
The new tactical fields move more of the decision boundary into MCP-authored policy: the LLM can now specify fire tolerance, fire mode, spacing bounds, LOS-loss behavior, stuck recovery style, strafe persistence, turn policy, navigation target, and one explicit movement primitive, while Doom still converts those policies into frame-level inputs.

## Sequence Numbers

Agents increment `sequence_number` every decision. Higher sequence numbers override older intents immediately. If sequence numbers are missing or tied, Doom falls back to issued-time freshness.

Expired rows do not reactivate after a newer sequence number has replaced them. If the latest MCP intent reaches its nominal expiry before the chatbot sends a replacement, Doom keeps executing that last LLM-authored policy with `intent_status=stale` until a newer intent arrives or `stop_participant_intent` clears it.

## Chatbot Refresh Loop

In the normal browser/chatbot flow, each agent should immediately observe again after sending an intent, then send the next updated intent with a higher `sequence_number`.

Doom continues executing the current intent between chat tool calls. When the next valid intent arrives, the higher `sequence_number` makes it override the previous one immediately. In chatbot mode, expiry is treated as a stale-policy warning rather than a no-policy stop, which prevents visible freezes while the chat client is still producing the next tool call. Normal combat leases should be about `20000` to `25000` ms; opening intents use a longer `60000` ms lease so both participants can pass the ready gate.

## MCP Timing Stats

The browser/server flow writes `stats.json` for each duel round. Multi-round browser sessions use `benchmarks/results/session_*/round_NN_run_*/stats.json`; one-off debug runs may still use `benchmarks/results/run_*/stats.json`. The file records local MCP tool-call latency, completion/error status, and whether an in-flight call was overlapped by a later call for the same participant. Browser-created chatbot runs also accept telemetry from stdio MCP clients, so both Player 1 and Player 2 calls can be correlated to accepted intent rows.

For accepted `set_participant_intent` calls, it also records intent lifecycle timing:

- `superseded_before_expiry`
- `effective_duration_ms`
- `unused_duration_ms`
- `gap_after_previous_expiry_ms`
- `average_gap_after_intent_expiry_ms`
- `intents_continued_stale_after_expiry`
- `average_stale_intent_extension_ms`
- `average_inferred_chat_decision_latency_ms`

These fields are meant to help tune `Intent Duration MS`: large unused durations mean new intents are arriving well before expiry, while large stale extensions mean the chatbot is taking longer than the configured intent lease. `latency_ms` is the local HTTP MCP call latency; inferred chat decision latency approximates the time from an observation response to the next intent request.

The server mirrors the current duel event TSV into `events.jsonl` in the active run or round folder whenever browser event logs arrive. It also rejects new participant intents after the match state reaches `phase=finished`, so delayed chatbot responses do not pollute finished-run logs.

## Multi-Round Sessions

The browser can keep several rounds under one session folder:

```text
benchmarks/results/session_*/round_01_run_*
benchmarks/results/session_*/round_02_run_*
```

`Start Duel` creates a new session. `Next Round` is only valid after the current round reaches `phase=finished`; it keeps the same session id, increments the round number, creates a new run id, and generates fresh prompts and controller tokens. Prompts are round-scoped, so agents must use the newly generated instructions after every `Next Round`.

## Ready Gate

The duel starts in:

```text
waiting_for_agents
```

Doom freezes both participants until both players have signaled readiness with `set_participant_ready` and both players have submitted an opening `set_participant_intent`. The opening intents are armed but not executed while the phase is still `waiting_for_agents`. Once both opening intents are present, the match changes to:

```text
combat
```

This keeps one agent from acting before the other is connected or before the other agent has chosen its first high-level action.

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
