# Insights

This document tracks important findings from building and testing Doom Arena with LLM agents.

## LLM control behavior

- Faster tool calls do not automatically produce better gameplay.
- Clean MCP tool use matters, but the strongest competitive behavior also depends on tactical adaptation.
- Models can follow high-level strategy schemas more reliably than large parameter-heavy intent schemas.
- Compact observations reduce decision overhead and make it easier to compare model control quality.
- Requiring the model to choose from a small set of categories and actions reduces prompt/token load while still preserving meaningful tactical choice.

## Hierarchical strategy control

The current default control mode uses `set_participant_strategy`.

This works better than asking models to manually set many low-level tactical fields because:

- the model chooses intent at the strategy level,
- the server expands the strategy into Doom autopilot controls,
- invalid category/action combinations can be rejected cleanly,
- logs can show the model-facing decision directly,
- the Doom engine still receives the same full intent path it already understands.

## Fog of war

Fog of war is important for testing real agent behavior.

Without fog of war, models can rely on shared opponent coordinates instead of maintaining map memory or searching. With fog of war enabled:

- each model always knows its own state,
- opponent position is hidden unless visible,
- visibility is directional,
- one player seeing the other does not automatically reveal that information back,
- models must infer where the opponent might be based on prior contact, map layout, and recent observations.

This better tests whether the model can track uncertainty instead of only reacting to perfect state.

## Map memory

The starting MCP prompt includes the static ASCII map once.

This is useful because:

- the model can reason about the map without receiving the full layout every observation,
- repeated observations stay compact,
- weaker models are not given a constantly refreshed full world model,
- stronger models can benefit from remembering structure across the chat.

The observation should provide live state, not a full repeated map dump.

## Cross-round learning

Cross-round learning recap is currently disabled in the default UI, but the concept is useful.

When enabled, it should let models adapt across rounds by summarizing what happened before, for example:

- which strategies failed,
- whether the model got stuck or spun,
- whether it repeatedly pushed into bad positions,
- where the opponent tended to appear,
- whether aggressive or evasive play worked better,
- which player won and why.

This helps test whether agents can adapt from bad moves made in earlier rounds rather than repeating the same failed behavior.

The recap should stay compact. It should not become a full replay or perfect memory oracle.

## Tactical overlay findings

The tactical overlay is for human debugging, not model input.

Important findings:

- The overlay should match actual Doom automap geometry as closely as possible.
- Manually drawn tactical geometry can be misleading if it diverges from game collision/visibility.
- Player trails help diagnose whether agents are exploring, stuck, circling, or snapping between states.
- Trail rendering needs snap filtering because marker detection can occasionally produce one-frame bad points.

## Benchmarking lesson

Doom Arena is useful because it exposes more than task success.

It also reveals:

- decision latency,
- MCP latency,
- stale strategy behavior,
- invalid tool calls,
- recovery from mistakes,
- spatial memory,
- ability to act under partial information,
- ability to keep using tools cleanly over time.

This makes it a better agent benchmark than a single final score alone.
