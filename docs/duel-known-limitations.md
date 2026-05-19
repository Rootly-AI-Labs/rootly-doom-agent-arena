# Duel Mode — Known Limitations

The two duel participants are NOT fully symmetric in the current build.
These gaps don't break the benchmark, but they affect how results
should be interpreted.

The original benchmark already documented a statistically significant
side bias (`player_2` won ~74% of rounds in the published runs —
see `analysis/results_overview.md` and
`analysis/model_vs_model_side_breakdown.md`). Mirrored evaluation
(each pair plays both side assignments) is the recommended way to
control for it. The asymmetry sources below are why that bias exists.

## 1. Player ability asymmetry

`player_1` is the real Doom console player. It has the full
`player_t` struct: a `weaponowned[]` array, per-type ammo, currently
equipped weapon, fire-rate cooldowns, and standard pickup-collision
handling. When `player_1` walks over the shotgun, chaingun, rocket
launcher, plasma rifle, or medikits scattered around E1M8, it picks
them up natively and damage scales with the equipped weapon.

`player_2` is a synthetic `MT_PLAYER` mobj spawned by arena code in
`ArenaDuel_SpawnPlayer2`. It has no `player_t`, no weapons array, no
pickup logic. Its only attack is the hardcoded
`ArenaDuel_Player2Attack` (see `src/doom/arena_duel.c`) which always
does `5 * (P_Random() % 3 + 1)` damage — the same formula as a Doom
pistol, but `player_2` can never upgrade past it.

**Practical impact:** in a match where `player_1` reaches a weapon
pickup first, it can land 35–105 damage shotgun blasts or 80+
splash-damage rockets against `player_2`'s 5–15 damage pistol shots.
This is positional luck, not strategy quality.

If you compare two model duels and `player_1` wins decisively, check
whether `player_1_shots_hit * average_pistol_damage` accounts for
the reported `player_1_damage_dealt`. If the implied per-hit damage
is much higher than 15, `player_1` was using a heavier weapon and
the match isn't a fair head-to-head.

## 2. `player_1_shots_fired` counter is unreliable

`arena_duel_player1_shots_fired` only increments via the low-level
manual-command path (`ArenaParticipantCommands_Command(PLAYER_1).attack`),
which is the debug channel for the `set_player_input` MCP tool.

In real duels, `player_1` fires via the autopilot, which sets
`cmd->buttons |= BT_ATTACK` directly on the ticcmd. Doom processes
that natively and fires the equipped weapon — but the arena counter
never sees those attacks.

**Practical impact:** a real-world duel will often show
`player_1_shots_fired: 0` in `summary.json` even when player_1
clearly engaged. Trust `damage_dealt` and `shots_hit` (both are
derived from observed health drops on `player_2`, not from command
channels) and treat `player_1_shots_fired` as a placeholder.

`player_2_shots_fired` is accurate — it's incremented inside
`ArenaDuel_Player2Attack` next to the actual `P_LineAttack` call.

## 3. Suggested fixes (out of scope for this branch)

- **For #1:** either strip weapon/ammo/health pickups from E1M8
  at level setup so neither side gets a mid-match upgrade, or
  promote `player_2` to a real `player_t` so Doom's native weapon
  pickup logic applies symmetrically.

- **For #2:** increment `arena_duel_player1_shots_fired` from
  `arena_player_control.c` when the autopilot pulses `BT_ATTACK`,
  or hook the increment into Doom's weapon-fire codepointer
  (`A_FirePistol`, `A_FireShotgun`, etc.).
