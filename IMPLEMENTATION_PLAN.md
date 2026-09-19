# On-Demand Jev Doom Player Plugin — Implementation Plan

## Goal

Build a client-neutral MCP sidecar that can be enabled for exactly one Doom Arena
participant. The sidecar uses deterministic code for legal route generation, Jev
for fast structured plan selection through OpenRouter, and a frontier LLM only
for strategic handoffs. Doom remains responsible for frame-level movement,
aiming, collision, and firing.

This is a planning-stack experiment, not a claim that Jev performs raw motor
control or that a hybrid has already beaten an Opus-only agent.

## V1 architecture decisions

- Package the sidecar as a personal Codex plugin named `jev-doom-player`, while
  keeping its MCP protocol client-neutral so the same server can later be
  configured in Claude Code.
- Keep the plugin dormant unless it is installed and enabled in the selected
  participant's client.
- Give any plugin-controlled participant only the plugin MCP server. Do not expose the
  regular Doom Arena planning MCP server in that client during V1. This makes the
  plugin the operational single writer without adding a new arena authentication
  and lease protocol.
- Treat this as tool-surface isolation, not a security boundary. The arena HTTP
  endpoint is local and unauthenticated; adversarial isolation would require a
  separate server-side authentication project.
- Reuse `DoomArenaClient` from `scripts/doom_arena_mcp.py` inside the sidecar.
  This is important because `DoomArenaClient.set_participant_plan()` accepts
  `engagement_policy`, but that field is currently absent from the public
  `participant_plan_schema()`.
- Load the selected participant's controller token inside the sidecar from the
  current run's `controller_tokens.json`. Never pass it through a model-visible
  tool argument or record it in telemetry.
- Use OpenRouter's dedicated Decisions API (`POST /api/alpha/decisions`), not
  Chat Completions, and pin the model ID to `typesafe/jev-1.13`. Record both
  the requested model and the canonical model returned with every run.
- Invoke Jev at most 1–2 times per second, and only following a material state
  trigger. A heartbeat is a maximum time between evaluations, not an unconditional
  per-frame or fixed-rate request.
- Use a supervised task inside the MCP server process. It may continue safe
  control between bounded tool calls, but it must not create a detached process
  or outlive the MCP session.
- Make `run_jev_player` and `resume_jev_player` bounded calls: 45 seconds by
  default and 55 seconds maximum, leaving margin below Codex's default 60-second
  MCP tool timeout.
- During an Opus handoff, continue only the last safe plan or deterministic safe
  fallback. Resume Jev decisions after Opus supplies a new directive or a
  validated override.
- Use the existing `player_1_model` or `player_2_model` run metadata field with
  the actual arm label (`jev_only` or `jev_hybrid`); do not introduce a parallel
  `controller_stack` field.
- Defer launcher and benchmark-harness automation until the manually enabled V1
  is reliable.

## Proposed MCP tools

### `prepare_jev_player`

Inputs: `participant_id`, optional `agent_name`, optional `control_mode`
(`jev_only` or `jev_hybrid`).

Loads the matching token internally, validates the pinned OpenRouter
configuration and key presence, loads the map graph, registers readiness, and
returns a filtered opening observation. It deliberately defers the first paid
OpenRouter request until `run_jev_player`. It does not start an unbounded
controller.

### `run_jev_player`

Inputs: optional `strategic_directive`, optional `max_run_ms`. The participant is
owned by the preceding `prepare_jev_player` call.

`strategic_directive` is used only by `jev_hybrid`. The `jev_only` baseline
ignores host-authored strategy so its decisions depend only on the sanitized
arena state and the fixed candidate criteria.

Starts or joins the supervised controller, submits the opening plan when needed,
and blocks until match completion, a hybrid-only strategic handoff, cancellation,
or the bounded return deadline. A deadline return reports `status=running`; the
in-process supervisor continues control until the next call or MCP shutdown.

### `resume_jev_player`

Hybrid-only inputs: `strategic_directive`, optional validated `override_plan`,
optional `max_run_ms`. This tool is never used by `jev_only`.

Resolves a handoff and re-enters the bounded wait. An Opus-authored override is
never sent directly to the arena: the sidecar normalizes and validates it first.

### `get_jev_player_status`

Returns controller mode, run ID, participant, sequence number, last accepted
plan, last Jev decision, current handoff reason, and match state. It returns no
controller token or unfiltered opponent state.

### `stop_jev_player`

Cancels the supervised task, stops further plan writes, clears sensitive
in-memory state, and returns a final status. MCP process shutdown and stdio EOF
must perform the same cleanup.

## Controller loop

1. Read local state from `GET /api/arena/state` without using the blocking
   `get_participant_observation` cycle.
2. Apply the existing `make_participant_observation()` fog-of-war filter.
3. Reduce the result through an explicit outbound-field whitelist.
4. Detect material changes:
   - route completion or stall;
   - line-of-sight change;
   - health threshold change;
   - pickup availability change;
   - visible or last-seen opponent cell change;
   - plan rejection;
   - maximum evaluation interval reached.
5. Generate deterministic, legal candidate plans.
6. Ask Jev `Choice` through OpenRouter Decisions to select one offered candidate.
   In `jev_only`, offer only legal actionable plans. In `jev_hybrid`, also offer
   `handoff_to_opus`.
7. In `jev_only`, submit Jev's valid returned choice regardless of confidence.
   In `jev_hybrid`, submit a high-confidence actionable choice using the plugin's
   single sequence allocator.
8. In `jev_hybrid`, retain a safe plan and return a compact handoff packet to
   Opus on low confidence or explicit handoff. In either mode, use deterministic
   fallback for transport, response, invalid-choice, or stale-choice failures.

Raw arena state, hidden enemy information, controller tokens, environment
secrets, and absolute local paths must never be sent to OpenRouter or TypeSafe.

## Deterministic candidate generation

The route engine must:

- build a graph from walkable blueprint cells;
- exclude blocked cells and cells violating the existing 24-unit wall-clearance
  requirement;
- avoid diagonal segments and known problematic adjacent waypoints;
- use deterministic shortest-path search with stable tie-breaking;
- compress collinear paths to at most eight waypoints;
- validate every candidate through the same route-normalization and validation
  code used by `DoomArenaClient` before presenting it to Jev.

Initial objective set:

- continue current plan;
- pursue visible opponent;
- move toward last-seen opponent;
- flank left;
- flank right;
- seek health;
- seek shotgun;
- disengage;
- hold position;
- hand off to Opus.

Every candidate contains a stable ID, objective, route, engagement policy,
concise reasoning, and a required first-person `plan_note` between 1 and 80
characters. Jev selects IDs; it does not generate coordinates, prose, or numeric
calculations.

## Failure and handoff policy

In `jev_hybrid`, trigger an Opus handoff for:

- Jev confidence below the configured threshold;
- explicit `handoff_to_opus` selection;
- no legal candidates;
- repeated stall or plan rejection;
- OpenRouter/TypeSafe timeout, malformed response, rate limit, or outage;
- a strategic situation not represented by the candidate library.

In `jev_only`, confidence is recorded for analysis but never overrides a valid
Jev selection, and `handoff_to_opus` is not offered. Deterministic fallback is
reserved for an API/transport failure, malformed or unknown choice, a choice
that became stale before submission, or the absence of any legal actionable
plan. Host-authored strategic directives and override plans are not part of this
standalone arm.

The confidence threshold is configuration calibrated from replay evaluation; it
is not a hardcoded or advertised 99% guarantee. Failures must not enter a rapid
retry loop. The handoff packet includes only filtered state, the current plan,
candidate summaries, confidence, and the reason for escalation.

## Plugin configuration

The personal plugin contains:

```text
jev-doom-player/
  .codex-plugin/plugin.json
  .mcp.json
  skills/jev-doom-player/SKILL.md
  scripts/jev_doom_mcp.py
  scripts/controller.py
  scripts/candidate_routes.py
  scripts/jev_adapter.py
  scripts/telemetry.py
  tests/
```

The manifest lists only components that exist. V1 requires no application UI or
lifecycle hook.

The packaged stdio MCP configuration forwards `OPENROUTER_API_KEY` using
`env_vars`; it never contains the key value. The development launcher may load
only allowlisted OpenRouter and arena settings from the repository's ignored
`.env`; installed clients should provide real environment variables. Configure `tool_timeout_sec` with
enough margin for the 55-second maximum, and set `approval_mode=auto` for the
run/resume tools through Codex's plugin-specific MCP settings. Validate the exact
packaged configuration against the installed Codex version before relying on it.

## Stage 0 — Safety and protocol contract

**Goal:** Freeze the state machine, outbound OpenRouter schema, tool contracts,
handoff reasons, process lifecycle, and telemetry schema.

**Changes:**

- Define controller modes: `idle`, `prepared`, `running`, `awaiting_opus`,
  `stopping`, `finished`, and `failed`.
- Define the exact filtered outbound payload, OpenRouter Decisions request, and maximum sizes.
- Specify supervisor cancellation on stop, match completion, stdio EOF, and
  client disconnect.
- Specify sequence-number recovery from the latest accepted arena plan.

**Success criteria:** No unspecified data can reach OpenRouter, and every controller
state has a bounded exit or recovery path.

**Tests:** Schema snapshots, token and secret redaction, fog-of-war fixtures,
state-machine transition tests, and cancellation tests.

**Status:** Complete for V1. Contracts, fog filtering, redaction, lifecycle, and
cancellation behavior are covered by automated tests.

## Stage 1 — Deterministic route candidate engine

**Goal:** Generate a small, useful set of legal tactical plans without Jev or an
LLM.

**Changes:** Implement map graph construction, wall clearance, objective scoring,
shortest paths, stable tie-breaking, path compression, candidate narration, and
final route validation.

**Success criteria:** Identical input produces identical candidates; the replay
corpus produces zero invalid candidates; every route contains at most eight
waypoints and every quip is 1–80 characters.

**Tests:** Blocked and unreachable cells, diagonals, wall clearance, adjacent
waypoint hazards, collinear compression, stable ordering, pickup availability,
and route-validation property tests.

**Status:** Implemented and unit verified. The deterministic engine is also
smoke-tested against the real arena blueprint; the larger replay gate remains a
benchmark prerequisite.

## Stage 2 — Jev decision adapter

**Goal:** Add a narrow, testable OpenRouter Decisions boundary around Jev `Choice`.

**Changes:** Pin `typesafe/jev-1.13`, define the Choice question/criteria schema,
parse probabilities and confidence, implement deadlines and backoff, and provide
a fake adapter for tests. Do not use Chat Completions or `response_format` for Jev.

**Success criteria:** Every response produces either a known candidate ID or an
explicit handoff; no network request contains fields outside the whitelist; the
returned canonical model remains inside the pinned Jev 1.13 family.

**Tests:** High and low confidence, optional probabilities/confidence, explicit
handoff, unknown ID, malformed JSON, timeout, rate limit, service outage, and
pinned-version mismatch. CI uses no live OpenRouter calls.

**Status:** Complete for V1. Offline contract tests pass and a live OpenRouter
Decisions smoke returned the pinned Jev 1.13 family.

## Stage 3 — Plugin and MCP server

**Goal:** Package the controller as an installable, dormant personal plugin.

**Changes:** Scaffold the manifest, skill, stdio MCP server, environment
forwarding, tool definitions, and installation metadata. Import or wrap
`DoomArenaClient` directly so engagement policy and existing route validation are
available even though the public plan tool schema omits that field.

**Success criteria:** Plugin validation passes; the MCP server initializes and
advertises only its own tools; missing keys and missing run metadata fail during
preflight; installing the plugin alone sends no arena or OpenRouter requests.

**Tests:** Manifest validation, MCP initialize/list/call framing, environment
forwarding, internal token loading, wrong-participant rejection, and dormant
installation.

**Status:** Complete for V1. The source and cached package validate, the personal
plugin is installed and enabled, and the installed stdio process advertises
exactly the five intended tools while remaining dormant before preparation.

## Stage 4 — Supervised live controller

**Goal:** Run one selected participant through a full match without a second plan
writer or control gaps at tool-call boundaries.

**Changes:** Implement the in-process supervisor, filtered observation loop,
trigger detection, sequence allocator, plan submission, safe fallback, and clean
shutdown. Configure the hybrid client with only the plugin MCP server.

**Success criteria:** The controller survives bounded `run` returns, continues a
safe plan while awaiting the next call, stops on MCP shutdown, never writes for
the other participant, and produces no sequence collisions.

**Tests:** Full local match, 55-second return, handoff wait, client disconnect,
stdio EOF, match restart, stale run ID, plan rejection, OpenRouter outage, and
plugin-disabled parity.

**Status:** Implemented and integration-smoke verified. The installed package
completed prepare, a real Jev decision, plan submission, handoff, stop, and
forced intent cleanup. Repeated full two-participant matches are still required
for the live gate.

## Stage 5 — Opus handoff and resume

**Goal:** Let Opus handle novel strategic decisions without bypassing the
sidecar's validation and sequence ownership.

**Changes:** Implement compact handoff packets, directive updates, optional
override plans, validation, and resume behavior. Keep deterministic safe control
active while Opus reasons.

**Success criteria:** A handoff never exposes hidden state or secrets; an invalid
override is rejected without disrupting the current safe plan; a valid override
is submitted once and Jev control resumes.

**Tests:** Low confidence, explicit handoff, repeated stall, invalid and valid
overrides, delayed response, duplicate resume, and canceled handoff.

**Status:** Implemented and unit verified. Low-confidence handoff, sanitized
packets, validated override submission, directive resume, invalid override, and
duplicate resume behavior are covered. A full live Opus handoff match remains
part of the live gate.

## Stage 6 — Telemetry and run labeling

**Goal:** Make the experiment reproducible without introducing a parallel run
metadata schema.

**Changes:** Set the selected participant's existing model field to the actual
arm (`jev_only` or `jev_hybrid`) when launching the manual run. Record sanitized
sidecar decision traces with run ID, participant, plugin and Jev versions,
filtered-state hash, trigger, candidate IDs, probabilities, confidence, selected
plan, latency, submission result, and handoff reason.

**Success criteria:** A result directory can be attributed to the correct
standalone or hybrid stack and analyzed decision by decision; traces contain no
token, key, raw hidden state, or absolute local path.

**Tests:** Trace serialization, redaction, interrupted writes, clock ordering,
model-field labeling, and joinability with existing match results.

**Status:** Implemented and unit verified for sanitized JSONL traces and stable
state hashes. Manual-run model labeling and result-directory analysis still need
validation during the repeated live-match gate.

## Stage 7 — Controlled benchmark

**Goal:** Determine whether Jev adds value beyond deterministic preprocessing and
whether Opus handoffs add value beyond Jev alone.

All arms use `hide_enemy_position=true`, identical arena settings, paired seeds,
swapped spawn positions, the same match limits, and pinned component versions.

Benchmark arms:

1. Existing Opus-only planner.
2. Deterministic candidates with Opus selection.
3. Jev selection with Opus handoffs.
4. Jev-only returned-Choice selection (validated as highest-probability when
   probability metadata is present), with deterministic fallback only on errors
   or invalid/stale choices.
5. Deterministic-only controller.

Metrics:

- paired wins and draws;
- damage dealt and received;
- accuracy;
- p50 and p95 decision latency;
- Jev request count and latency;
- Opus wakeups and handoff frequency;
- time controlled by Jev, fallback, and Opus;
- API cost;
- invalid or rejected plans;
- controller and API failures.

Run a pilot first to estimate variance and predeclare the full sample size and
decision thresholds. Do not describe the result as raw real-time LLM control:
every arm still relies on Doom's frame-level autopilot.

**Success criteria:** The paired experiment is reproducible and can distinguish
Jev's contribution from deterministic routing and Opus escalation.

**Tests:** Benchmark configuration validation, seed pairing, spawn swaps,
fog-of-war enforcement, version capture, and result completeness checks.

**Status:** Not started.

## Go/no-go gates

1. **Replay gate:** zero invalid candidates and zero outbound secret or fog leaks.
2. **Plugin gate:** clean validation/install, correct environment forwarding, and
   no activity while disabled.
3. **Live gate:** no sequence collisions, cross-player writes, orphan controller,
   or post-match submissions in repeated local matches.
4. **Pilot gate:** measured Jev latency, request volume, availability, and cost are
   acceptable enough to predeclare the full benchmark.
5. **Benchmark gate:** only after the preceding gates pass may the team make a
   performance or cost claim about the hybrid.

## Explicit V1 non-goals

- Raw frame, pixel, projectile, movement, or collision control by Jev.
- Jev-generated routes, coordinates, free-form plans, or quips.
- A claim that a 99% collision classifier exists.
- Server-side adversarial authentication or controller leases.
- Automatic installation into both player clients.
- Launcher or benchmark-harness toggles before the manual V1 is proven.
- Public performance claims before the controlled benchmark is complete.
