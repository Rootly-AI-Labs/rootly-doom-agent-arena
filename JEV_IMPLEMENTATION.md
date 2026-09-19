# Jev Quick Start

This is the shortest supported workflow for running either:

- **Jev-only** against a regular LLM.
- **Jev + LLM** against a regular LLM.

## The Simple Mental Model

Use two Codex windows:

| Window | Controls | What you paste |
|---|---|---|
| Window A | Jev participant, normally `player_1` | One token-free prompt from this guide |
| Window B | Regular LLM, normally `player_2` | The browser-generated Player 2 prompt |

Jev never receives a controller token. The plugin loads it internally.

The two Jev modes differ in only one important way:

| Mode | Behavior |
|---|---|
| `jev_only` | Jev's valid choice is executed directly. No host strategy or LLM handoff. |
| `jev_hybrid` | Jev handles normal choices; the host LLM handles low-confidence or explicit handoffs. |

## 1. Add the OpenRouter Key Once

Put this in the repository-root `.env` file:

```dotenv
OPENROUTER_API_KEY=<paste-your-openrouter-key-here>
OPENROUTER_DECISIONS_URL=https://openrouter.ai/api/alpha/decisions
OPENROUTER_MODEL=typesafe/jev-1.13
DOOM_ARENA_BASE_URL=http://127.0.0.1:8001
```

Do not paste the key into Codex, the browser, a prompt, or a committed file. A separate TypeSafe key is not needed.

The current implementation uses OpenRouter's Decisions endpoint, not Chat Completions.

Optional check that the plugin is installed:

```powershell
codex --enable plugins mcp get jev-doom-player --json
```

## 2. Start the Arena

From PowerShell:

```powershell
Set-Location 'C:\Users\muhha\OneDrive\Desktop\doom-test\rootly-doom-agent-arena'
.\scripts\start-docker.ps1
```

Open:

```text
http://127.0.0.1:8001/
```

Choose the available map, pickups, and number of matches, then click **Start Benchmark** once.

## 3. Start Window A: Jev

Open a fresh PowerShell window:

```powershell
Set-Location 'C:\Users\muhha\OneDrive\Desktop\doom-test\rootly-doom-agent-arena'
$repo = (Resolve-Path .).Path
$env:DOOM_ARENA_REPO_ROOT = $repo
$env:DOOM_ARENA_BASE_URL = 'http://127.0.0.1:8001'
Remove-Item Env:JEV_DOOM_CONTROL_MODE -ErrorAction SilentlyContinue
codex --enable plugins -C $repo -s read-only -a on-request -c 'mcp_servers.doom-arena.enabled=false' --no-alt-screen
```

Run `/mcp`. Confirm that `jev-doom-player` is connected and `doom-arena` is disabled or absent.

Now choose exactly one prompt.

### Option A: Jev-Only

Paste this into Window A:

```text
Use the jev-doom-player skill. Control only player_1. Call prepare_jev_player once with participant_id="player_1", agent_name="Jev Jockey", and control_mode="jev_only". Then call run_jev_player with max_run_ms=45000 and no strategic_directive. If status is running, call run_jev_player again until status is finished or failed. Never call resume_jev_player, never provide strategy, never control player_2, never request or display a controller token, and never use doom-arena tools.
```

That is the standalone baseline. The host Codex session only keeps the plugin running; it does not supply tactics.

### Option B: Jev + LLM

Paste this into Window A instead:

```text
Use the jev-doom-player skill. Control only player_1. Call prepare_jev_player once with participant_id="player_1", agent_name="Jev Hybrid", and control_mode="jev_hybrid". Call run_jev_player with strategic_directive="Prioritize useful weapon and health control, pursue visible opponents when advantageous, and disengage only when necessary." and max_run_ms=45000. If status is running, continue run_jev_player. If status is awaiting_opus, inspect the sanitized handoff, choose a concise new directive, and call resume_jev_player without an override plan unless a current legal route is genuinely required. Continue until finished or failed. Never control player_2, request or display a controller token, reset the duel, or use doom-arena tools.
```

The host can be Opus, GPT, Astra, or another LLM. `awaiting_opus` is only the legacy name for the hybrid handoff state.

## 4. Start Window B: The Opposing LLM

Open a second fresh PowerShell window:

```powershell
Set-Location 'C:\Users\muhha\OneDrive\Desktop\doom-test\rootly-doom-agent-arena'
$repo = (Resolve-Path .).Path
codex --disable plugins -m gpt-5.6-sol -C $repo -c 'mcp_servers.doom-arena.enabled=true' --no-alt-screen
```

Change `gpt-5.6-sol` to the model you want to test.

Run `/mcp`. Confirm that Window B has `doom-arena` and does not have `jev-doom-player`.

Click **Copy Player 2 Prompt** in the browser and paste it into Window B. Do not paste the Player 1 browser prompt into Window A; that prompt contains a controller token the Jev plugin already loads internally.

To put Jev on `player_2` instead, swap the participant IDs and give the regular LLM the browser-generated Player 1 prompt.

## Rules to Remember

1. One participant gets one controller. Never run Jev and regular Doom tools for the same participant.
2. `status=running` means call `run_jev_player` again in the same Window A.
3. Use `resume_jev_player` only for `jev_hybrid` after `status=awaiting_opus`.
4. For every automatically started new round, call `prepare_jev_player` again because the run ID changed.
5. After changing or reinstalling the plugin, open a fresh Codex session; do not use `codex resume`.
6. Use Jev telemetry to verify the real controller mode. The spectator nameplate may display the host Codex identity.

## Exact Recorded Jev-Only Example

This example comes from `run_03ecb904dc0b`; it is not hypothetical.

At `112.742` seconds into `duel_e1m8_blind_spawn`:

- Player 1 was near cell `Q08`, around `(-576, -342)`.
- Player 2 was no longer visible, but the controller retained the last-seen location.
- Reachable health and shotgun choices existed.
- The current plan used `avoid_until_target`.
- No handoff or host-authored strategy was available.

Jev received these choices:

| Option | Probability |
|---|---:|
| `disengage` | **44%** |
| `seek_health` | 21% |
| `hold_position` | 18% |
| `continue_current` | 9% |
| `seek_shotgun` | 4% |
| `pursue_last_seen` | 2% |
| `flank_left` | 1% |
| `flank_right` | 1% |

Jev returned:

```text
choice: disengage
confidence: 0.37
```

The controller executed it directly:

```text
Route: Q14 -> T14 -> T33 -> W33
Policy: hold_fire
Reason: This route increases distance from the known threat.
```

Player 1 immediately moved toward `Q14`. About `0.6` seconds later another Jev decision replaced the plan. Player 2 hit Player 1 at `113.342` seconds, and Jev selected `disengage` again.

Three seconds earlier, while Player 2 was visible, Jev was explicitly offered an attack:

```text
continue_current  29%  <- selected
seek_health       27%
disengage         16%
hold_position     16%
pursue_visible     8%
seek_shotgun       2%
flank_left         1%
flank_right        1%
```

`pursue_visible` was available, but Jev rated `continue_current` more highly.

Across the full run, Jev selected:

| Choice | Count |
|---|---:|
| `disengage` | 71 |
| `hold_position` | 27 |
| `seek_health` | 17 |
| `continue_current` | 11 |

There were 126 successful Jev decisions, five additional deterministic safety fallbacks, and no LLM handoff. Player 2 won on timeout with 150 health versus Jev's 134.

Local evidence:

- [`benchmarks/results/run_03ecb904dc0b/jev_player_1.jsonl`](benchmarks/results/run_03ecb904dc0b/jev_player_1.jsonl)
- [`benchmarks/results/session_a1d8c632f575/round_01_run_03ecb904dc0b/summary.json`](benchmarks/results/session_a1d8c632f575/round_01_run_03ecb904dc0b/summary.json)

These result paths are local and ignored by Git. Never commit controller-token files, generated participant prompts, or `.env`.

## If Something Fails

- **Missing API key:** confirm `.env` is in the repository root and Window A exported `DOOM_ARENA_REPO_ROOT`.
- **Waiting for agents:** make sure both windows prepared/submitted an opening plan.
- **Wrong tools in Window A:** relaunch it with `mcp_servers.doom-arena.enabled=false`.
- **Old plugin behavior:** reinstall/cache-bust the plugin and start a new Codex session.
