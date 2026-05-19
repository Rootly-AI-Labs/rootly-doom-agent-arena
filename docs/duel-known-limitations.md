# Duel Mode — Known Limitations

The published benchmark already documented a statistically significant `player_2` side bias (~74% win rate, see `analysis/results_overview.md`). Mirrored evaluation is the recommended way to control for it. The asymmetries below are why that bias exists.

## Player ability asymmetry

`player_1` is the real Doom console player — full `player_t` struct, weapons array, native pickup collision. It can grab the shotgun, rocket launcher, etc. from E1M8 and damage scales with the equipped weapon (35–105 per shotgun shot, 80+ per rocket).

`player_2` is a synthetic mobj with no `player_t` and no pickup logic. Its only attack is hardcoded in `ArenaDuel_Player2Attack` to do 5–15 damage per shot (pistol equivalent). It can never upgrade.

If `player_1` wins with implied per-hit damage > 15, it grabbed a heavier weapon — the match isn't a fair head-to-head.

## `player_1_shots_fired` is unreliable

`arena_duel_player1_shots_fired` only counts the manual-input debug channel. Autopilot-driven shots (the normal case) don't increment it. Use `damage_dealt` and `shots_hit` instead — both are derived from observed health drops on `player_2` and are accurate. `player_2_shots_fired` is fine.
