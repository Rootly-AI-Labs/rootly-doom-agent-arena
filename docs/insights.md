# Insights

## Route planning is the current control direction

The current default interface asks models to choose grid-cell routes with `set_participant_plan` instead of picking from fixed lane/category actions. This gives the model more planning freedom while still keeping Doom responsible for frame-level movement, collision, aiming, and firing.

## Keep repeated observations compact

The static map belongs in the initial prompt. Repeated observations should stay focused on live state: own position, visibility, health, tactical status, route bounds, and pickups. This tests whether the model can remember and use the map without flooding every turn with the full blueprint.

## Fog of war makes memory matter

With fog enabled, models cannot rely on perfect opponent coordinates. They must remember the map, infer likely movement, and use last-seen/visibility state to decide where to route next.

## Pickups create useful strategy pressure

Health packs and the center shotgun let us test whether models can trade off healing, upgrading, denying resources, and forcing fights.

## Cross-round learning is useful when enabled

Cross-round recap can show whether models adapt after losing, getting stuck, or choosing bad routes. This is useful for evaluating longer-horizon agent behavior, but it should be measured separately from single-round map-memory performance.
