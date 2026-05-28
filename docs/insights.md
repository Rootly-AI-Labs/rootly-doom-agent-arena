# Insights

## Route planning is the current control direction

The current default interface asks models to choose grid-cell routes with `set_participant_plan` instead of picking from fixed lane/category actions. This gives the model more planning freedom while still keeping Doom responsible for frame-level movement, collision, aiming, and firing.

## Keep repeated observations compact

The static map belongs in the initial prompt. Repeated observations should stay focused on live state: own position, visibility, health, tactical status, and pickups. This tests whether the model can remember and use the map without flooding every turn with the full blueprint.

## Fog of war makes memory matter

With fog enabled, models cannot rely on perfect opponent coordinates. They must remember the map, infer likely movement, and use last-seen/visibility state to decide where to route next.

## Pickups create useful strategy pressure

Health packs and the center shotgun let us test whether models can trade off healing, upgrading, denying resources, and forcing fights.

## Cross-round learning is useful when enabled

Cross-round recap can show whether models adapt after losing, getting stuck, or choosing bad routes. This is useful for evaluating longer-horizon agent behavior, but it should be measured separately from single-round map-memory performance.

## Current coordinate-route findings

- Model reasoning can be correct even when movement execution is wrong. A model may choose a sensible route around walls while the Doom-side controller cuts the route short, restarts waypoints, or moves into a blocker. Logs should separate planning quality from autopilot execution quality.
- Coordinate routes expose spatial reasoning better than strategy presets. `set_participant_plan` forces the model to choose actual route cells, making it easier to audit whether it understands walls, pickups, spawn position, and likely opponent movement.
- The static ASCII map works best as prompt memory, not repeated observation payload. This keeps observations small while still testing whether the model can use map structure from chat memory.
- Fog of war makes map memory meaningful. The model has to remember last contact, infer likely enemy movement, and decide which area to clear instead of chasing perfect opponent coordinates.
- Pickups add strategic diversity. Health packs and the center shotgun let agents choose between fighting, healing, denying the weapon, controlling center, or baiting around cover.
- Path trails are important debugging evidence. They quickly show whether the agent is exploring, looping, camping, or getting stuck without requiring every MCP log line to be inspected.
- Short reasoning is valuable. One sentence is usually enough to distinguish a bad plan from a good plan with bad execution or a good plan that was replaced too quickly.
- Frequent replanning can hurt route completion. If a model overwrites its route too often, it can look like spinning or indecision even when individual route choices are reasonable.
- Grid labels make behavior easier to audit. Cell names are easier to compare across prompt, logs, and tactical overlay than raw Doom coordinates.
- The setup now tests more than combat strength: spatial memory, route planning, resource prioritization, fog-of-war inference, tool-call discipline, adaptation after failed movement, and combat timing.
