//
// Doom Agent Arena participant autopilot decision logic.
//

#include <math.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#include "arena_participant_autopilot.h"

#define ARENA_AUTOPILOT_AIM_TURN_DEGREES 6
#define ARENA_AUTOPILOT_AIM_ATTACK_DEGREES 8
#define ARENA_AUTOPILOT_AIM_SUPPRESSIVE_DEGREES 24
#define ARENA_AUTOPILOT_MS_PER_TICK 28
#define ARENA_AUTOPILOT_STUCK_TICKS 8
#define ARENA_AUTOPILOT_MIN_DISTANCE 128
#define ARENA_AUTOPILOT_LOW_HEALTH 35
#define ARENA_AUTOPILOT_STUCK_BURST_WINDOW_TICKS 42
#define ARENA_AUTOPILOT_STUCK_BURST_THRESHOLD 4
#define ARENA_AUTOPILOT_STUCK_COOLDOWN_TICKS 84
#define ARENA_AUTOPILOT_ROUTE_REACHED_DISTANCE 32

static arena_participant_autopilot_debug_t arena_autopilot_debug[ARENA_PARTICIPANT_COUNT];
static char arena_route_cursor_intent_id[ARENA_PARTICIPANT_COUNT][64];
static int arena_route_cursor_index[ARENA_PARTICIPANT_COUNT];
static int arena_autopilot_last_health[ARENA_PARTICIPANT_COUNT] = {-1, -1};
static int arena_autopilot_last_strafe_direction[ARENA_PARTICIPANT_COUNT] = {-1, 1};
static int arena_autopilot_stuck_burst_count[ARENA_PARTICIPANT_COUNT] = {0, 0};
static int arena_autopilot_last_stuck_tick[ARENA_PARTICIPANT_COUNT] = {-100000, -100000};
static int arena_autopilot_unstick_cooldown_until_tick[ARENA_PARTICIPANT_COUNT] = {0, 0};

static int ClampUnit(int value)
{
    if (value < -1)
    {
        return -1;
    }
    if (value > 1)
    {
        return 1;
    }
    return value;
}

static int AbsInt(int value)
{
    return value < 0 ? -value : value;
}

static int IntentFieldEquals(const char *value, const char *expected)
{
    return value != NULL && expected != NULL && !strcmp(value, expected);
}

static int NormalizeAngleError(int value)
{
    while (value > 180)
    {
        value -= 360;
    }
    while (value < -180)
    {
        value += 360;
    }
    return value;
}

static int DoomAngleToPoint(int from_x, int from_y, int to_x, int to_y)
{
    double radians;
    int degrees;

    radians = atan2((double) (to_y - from_y), (double) (to_x - from_x));
    degrees = (int) (radians * 180.0 / 3.14159265358979323846);
    while (degrees < 0)
    {
        degrees += 360;
    }
    while (degrees >= 360)
    {
        degrees -= 360;
    }
    return degrees;
}

static int SquaredDistance(int x1, int y1, int x2, int y2)
{
    int dx;
    int dy;

    dx = x2 - x1;
    dy = y2 - y1;
    return dx * dx + dy * dy;
}

static void CopyField(char *dest, size_t dest_size, const char *value)
{
    if (dest_size == 0)
    {
        return;
    }

    if (value == NULL)
    {
        dest[0] = '\0';
        return;
    }

    strncpy(dest, value, dest_size - 1);
    dest[dest_size - 1] = '\0';
}

static void SetFallbackDebug(arena_participant_id_t participant, const char *reason)
{
    if (participant < 0 || participant >= ARENA_PARTICIPANT_COUNT)
    {
        return;
    }

    memset(&arena_autopilot_debug[participant],
           0,
           sizeof(arena_autopilot_debug[participant]));
    CopyField(arena_autopilot_debug[participant].controller_mode,
              sizeof(arena_autopilot_debug[participant].controller_mode),
              "low_level_command");
    CopyField(arena_autopilot_debug[participant].intent,
              sizeof(arena_autopilot_debug[participant].intent),
              "none");
    CopyField(arena_autopilot_debug[participant].intent_status,
              sizeof(arena_autopilot_debug[participant].intent_status),
              "inactive");
    CopyField(arena_autopilot_debug[participant].autopilot_action,
              sizeof(arena_autopilot_debug[participant].autopilot_action),
              "none");
    CopyField(arena_autopilot_debug[participant].autopilot_reason,
              sizeof(arena_autopilot_debug[participant].autopilot_reason),
              reason == NULL ? "no_active_intent" : reason);
    CopyField(arena_autopilot_debug[participant].strafe_direction,
              sizeof(arena_autopilot_debug[participant].strafe_direction),
              "auto");
    CopyField(arena_autopilot_debug[participant].movement_bias,
              sizeof(arena_autopilot_debug[participant].movement_bias),
              "direct");
    CopyField(arena_autopilot_debug[participant].fire_policy,
              sizeof(arena_autopilot_debug[participant].fire_policy),
              "only_when_aligned");
    CopyField(arena_autopilot_debug[participant].distance_policy,
              sizeof(arena_autopilot_debug[participant].distance_policy),
              "maintain");
    CopyField(arena_autopilot_debug[participant].los_lost_action,
              sizeof(arena_autopilot_debug[participant].los_lost_action),
              "sweep");
    CopyField(arena_autopilot_debug[participant].stuck_recovery_strategy,
              sizeof(arena_autopilot_debug[participant].stuck_recovery_strategy),
              "default");
    arena_autopilot_debug[participant].movement_primitive[0] = '\0';
    CopyField(arena_autopilot_debug[participant].turn_policy,
              sizeof(arena_autopilot_debug[participant].turn_policy),
              "auto");
    CopyField(arena_autopilot_debug[participant].navigation_target,
              sizeof(arena_autopilot_debug[participant].navigation_target),
              "opponent");
    CopyField(arena_autopilot_debug[participant].fire_mode,
              sizeof(arena_autopilot_debug[participant].fire_mode),
              "auto");
    arena_autopilot_debug[participant].executed_los_lost_action[0] = '\0';
    arena_autopilot_debug[participant].executed_stuck_recovery_strategy[0] = '\0';
    arena_autopilot_debug[participant].executed_movement_primitive[0] = '\0';
    arena_autopilot_debug[participant].executed_turn_policy[0] = '\0';
    arena_autopilot_debug[participant].executed_navigation_target[0] = '\0';
    arena_autopilot_debug[participant].executed_fire_mode[0] = '\0';
    arena_autopilot_debug[participant].sequence_number = -1;
    arena_autopilot_debug[participant].decision_cadence_ms = 0;
    arena_autopilot_debug[participant].issued_at_ms = 0;
    arena_autopilot_debug[participant].expires_at_ms = 0;
    arena_autopilot_debug[participant].replan_recommended = false;
    arena_autopilot_debug[participant].replan_reasons[0] = '\0';
}

static arena_participant_autopilot_command_t NoopCommand(const char *reason)
{
    arena_participant_autopilot_command_t command;

    memset(&command, 0, sizeof(command));
    CopyField(command.action, sizeof(command.action), "noop");
    CopyField(command.reason, sizeof(command.reason), reason);
    return command;
}

static int TurnForAimError(int aim_error)
{
    if (AbsInt(aim_error) <= ARENA_AUTOPILOT_AIM_TURN_DEGREES)
    {
        return 0;
    }

    return aim_error > 0 ? 1 : -1;
}

static int TurnForPolicy(const arena_participant_autopilot_input_t *input,
                         int aim_error)
{
    if (input == NULL
        || input->intent.turn_policy[0] == '\0'
        || IntentFieldEquals(input->intent.turn_policy, "auto")
        || IntentFieldEquals(input->intent.turn_policy, "turn_to_enemy")
        || IntentFieldEquals(input->intent.turn_policy, "face_last_seen"))
    {
        return TurnForAimError(aim_error);
    }

    if (IntentFieldEquals(input->intent.turn_policy, "sweep_left"))
    {
        return -1;
    }

    if (IntentFieldEquals(input->intent.turn_policy, "sweep_right"))
    {
        return 1;
    }

    if (IntentFieldEquals(input->intent.turn_policy, "hold_angle"))
    {
        return 0;
    }

    return TurnForAimError(aim_error);
}

static const char *EffectiveFireModeForIntent(const arena_participant_intent_t *intent)
{
    if (intent == NULL)
    {
        return "fire_when_aligned";
    }

    if (intent->fire_mode[0] != '\0'
        && !IntentFieldEquals(intent->fire_mode, "auto"))
    {
        return intent->fire_mode;
    }

    if (IntentFieldEquals(intent->fire_policy, "hold_fire"))
    {
        return "hold_fire";
    }

    if (IntentFieldEquals(intent->fire_policy, "burst_when_aligned"))
    {
        return "burst";
    }

    if (IntentFieldEquals(intent->fire_policy, "suppressive"))
    {
        return "suppressive";
    }

    return "fire_when_aligned";
}

static const char *EffectiveFireMode(const arena_participant_autopilot_input_t *input)
{
    return input == NULL
        ? "fire_when_aligned"
        : EffectiveFireModeForIntent(&input->intent);
}

static int AttackAllowed(const arena_participant_autopilot_input_t *input, int aim_error)
{
    int abs_error;
    int tolerance;
    int burst_ticks;
    const char *fire_mode;

    fire_mode = EffectiveFireMode(input);
    if (IntentFieldEquals(fire_mode, "hold_fire"))
    {
        return false;
    }

    if (!input->line_of_sight || input->self_ammo <= 0 || input->opponent_health <= 0)
    {
        return false;
    }

    abs_error = AbsInt(aim_error);
    if (input->intent.min_fire_alignment > 0)
    {
        tolerance = input->intent.min_fire_alignment;
    }
    else if (input->intent.aim_tolerance > 0)
    {
        tolerance = input->intent.aim_tolerance;
    }
    else if (IntentFieldEquals(fire_mode, "suppressive"))
    {
        tolerance = ARENA_AUTOPILOT_AIM_SUPPRESSIVE_DEGREES;
    }
    else
    {
        tolerance = ARENA_AUTOPILOT_AIM_ATTACK_DEGREES;
    }

    if (IntentFieldEquals(fire_mode, "suppressive"))
    {
        return abs_error <= tolerance;
    }

    if (IntentFieldEquals(fire_mode, "burst"))
    {
        burst_ticks = input->intent.fire_burst_ms > 0
            ? input->intent.fire_burst_ms / ARENA_AUTOPILOT_MS_PER_TICK
            : 9;
        if (burst_ticks < 1)
        {
            burst_ticks = 1;
        }
        if (burst_ticks > 35)
        {
            burst_ticks = 35;
        }

        return abs_error <= tolerance
            && (input->tick % (burst_ticks * 2 + 3)) < burst_ticks;
    }

    if (IntentFieldEquals(fire_mode, "single_shot"))
    {
        return abs_error <= tolerance && (input->tick % 8) == 0;
    }

    return abs_error <= tolerance;
}

static int PreferredDistance(const arena_participant_autopilot_input_t *input)
{
    if (input->intent.preferred_distance > 0)
    {
        return input->intent.preferred_distance;
    }

    return 600;
}

static int RetreatThreshold(const arena_participant_autopilot_input_t *input,
                            int fallback)
{
    if (input->intent.retreat_if_closer_than > 0)
    {
        return input->intent.retreat_if_closer_than;
    }

    if (input->intent.min_distance > 0)
    {
        return input->intent.min_distance;
    }

    return fallback;
}

static int PushThreshold(const arena_participant_autopilot_input_t *input,
                         int fallback)
{
    if (input->intent.push_if_farther_than > 0)
    {
        return input->intent.push_if_farther_than;
    }

    if (input->intent.max_distance > 0)
    {
        return input->intent.max_distance;
    }

    return fallback;
}

static int AlternatingDirection(int tick, int period)
{
    if (period <= 0)
    {
        period = 20;
    }

    return ((tick / period) % 2) == 0 ? 1 : -1;
}

static int TacticalStrafeDirection(const arena_participant_autopilot_input_t *input,
                                   int period)
{
    arena_participant_id_t participant;
    int direction;

    participant = input->participant;
    if (participant < 0 || participant >= ARENA_PARTICIPANT_COUNT)
    {
        participant = ARENA_PARTICIPANT_PLAYER_1;
    }

    if (IntentFieldEquals(input->intent.strafe_direction, "left"))
    {
        arena_autopilot_last_strafe_direction[participant] = -1;
        return -1;
    }

    if (IntentFieldEquals(input->intent.strafe_direction, "right"))
    {
        arena_autopilot_last_strafe_direction[participant] = 1;
        return 1;
    }

    if (IntentFieldEquals(input->intent.strafe_direction, "hold_direction"))
    {
        direction = arena_autopilot_last_strafe_direction[participant];
        if (direction == 0)
        {
            direction = participant == ARENA_PARTICIPANT_PLAYER_1 ? -1 : 1;
        }
        return direction;
    }

    if (IntentFieldEquals(input->intent.strafe_direction, "switch_if_hit"))
    {
        direction = arena_autopilot_last_strafe_direction[participant];
        if (direction == 0)
        {
            direction = participant == ARENA_PARTICIPANT_PLAYER_1 ? -1 : 1;
        }
        if (arena_autopilot_last_health[participant] > 0
            && input->self_health < arena_autopilot_last_health[participant])
        {
            direction = -direction;
        }
        arena_autopilot_last_health[participant] = input->self_health;
        arena_autopilot_last_strafe_direction[participant] = direction;
        return direction;
    }

    direction = AlternatingDirection(input->tick, period);
    arena_autopilot_last_strafe_direction[participant] = direction;
    arena_autopilot_last_health[participant] = input->self_health;
    return direction;
}

static int CombatIntent(const arena_participant_autopilot_input_t *input)
{
    return IntentFieldEquals(input->intent.intent, "engage_opponent")
        || IntentFieldEquals(input->intent.intent, "strafe_attack");
}

static int IntentIsStale(const arena_participant_autopilot_input_t *input)
{
    if (input == NULL)
    {
        return false;
    }

    return IntentFieldEquals(input->intent.status, "stale");
}

static int ParticipantIndexOrDefault(const arena_participant_autopilot_input_t *input)
{
    if (input == NULL
        || input->participant < 0
        || input->participant >= ARENA_PARTICIPANT_COUNT)
    {
        return ARENA_PARTICIPANT_PLAYER_1;
    }

    return (int) input->participant;
}

static int InStuckCooldown(const arena_participant_autopilot_input_t *input)
{
    int participant;

    participant = ParticipantIndexOrDefault(input);
    return input != NULL && input->tick < arena_autopilot_unstick_cooldown_until_tick[participant];
}

static void TrackStuckRecoveryBurst(const arena_participant_autopilot_input_t *input)
{
    int participant;
    int delta_ticks;

    if (input == NULL)
    {
        return;
    }

    participant = ParticipantIndexOrDefault(input);
    delta_ticks = input->tick - arena_autopilot_last_stuck_tick[participant];

    if (delta_ticks <= ARENA_AUTOPILOT_STUCK_BURST_WINDOW_TICKS)
    {
        arena_autopilot_stuck_burst_count[participant]++;
    }
    else
    {
        arena_autopilot_stuck_burst_count[participant] = 1;
    }

    arena_autopilot_last_stuck_tick[participant] = input->tick;

    if (arena_autopilot_stuck_burst_count[participant] >= ARENA_AUTOPILOT_STUCK_BURST_THRESHOLD)
    {
        arena_autopilot_unstick_cooldown_until_tick[participant] =
            input->tick + ARENA_AUTOPILOT_STUCK_COOLDOWN_TICKS;
        arena_autopilot_stuck_burst_count[participant] = 0;
    }
}

static int ReplanTriggerEnabled(const arena_participant_autopilot_input_t *input,
                                const char *trigger)
{
    const char *cursor;
    size_t trigger_len;

    if (input == NULL || trigger == NULL || input->intent.replan_if[0] == '\0')
    {
        return false;
    }

    cursor = input->intent.replan_if;
    trigger_len = strlen(trigger);
    while (*cursor != '\0')
    {
        while (*cursor == ',')
        {
            cursor++;
        }

        if (!strncmp(cursor, trigger, trigger_len)
            && (cursor[trigger_len] == '\0' || cursor[trigger_len] == ','))
        {
            return true;
        }

        cursor = strchr(cursor, ',');
        if (cursor == NULL)
        {
            break;
        }
    }

    return false;
}

static void AppendReason(char *dest, size_t dest_size, const char *reason)
{
    size_t length;

    if (dest_size == 0 || reason == NULL || reason[0] == '\0')
    {
        return;
    }

    length = strlen(dest);
    if (length >= dest_size - 1)
    {
        return;
    }

    if (dest[0] != '\0')
    {
        strncat(dest, ",", dest_size - strlen(dest) - 1);
    }
    strncat(dest, reason, dest_size - strlen(dest) - 1);
}

static void ApplyReplanHints(const arena_participant_autopilot_input_t *input,
                             arena_participant_autopilot_command_t *command)
{
    int preferred_distance;

    if (input == NULL || command == NULL)
    {
        return;
    }

    preferred_distance = PreferredDistance(input);
    command->replan_recommended = false;
    command->replan_reasons[0] = '\0';

    if (ReplanTriggerEnabled(input, "lost_los")
        && CombatIntent(input)
        && !input->line_of_sight)
    {
        AppendReason(command->replan_reasons,
                     sizeof(command->replan_reasons),
                     "lost_los");
    }

    if (ReplanTriggerEnabled(input, "stuck") && command->stuck_recovery)
    {
        AppendReason(command->replan_reasons,
                     sizeof(command->replan_reasons),
                     "stuck");
    }

    if (ReplanTriggerEnabled(input, "low_health")
        && input->self_health > 0
        && input->self_health < ARENA_AUTOPILOT_LOW_HEALTH)
    {
        AppendReason(command->replan_reasons,
                     sizeof(command->replan_reasons),
                     "low_health");
    }

    if (ReplanTriggerEnabled(input, "target_far")
        && input->distance > preferred_distance + preferred_distance / 2)
    {
        AppendReason(command->replan_reasons,
                     sizeof(command->replan_reasons),
                     "target_far");
    }

    if (ReplanTriggerEnabled(input, "target_close")
        && input->distance < preferred_distance / 2)
    {
        AppendReason(command->replan_reasons,
                     sizeof(command->replan_reasons),
                     "target_close");
    }

    command->replan_recommended = command->replan_reasons[0] != '\0';
}

static void ClampCommand(arena_participant_autopilot_command_t *command)
{
    command->forward = ClampUnit(command->forward);
    command->strafe = ClampUnit(command->strafe);
    command->turn = ClampUnit(command->turn);
    command->attack = command->attack ? true : false;
    command->use = false;
}

static void ApplyNavigationTarget(const arena_participant_autopilot_input_t *input,
                                  arena_participant_autopilot_command_t *command,
                                  int aim_error)
{
    int center_x;

    if (input == NULL || command == NULL)
    {
        return;
    }

    if (input->intent.navigation_target[0] == '\0'
        || IntentFieldEquals(input->intent.navigation_target, "none")
        || IntentFieldEquals(input->intent.navigation_target, "opponent")
        || IntentFieldEquals(input->intent.navigation_target, "keep_distance"))
    {
        return;
    }

    if (IntentFieldEquals(input->intent.navigation_target, "last_seen_enemy"))
    {
        if (!input->line_of_sight)
        {
            command->forward = 1;
            command->turn = TurnForPolicy(input, aim_error);
            CopyField(command->action,
                      sizeof(command->action),
                      command->attack ? "nav_last_seen_enemy+attack" : "nav_last_seen_enemy");
        }
        return;
    }

    if (IntentFieldEquals(input->intent.navigation_target, "left_lane"))
    {
        command->strafe = -1;
        CopyField(command->action,
                  sizeof(command->action),
                  command->attack ? "nav_left_lane+attack" : "nav_left_lane");
    }
    else if (IntentFieldEquals(input->intent.navigation_target, "right_lane"))
    {
        command->strafe = 1;
        CopyField(command->action,
                  sizeof(command->action),
                  command->attack ? "nav_right_lane+attack" : "nav_right_lane");
    }
    else if (IntentFieldEquals(input->intent.navigation_target, "center"))
    {
        center_x = (input->self_x + input->opponent_x) / 2;
        if (AbsInt(input->self_x - center_x) > 48)
        {
            command->strafe = input->self_x < center_x ? 1 : -1;
        }
        if (!input->line_of_sight && command->forward == 0)
        {
            command->forward = 1;
        }
        CopyField(command->action,
                  sizeof(command->action),
                  command->attack ? "nav_center+attack" : "nav_center");
    }
}

static int ApplyRoutePlan(const arena_participant_autopilot_input_t *input,
                          arena_participant_autopilot_command_t *command)
{
    int i;
    int participant_index;
    int target_x;
    int target_y;
    int route_error;
    int route_abs_error;
    int reached_distance_sq;

    if (input == NULL
        || command == NULL
        || input->intent.route_waypoint_count <= 0)
    {
        return false;
    }

    participant_index = input->participant;
    if (participant_index < 0 || participant_index >= ARENA_PARTICIPANT_COUNT)
    {
        participant_index = ARENA_PARTICIPANT_PLAYER_1;
    }
    if (strcmp(arena_route_cursor_intent_id[participant_index], input->intent.intent_id))
    {
        CopyField(arena_route_cursor_intent_id[participant_index],
                  sizeof(arena_route_cursor_intent_id[participant_index]),
                  input->intent.intent_id);
        arena_route_cursor_index[participant_index] = 0;
    }
    if (arena_route_cursor_index[participant_index] < 0)
    {
        arena_route_cursor_index[participant_index] = 0;
    }
    if (arena_route_cursor_index[participant_index] >= input->intent.route_waypoint_count)
    {
        arena_route_cursor_index[participant_index] = input->intent.route_waypoint_count - 1;
    }

    reached_distance_sq = ARENA_AUTOPILOT_ROUTE_REACHED_DISTANCE
        * ARENA_AUTOPILOT_ROUTE_REACHED_DISTANCE;

    i = arena_route_cursor_index[participant_index];
    while (i < input->intent.route_waypoint_count)
    {
        target_x = input->intent.route_x[i];
        target_y = input->intent.route_y[i];
        if (SquaredDistance(input->self_x, input->self_y, target_x, target_y) > reached_distance_sq)
        {
            break;
        }
        i++;
    }
    arena_route_cursor_index[participant_index] = i;

    if (i >= input->intent.route_waypoint_count)
    {
        command->forward = 0;
        command->strafe = 0;
        command->turn = TurnForPolicy(input, command->aim_error);
        CopyField(command->action,
                  sizeof(command->action),
                  command->attack ? "route_complete+attack" : "route_complete");
        CopyField(command->reason,
                  sizeof(command->reason),
                  input->intent.plan_reasoning[0] == '\0'
                    ? "route plan complete"
                    : input->intent.plan_reasoning);
        return true;
    }

    route_error = NormalizeAngleError(DoomAngleToPoint(input->self_x,
                                                       input->self_y,
                                                       target_x,
                                                       target_y)
                                      - input->self_angle);
    route_abs_error = AbsInt(route_error);
    command->route_waypoint_active = true;
    command->route_target_x = target_x;
    command->route_target_y = target_y;
    command->route_waypoint_index = i + 1;
    command->route_waypoint_count = input->intent.route_waypoint_count;
    /*
     * Route movement uses world-space waypoint thrust in the Doom-side
     * controller, so view angle does not need to point at the waypoint to move
     * correctly.  If the opponent is visible, keep the aim/turn policy on the
     * opponent so route following can still deal damage instead of firing while
     * looking at the next path cell.
     */
    command->turn = input->line_of_sight
        ? TurnForPolicy(input, command->aim_error)
        : TurnForAimError(route_error);

    /*
     * Route plans are waypoint-following commands, not aim-only combat
     * commands.  The previous route steering stopped all translation when the
     * next waypoint was more than ~85 degrees off-angle.  On grid routes with
     * many 90-degree turns this made actors rotate in place, trigger stuck
     * recovery, and appear to execute one tiny step at a time.  Keep lateral
     * movement active while turning so the player arcs toward the next waypoint
     * instead of freezing between cells.
     */
    /*
     * Drive toward the waypoint in local movement space instead of treating
     * the waypoint like an aiming target.  This makes the route behave closer
     * to coordinate following:
     *   - target ahead: move forward
     *   - target side-on: strafe
     *   - target behind: reverse
     *
     * Turning still happens, but translation does not stop just because the
     * target is not centered in the view.
     */
    if (route_abs_error <= 60)
    {
        command->forward = 1;
    }
    else if (route_abs_error >= 120)
    {
        command->forward = -1;
    }
    else
    {
        command->forward = 0;
    }
    command->strafe = route_abs_error > 20 && route_abs_error < 170
        ? (route_error > 0 ? 1 : -1)
        : 0;
    snprintf(command->action,
             sizeof(command->action),
             command->attack ? "route_waypoint+attack" : "route_waypoint");
    snprintf(command->reason,
             sizeof(command->reason),
             "wp=%d/%d target=(%d,%d) %s",
             i + 1,
             input->intent.route_waypoint_count,
             target_x,
             target_y,
             input->intent.plan_reasoning[0] == '\0'
                ? "following MCP route plan"
                : input->intent.plan_reasoning);
    return true;
}

static void ApplyStrictSpacing(const arena_participant_autopilot_input_t *input,
                               arena_participant_autopilot_command_t *command)
{
    int retreat_distance;
    int push_distance;

    if (input == NULL || command == NULL || input->distance <= 0)
    {
        return;
    }

    retreat_distance = RetreatThreshold(input, 0);
    push_distance = PushThreshold(input, 0);

    if (retreat_distance > 0 && input->distance < retreat_distance)
    {
        command->forward = -1;
        if (command->strafe == 0 && CombatIntent(input))
        {
            command->strafe = TacticalStrafeDirection(input, 16);
        }
        CopyField(command->action,
                  sizeof(command->action),
                  command->attack ? "spacing_retreat+attack" : "spacing_retreat");
    }
    else if (push_distance > 0 && input->distance > push_distance)
    {
        command->forward = 1;
        CopyField(command->action,
                  sizeof(command->action),
                  command->attack ? "spacing_push+attack" : "spacing_push");
    }
}

static arena_participant_autopilot_command_t FinalizeCommand(
    const arena_participant_autopilot_input_t *input,
    arena_participant_autopilot_command_t *command)
{
    if (strncmp(command->action, "primitive_", 10)
        && ApplyRoutePlan(input, command))
    {
        ClampCommand(command);
        ApplyReplanHints(input, command);
        return *command;
    }
    ApplyNavigationTarget(input, command, command->aim_error);
    ApplyStrictSpacing(input, command);
    ClampCommand(command);
    ApplyReplanHints(input, command);
    return *command;
}

static void ApplyLosLostAction(const arena_participant_autopilot_input_t *input,
                               arena_participant_autopilot_command_t *command,
                               int aim_error)
{
    if (IntentFieldEquals(input->intent.los_lost_action, "turn_left"))
    {
        command->turn = -1;
        command->forward = 0;
        CopyField(command->action, sizeof(command->action), "lost_los_turn_left");
    }
    else if (IntentFieldEquals(input->intent.los_lost_action, "turn_right"))
    {
        command->turn = 1;
        command->forward = 0;
        CopyField(command->action, sizeof(command->action), "lost_los_turn_right");
    }
    else if (IntentFieldEquals(input->intent.los_lost_action, "advance_last_seen"))
    {
        command->turn = TurnForPolicy(input, aim_error);
        command->forward = 1;
        CopyField(command->action, sizeof(command->action), "lost_los_advance_last_seen");
    }
    else if (IntentFieldEquals(input->intent.los_lost_action, "hold_angle"))
    {
        command->turn = 0;
        command->forward = 0;
        command->strafe = 0;
        CopyField(command->action, sizeof(command->action), "lost_los_hold_angle");
    }
    else
    {
        command->turn = AlternatingDirection(input->tick, 24);
        command->forward = ((input->tick / 35) % 3) == 0 ? 1 : 0;
        CopyField(command->action, sizeof(command->action), "lost_los_sweep");
    }
}

static arena_participant_autopilot_command_t MovementPrimitiveCommand(
    const arena_participant_autopilot_input_t *input,
    int aim_error)
{
    arena_participant_autopilot_command_t command;

    command = NoopCommand("movement_primitive");
    command.active = true;
    command.turn = TurnForPolicy(input, aim_error);
    command.attack = AttackAllowed(input, aim_error);
    command.aim_error = aim_error;

    if (IntentFieldEquals(input->intent.movement_primitive, "advance"))
    {
        command.forward = 1;
        CopyField(command.action, sizeof(command.action), command.attack ? "primitive_advance+attack" : "primitive_advance");
    }
    else if (IntentFieldEquals(input->intent.movement_primitive, "retreat"))
    {
        command.forward = -1;
        CopyField(command.action, sizeof(command.action), command.attack ? "primitive_retreat+attack" : "primitive_retreat");
    }
    else if (IntentFieldEquals(input->intent.movement_primitive, "strafe_left"))
    {
        command.strafe = -1;
        CopyField(command.action, sizeof(command.action), command.attack ? "primitive_strafe_left+attack" : "primitive_strafe_left");
    }
    else if (IntentFieldEquals(input->intent.movement_primitive, "strafe_right"))
    {
        command.strafe = 1;
        CopyField(command.action, sizeof(command.action), command.attack ? "primitive_strafe_right+attack" : "primitive_strafe_right");
    }
    else if (IntentFieldEquals(input->intent.movement_primitive, "circle_left"))
    {
        command.strafe = -1;
        CopyField(command.action, sizeof(command.action), command.attack ? "primitive_circle_left+attack" : "primitive_circle_left");
    }
    else if (IntentFieldEquals(input->intent.movement_primitive, "circle_right"))
    {
        command.strafe = 1;
        CopyField(command.action, sizeof(command.action), command.attack ? "primitive_circle_right+attack" : "primitive_circle_right");
    }
    else if (IntentFieldEquals(input->intent.movement_primitive, "hold_position"))
    {
        command.forward = 0;
        command.strafe = 0;
        CopyField(command.action, sizeof(command.action), command.attack ? "primitive_hold_position+attack" : "primitive_hold_position");
    }
    else
    {
        CopyField(command.reason, sizeof(command.reason), "empty_movement_primitive");
    }

    return FinalizeCommand(input, &command);
}

static arena_participant_autopilot_command_t StuckRecoveryCommand(
    const arena_participant_autopilot_input_t *input,
    int aim_error)
{
    arena_participant_autopilot_command_t command;
    int direction;
    int retreat_distance;

    command = NoopCommand("stuck_recovery");
    direction = TacticalStrafeDirection(input, 12);
    retreat_distance = RetreatThreshold(input, ARENA_AUTOPILOT_MIN_DISTANCE);
    command.active = true;
    if (IntentFieldEquals(input->intent.stuck_recovery_strategy, "back_up"))
    {
        command.forward = -1;
        command.strafe = 0;
        command.turn = TurnForPolicy(input, aim_error);
    }
    else if (IntentFieldEquals(input->intent.stuck_recovery_strategy, "turn_left"))
    {
        command.forward = 0;
        command.strafe = 0;
        command.turn = -1;
    }
    else if (IntentFieldEquals(input->intent.stuck_recovery_strategy, "turn_right"))
    {
        command.forward = 0;
        command.strafe = 0;
        command.turn = 1;
    }
    else if (IntentFieldEquals(input->intent.stuck_recovery_strategy, "strafe_out"))
    {
        command.forward = 0;
        command.strafe = direction;
        command.turn = TurnForPolicy(input, aim_error);
    }
    else
    {
        command.forward = -1;
        command.strafe = direction;
        command.turn = -direction;
    }
    command.attack = AttackAllowed(input, aim_error)
        && (input == NULL
            || input->distance <= 0
            || retreat_distance <= 0
            || input->distance >= retreat_distance);
    command.aim_error = aim_error;
    command.stuck_recovery = true;
    CopyField(command.action,
              sizeof(command.action),
              command.attack ? "unstick+attack" : "unstick");
    return FinalizeCommand(input, &command);
}

static arena_participant_autopilot_command_t HoldCommand(
    const arena_participant_autopilot_input_t *input,
    int aim_error)
{
    arena_participant_autopilot_command_t command;

    command = NoopCommand("hold");
    command.active = true;
    command.turn = TurnForPolicy(input, aim_error);
    command.attack = AttackAllowed(input, aim_error);
    command.aim_error = aim_error;
    CopyField(command.action, sizeof(command.action), command.attack ? "hold+attack" : "hold+aim");
    return FinalizeCommand(input, &command);
}

static arena_participant_autopilot_command_t SearchCommand(
    const arena_participant_autopilot_input_t *input,
    int aim_error)
{
    arena_participant_autopilot_command_t command;

    command = NoopCommand("search");
    command.active = true;
    if (!input->line_of_sight)
    {
        ApplyLosLostAction(input, &command, aim_error);
    }
    else
    {
        command.turn = TurnForPolicy(input, aim_error);
    }
    command.attack = AttackAllowed(input, aim_error);
    command.aim_error = aim_error;
    if (input->line_of_sight)
    {
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "search+attack" : "search");
    }
    return FinalizeCommand(input, &command);
}

static arena_participant_autopilot_command_t EngageCommand(
    const arena_participant_autopilot_input_t *input,
    int aim_error)
{
    arena_participant_autopilot_command_t command;
    int preferred_distance;
    int retreat_distance;
    int push_distance;
    int strafe_direction;

    command = NoopCommand("engage_opponent");
    command.active = true;
    preferred_distance = PreferredDistance(input);
    strafe_direction = TacticalStrafeDirection(input, 20);
    command.turn = TurnForPolicy(input, aim_error);
    command.attack = AttackAllowed(input, aim_error);
    command.aim_error = aim_error;
    retreat_distance = RetreatThreshold(input, ARENA_AUTOPILOT_MIN_DISTANCE);
    push_distance = PushThreshold(input, preferred_distance);

    if (!input->line_of_sight)
    {
        ApplyLosLostAction(input, &command, aim_error);
        return FinalizeCommand(input, &command);
    }

    if (IntentFieldEquals(input->intent.distance_policy, "close"))
    {
        if (input->distance > retreat_distance)
        {
            command.forward = 1;
            if (IntentFieldEquals(input->intent.movement_bias, "circle")
                || IntentFieldEquals(input->intent.movement_bias, "evasive"))
            {
                command.strafe = strafe_direction;
            }
            CopyField(command.action,
                      sizeof(command.action),
                      command.attack ? "engage_close+attack" : "engage_close");
        }
        else
        {
            command.forward = -1;
            command.strafe = strafe_direction;
            CopyField(command.action,
                      sizeof(command.action),
                      command.attack ? "engage_safety_backoff+attack" : "engage_safety_backoff");
        }
    }
    else if (IntentFieldEquals(input->intent.distance_policy, "kite"))
    {
        command.strafe = strafe_direction;
        if (input->distance < RetreatThreshold(input, preferred_distance + preferred_distance / 3))
        {
            command.forward = -1;
            CopyField(command.action,
                      sizeof(command.action),
                      command.attack ? "engage_kite_backoff+attack" : "engage_kite_backoff");
        }
        else if (input->distance > PushThreshold(input, preferred_distance * 2)
                 && !IntentFieldEquals(input->intent.movement_bias, "cautious"))
        {
            command.forward = 1;
            CopyField(command.action,
                      sizeof(command.action),
                      command.attack ? "engage_kite_close_gap+attack" : "engage_kite_close_gap");
        }
        else
        {
            CopyField(command.action,
                      sizeof(command.action),
                      command.attack ? "engage_kite_strafe+attack" : "engage_kite_strafe");
        }
    }
    else if (input->distance > push_distance)
    {
        command.forward = 1;
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "engage_forward+attack" : "engage_forward");
    }
    else if (input->distance > retreat_distance)
    {
        command.strafe = strafe_direction;
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "engage_strafe+attack" : "engage_strafe");
    }
    else
    {
        command.forward = -1;
        command.strafe = strafe_direction;
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "engage_backoff+attack" : "engage_backoff");
    }

    if (IntentFieldEquals(input->intent.movement_bias, "circle")
        && input->line_of_sight
        && input->distance <= PushThreshold(input, preferred_distance + preferred_distance / 2))
    {
        command.strafe = strafe_direction;
        if (!IntentFieldEquals(input->intent.distance_policy, "close"))
        {
            command.forward = 0;
        }
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "engage_circle+attack" : "engage_circle");
    }
    else if (IntentFieldEquals(input->intent.movement_bias, "evasive"))
    {
        command.strafe = strafe_direction;
        if (!IntentFieldEquals(input->intent.distance_policy, "close")
            && input->distance <= PushThreshold(input, preferred_distance + preferred_distance / 2))
        {
            command.forward = input->distance < RetreatThreshold(input, preferred_distance) ? -1 : 0;
        }
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "engage_evasive+attack" : "engage_evasive");
    }
    else if (IntentFieldEquals(input->intent.movement_bias, "cautious"))
    {
        if (command.forward > 0 && input->distance < PushThreshold(input, preferred_distance * 2))
        {
            command.forward = 0;
        }
        if (input->line_of_sight && input->distance < RetreatThreshold(input, preferred_distance))
        {
            command.strafe = strafe_direction;
            command.forward = -1;
        }
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "engage_cautious+attack" : "engage_cautious");
    }

    return FinalizeCommand(input, &command);
}

static arena_participant_autopilot_command_t StrafeAttackCommand(
    const arena_participant_autopilot_input_t *input,
    int aim_error)
{
    arena_participant_autopilot_command_t command;
    int preferred_distance;
    int retreat_distance;
    int strafe_direction;

    command = NoopCommand("strafe_attack");
    command.active = true;
    preferred_distance = PreferredDistance(input);
    strafe_direction = TacticalStrafeDirection(input, 16);
    command.turn = TurnForPolicy(input, aim_error);
    command.strafe = strafe_direction;
    command.attack = AttackAllowed(input, aim_error);
    command.aim_error = aim_error;
    retreat_distance = RetreatThreshold(input, preferred_distance);

    if (!input->line_of_sight)
    {
        ApplyLosLostAction(input, &command, aim_error);
        return FinalizeCommand(input, &command);
    }

    if (IntentFieldEquals(input->intent.distance_policy, "close"))
    {
        if (input->distance > RetreatThreshold(input, ARENA_AUTOPILOT_MIN_DISTANCE))
        {
            command.forward = 1;
        }
    }
    else if (IntentFieldEquals(input->intent.distance_policy, "kite"))
    {
        if (input->distance < RetreatThreshold(input, preferred_distance + preferred_distance / 3))
        {
            command.forward = -1;
        }
        else if (input->distance > PushThreshold(input, preferred_distance * 2)
                 && !IntentFieldEquals(input->intent.movement_bias, "cautious"))
        {
            command.forward = 1;
        }
    }
    else if (input->distance > PushThreshold(input, preferred_distance + preferred_distance / 2))
    {
        command.forward = 1;
    }

    if (IntentFieldEquals(input->intent.movement_bias, "evasive"))
    {
        if (input->distance < retreat_distance)
        {
            command.forward = -1;
        }
        else if (input->distance <= PushThreshold(input, preferred_distance * 2))
        {
            command.forward = 0;
        }
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "strafe_evasive+attack" : "strafe_evasive");
    }
    else if (IntentFieldEquals(input->intent.movement_bias, "cautious"))
    {
        if (input->distance < retreat_distance)
        {
            command.forward = -1;
        }
        else if (input->distance < PushThreshold(input, preferred_distance * 2))
        {
            command.forward = 0;
        }
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "strafe_cautious+attack" : "strafe_cautious");
    }
    else
    {
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "strafe_attack+attack" : "strafe_attack");
    }
    return FinalizeCommand(input, &command);
}

arena_participant_autopilot_command_t ArenaParticipantAutopilot_Decide(
    const arena_participant_autopilot_input_t *input)
{
    int aim_error;

    if (input == NULL)
    {
        return NoopCommand("missing_input");
    }

    if (!input->intent.active || !input->intent.valid)
    {
        return NoopCommand("inactive_intent_fallback");
    }

    aim_error = NormalizeAngleError(input->relative_angle);

    if (input->phase_finished)
    {
        arena_participant_autopilot_command_t command;

        command = NoopCommand("phase_finished");
        command.active = true;
        command.aim_error = aim_error;
        return command;
    }

    if (input->opponent_health <= 0)
    {
        arena_participant_autopilot_command_t command;

        command = NoopCommand("opponent_down");
        command.active = true;
        command.aim_error = aim_error;
        return command;
    }

    if (IntentIsStale(input) && !input->line_of_sight && CombatIntent(input))
    {
        arena_participant_autopilot_command_t command;

        command = SearchCommand(input, aim_error);
        CopyField(command.reason, sizeof(command.reason), "stale_intent_lost_los_override");
        if (command.action[0] == '\0' || !strcmp(command.action, "noop"))
        {
            CopyField(command.action, sizeof(command.action), "stale_reacquire_search");
        }
        return command;
    }

    if (input->stuck_ticks >= ARENA_AUTOPILOT_STUCK_TICKS)
    {
        TrackStuckRecoveryBurst(input);
        if (InStuckCooldown(input) && !input->line_of_sight && CombatIntent(input))
        {
            arena_participant_autopilot_command_t command;

            command = SearchCommand(input, aim_error);
            CopyField(command.reason, sizeof(command.reason), "stuck_burst_cooldown_search");
            if (command.action[0] == '\0' || !strcmp(command.action, "noop"))
            {
                CopyField(command.action, sizeof(command.action), "cooldown_reacquire_search");
            }
            return command;
        }
        return StuckRecoveryCommand(input, aim_error);
    }

    if (input->intent.movement_primitive[0] != '\0')
    {
        return MovementPrimitiveCommand(input, aim_error);
    }

    if (!strcmp(input->intent.intent, "hold"))
    {
        return HoldCommand(input, aim_error);
    }

    if (!strcmp(input->intent.intent, "search"))
    {
        return SearchCommand(input, aim_error);
    }

    if (!strcmp(input->intent.intent, "engage_opponent"))
    {
        return EngageCommand(input, aim_error);
    }

    if (!strcmp(input->intent.intent, "strafe_attack"))
    {
        return StrafeAttackCommand(input, aim_error);
    }

    return NoopCommand("unknown_intent_fallback");
}

void ArenaParticipantAutopilot_ResetDebug(void)
{
    memset(arena_route_cursor_intent_id, 0, sizeof(arena_route_cursor_intent_id));
    memset(arena_route_cursor_index, 0, sizeof(arena_route_cursor_index));
    arena_autopilot_last_health[ARENA_PARTICIPANT_PLAYER_1] = -1;
    arena_autopilot_last_health[ARENA_PARTICIPANT_PLAYER_2] = -1;
    arena_autopilot_last_strafe_direction[ARENA_PARTICIPANT_PLAYER_1] = -1;
    arena_autopilot_last_strafe_direction[ARENA_PARTICIPANT_PLAYER_2] = 1;
    arena_autopilot_stuck_burst_count[ARENA_PARTICIPANT_PLAYER_1] = 0;
    arena_autopilot_stuck_burst_count[ARENA_PARTICIPANT_PLAYER_2] = 0;
    arena_autopilot_last_stuck_tick[ARENA_PARTICIPANT_PLAYER_1] = -100000;
    arena_autopilot_last_stuck_tick[ARENA_PARTICIPANT_PLAYER_2] = -100000;
    arena_autopilot_unstick_cooldown_until_tick[ARENA_PARTICIPANT_PLAYER_1] = 0;
    arena_autopilot_unstick_cooldown_until_tick[ARENA_PARTICIPANT_PLAYER_2] = 0;
    ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                             "no_active_intent");
    ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_2,
                                             "no_active_intent");
}

void ArenaParticipantAutopilot_RecordDecision(
    arena_participant_id_t participant,
    const arena_participant_intent_t *intent,
    const arena_participant_autopilot_command_t *command)
{
    arena_participant_autopilot_debug_t *debug;

    if (participant < 0 || participant >= ARENA_PARTICIPANT_COUNT)
    {
        return;
    }

    if (intent == NULL || command == NULL || !intent->active || !command->active)
    {
        ArenaParticipantAutopilot_RecordFallback(participant,
                                                 "inactive_intent_fallback");
        return;
    }

    debug = &arena_autopilot_debug[participant];
    memset(debug, 0, sizeof(*debug));
    CopyField(debug->controller_mode, sizeof(debug->controller_mode), "autopilot");
    CopyField(debug->intent, sizeof(debug->intent), intent->intent);
    CopyField(debug->intent_status,
              sizeof(debug->intent_status),
              !strcmp(intent->status, "stale") ? "stale" : "active");
    CopyField(debug->intent_id, sizeof(debug->intent_id), intent->intent_id);
    CopyField(debug->intent_style, sizeof(debug->intent_style), intent->style);
    CopyField(debug->autopilot_action,
              sizeof(debug->autopilot_action),
              command->action);
    CopyField(debug->autopilot_reason,
              sizeof(debug->autopilot_reason),
              command->reason);
    debug->aim_error = command->aim_error;
    debug->preferred_distance = intent->preferred_distance;
    debug->stuck_recovery = command->stuck_recovery ? true : false;
    CopyField(debug->strafe_direction,
              sizeof(debug->strafe_direction),
              intent->strafe_direction);
    CopyField(debug->movement_bias,
              sizeof(debug->movement_bias),
              intent->movement_bias);
    CopyField(debug->fire_policy,
              sizeof(debug->fire_policy),
              intent->fire_policy);
    CopyField(debug->distance_policy,
              sizeof(debug->distance_policy),
              intent->distance_policy);
    debug->aim_tolerance = intent->aim_tolerance;
    debug->fire_burst_ms = intent->fire_burst_ms;
    debug->min_fire_alignment = intent->min_fire_alignment;
    debug->min_distance = intent->min_distance;
    debug->max_distance = intent->max_distance;
    debug->retreat_if_closer_than = intent->retreat_if_closer_than;
    debug->push_if_farther_than = intent->push_if_farther_than;
    CopyField(debug->los_lost_action,
              sizeof(debug->los_lost_action),
              intent->los_lost_action);
    CopyField(debug->stuck_recovery_strategy,
              sizeof(debug->stuck_recovery_strategy),
              intent->stuck_recovery_strategy);
    CopyField(debug->movement_primitive,
              sizeof(debug->movement_primitive),
              intent->movement_primitive);
    CopyField(debug->turn_policy,
              sizeof(debug->turn_policy),
              intent->turn_policy);
    CopyField(debug->navigation_target,
              sizeof(debug->navigation_target),
              intent->navigation_target);
    CopyField(debug->fire_mode,
              sizeof(debug->fire_mode),
              intent->fire_mode);
    if (!strncmp(command->action, "lost_los_", 9))
    {
        CopyField(debug->executed_los_lost_action,
                  sizeof(debug->executed_los_lost_action),
                  intent->los_lost_action);
    }
    if (!strncmp(command->action, "unstick", 7))
    {
        CopyField(debug->executed_stuck_recovery_strategy,
                  sizeof(debug->executed_stuck_recovery_strategy),
                  intent->stuck_recovery_strategy);
    }
    if (!strncmp(command->action, "primitive_", 10))
    {
        CopyField(debug->executed_movement_primitive,
                  sizeof(debug->executed_movement_primitive),
                  intent->movement_primitive);
    }
    CopyField(debug->executed_turn_policy,
              sizeof(debug->executed_turn_policy),
              intent->turn_policy);
    CopyField(debug->executed_navigation_target,
              sizeof(debug->executed_navigation_target),
              intent->navigation_target);
    CopyField(debug->executed_fire_mode,
              sizeof(debug->executed_fire_mode),
              EffectiveFireModeForIntent(intent));
    CopyField(debug->replan_if,
              sizeof(debug->replan_if),
              intent->replan_if);
    debug->sequence_number = intent->has_sequence_number ? intent->sequence_number : -1;
    debug->decision_cadence_ms = intent->decision_cadence_ms;
    debug->issued_at_ms = intent->issued_at_ms;
    debug->expires_at_ms = intent->expires_at_ms;
    debug->replan_recommended = command->replan_recommended ? true : false;
    CopyField(debug->replan_reasons,
              sizeof(debug->replan_reasons),
              command->replan_reasons);
}

void ArenaParticipantAutopilot_RecordFallback(
    arena_participant_id_t participant,
    const char *reason)
{
    SetFallbackDebug(participant, reason);
}

arena_participant_autopilot_debug_t ArenaParticipantAutopilot_Debug(
    arena_participant_id_t participant)
{
    arena_participant_autopilot_debug_t empty_debug;

    if (participant < 0 || participant >= ARENA_PARTICIPANT_COUNT)
    {
        memset(&empty_debug, 0, sizeof(empty_debug));
        CopyField(empty_debug.controller_mode,
                  sizeof(empty_debug.controller_mode),
                  "low_level_command");
        CopyField(empty_debug.intent, sizeof(empty_debug.intent), "none");
        CopyField(empty_debug.intent_status,
                  sizeof(empty_debug.intent_status),
                  "inactive");
        CopyField(empty_debug.autopilot_action,
                  sizeof(empty_debug.autopilot_action),
                  "none");
        CopyField(empty_debug.autopilot_reason,
                  sizeof(empty_debug.autopilot_reason),
                  "invalid_participant");
        CopyField(empty_debug.strafe_direction,
                  sizeof(empty_debug.strafe_direction),
                  "auto");
        CopyField(empty_debug.movement_bias,
                  sizeof(empty_debug.movement_bias),
                  "direct");
        CopyField(empty_debug.fire_policy,
                  sizeof(empty_debug.fire_policy),
                  "only_when_aligned");
        CopyField(empty_debug.distance_policy,
                  sizeof(empty_debug.distance_policy),
                  "maintain");
        CopyField(empty_debug.los_lost_action,
                  sizeof(empty_debug.los_lost_action),
                  "sweep");
        CopyField(empty_debug.stuck_recovery_strategy,
                  sizeof(empty_debug.stuck_recovery_strategy),
                  "default");
        empty_debug.movement_primitive[0] = '\0';
        CopyField(empty_debug.turn_policy,
                  sizeof(empty_debug.turn_policy),
                  "auto");
        CopyField(empty_debug.navigation_target,
                  sizeof(empty_debug.navigation_target),
                  "opponent");
        CopyField(empty_debug.fire_mode,
                  sizeof(empty_debug.fire_mode),
                  "auto");
        empty_debug.executed_los_lost_action[0] = '\0';
        empty_debug.executed_stuck_recovery_strategy[0] = '\0';
        empty_debug.executed_movement_primitive[0] = '\0';
        empty_debug.executed_turn_policy[0] = '\0';
        empty_debug.executed_navigation_target[0] = '\0';
        empty_debug.executed_fire_mode[0] = '\0';
        empty_debug.sequence_number = -1;
        empty_debug.decision_cadence_ms = 0;
        empty_debug.issued_at_ms = 0;
        empty_debug.expires_at_ms = 0;
        empty_debug.replan_recommended = false;
        empty_debug.replan_reasons[0] = '\0';
        return empty_debug;
    }

    return arena_autopilot_debug[participant];
}
