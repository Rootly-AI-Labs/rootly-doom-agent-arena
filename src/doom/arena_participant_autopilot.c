//
// Doom Agent Arena participant autopilot decision logic.
//

#include <stdlib.h>
#include <string.h>

#include "arena_participant_autopilot.h"

#define ARENA_AUTOPILOT_AIM_TURN_DEGREES 6
#define ARENA_AUTOPILOT_AIM_ATTACK_DEGREES 8
#define ARENA_AUTOPILOT_AIM_SUPPRESSIVE_DEGREES 24
#define ARENA_AUTOPILOT_STUCK_TICKS 8
#define ARENA_AUTOPILOT_MIN_DISTANCE 128
#define ARENA_AUTOPILOT_LOW_HEALTH 35

static arena_participant_autopilot_debug_t arena_autopilot_debug[ARENA_PARTICIPANT_COUNT];

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

static int AttackAllowed(const arena_participant_autopilot_input_t *input, int aim_error)
{
    int abs_error;

    if (IntentFieldEquals(input->intent.fire_policy, "hold_fire"))
    {
        return false;
    }

    if (!input->line_of_sight || input->self_ammo <= 0 || input->opponent_health <= 0)
    {
        return false;
    }

    abs_error = AbsInt(aim_error);
    if (IntentFieldEquals(input->intent.fire_policy, "suppressive"))
    {
        return abs_error <= ARENA_AUTOPILOT_AIM_SUPPRESSIVE_DEGREES;
    }

    if (IntentFieldEquals(input->intent.fire_policy, "burst_when_aligned"))
    {
        return abs_error <= ARENA_AUTOPILOT_AIM_ATTACK_DEGREES
            && (input->tick % 21) < 9;
    }

    return abs_error <= ARENA_AUTOPILOT_AIM_ATTACK_DEGREES;
}

static int PreferredDistance(const arena_participant_autopilot_input_t *input)
{
    if (input->intent.preferred_distance > 0)
    {
        return input->intent.preferred_distance;
    }

    return 600;
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
    if (IntentFieldEquals(input->intent.strafe_direction, "left"))
    {
        return -1;
    }

    if (IntentFieldEquals(input->intent.strafe_direction, "right"))
    {
        return 1;
    }

    return AlternatingDirection(input->tick, period);
}

static int CombatIntent(const arena_participant_autopilot_input_t *input)
{
    return IntentFieldEquals(input->intent.intent, "engage_opponent")
        || IntentFieldEquals(input->intent.intent, "strafe_attack");
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

static arena_participant_autopilot_command_t FinalizeCommand(
    const arena_participant_autopilot_input_t *input,
    arena_participant_autopilot_command_t *command)
{
    ClampCommand(command);
    ApplyReplanHints(input, command);
    return *command;
}

static arena_participant_autopilot_command_t StuckRecoveryCommand(
    const arena_participant_autopilot_input_t *input,
    int aim_error)
{
    arena_participant_autopilot_command_t command;
    int direction;

    command = NoopCommand("stuck_recovery");
    direction = TacticalStrafeDirection(input, 12);
    command.active = true;
    command.forward = -1;
    command.strafe = direction;
    command.turn = -direction;
    command.attack = AttackAllowed(input, aim_error);
    command.aim_error = aim_error;
    command.stuck_recovery = true;
    CopyField(command.action, sizeof(command.action), command.attack ? "unstick+attack" : "unstick");
    return FinalizeCommand(input, &command);
}

static arena_participant_autopilot_command_t HoldCommand(
    const arena_participant_autopilot_input_t *input,
    int aim_error)
{
    arena_participant_autopilot_command_t command;

    command = NoopCommand("hold");
    command.active = true;
    command.turn = TurnForAimError(aim_error);
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
    command.turn = input->line_of_sight ? TurnForAimError(aim_error) : 1;
    command.forward = (!input->line_of_sight && ((input->tick / 35) % 3) == 0) ? 1 : 0;
    command.attack = AttackAllowed(input, aim_error);
    command.aim_error = aim_error;
    CopyField(command.action,
              sizeof(command.action),
              command.attack ? "search+attack" : "search");
    return FinalizeCommand(input, &command);
}

static arena_participant_autopilot_command_t EngageCommand(
    const arena_participant_autopilot_input_t *input,
    int aim_error)
{
    arena_participant_autopilot_command_t command;
    int preferred_distance;
    int strafe_direction;

    command = NoopCommand("engage_opponent");
    command.active = true;
    preferred_distance = PreferredDistance(input);
    strafe_direction = TacticalStrafeDirection(input, 20);
    command.turn = TurnForAimError(aim_error);
    command.attack = AttackAllowed(input, aim_error);
    command.aim_error = aim_error;

    if (IntentFieldEquals(input->intent.distance_policy, "close"))
    {
        if (input->distance > ARENA_AUTOPILOT_MIN_DISTANCE)
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
        if (input->distance < preferred_distance + preferred_distance / 3)
        {
            command.forward = -1;
            CopyField(command.action,
                      sizeof(command.action),
                      command.attack ? "engage_kite_backoff+attack" : "engage_kite_backoff");
        }
        else if (input->distance > preferred_distance * 2
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
    else if (input->distance > preferred_distance)
    {
        command.forward = 1;
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "engage_forward+attack" : "engage_forward");
    }
    else if (input->distance > ARENA_AUTOPILOT_MIN_DISTANCE)
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
        && input->distance <= preferred_distance + preferred_distance / 2)
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
            && input->distance <= preferred_distance + preferred_distance / 2)
        {
            command.forward = input->distance < preferred_distance ? -1 : 0;
        }
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "engage_evasive+attack" : "engage_evasive");
    }
    else if (IntentFieldEquals(input->intent.movement_bias, "cautious"))
    {
        if (command.forward > 0 && input->distance < preferred_distance * 2)
        {
            command.forward = 0;
        }
        if (input->line_of_sight && input->distance < preferred_distance)
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
    int strafe_direction;

    command = NoopCommand("strafe_attack");
    command.active = true;
    preferred_distance = PreferredDistance(input);
    strafe_direction = TacticalStrafeDirection(input, 16);
    command.turn = TurnForAimError(aim_error);
    command.strafe = strafe_direction;
    command.attack = AttackAllowed(input, aim_error);
    command.aim_error = aim_error;

    if (IntentFieldEquals(input->intent.distance_policy, "close"))
    {
        if (input->distance > ARENA_AUTOPILOT_MIN_DISTANCE)
        {
            command.forward = 1;
        }
    }
    else if (IntentFieldEquals(input->intent.distance_policy, "kite"))
    {
        if (input->distance < preferred_distance + preferred_distance / 3)
        {
            command.forward = -1;
        }
        else if (input->distance > preferred_distance * 2
                 && !IntentFieldEquals(input->intent.movement_bias, "cautious"))
        {
            command.forward = 1;
        }
    }
    else if (input->distance > preferred_distance + preferred_distance / 2)
    {
        command.forward = 1;
    }

    if (IntentFieldEquals(input->intent.movement_bias, "evasive"))
    {
        if (input->distance < preferred_distance)
        {
            command.forward = -1;
        }
        else if (input->distance <= preferred_distance * 2)
        {
            command.forward = 0;
        }
        CopyField(command.action,
                  sizeof(command.action),
                  command.attack ? "strafe_evasive+attack" : "strafe_evasive");
    }
    else if (IntentFieldEquals(input->intent.movement_bias, "cautious"))
    {
        if (input->distance < preferred_distance)
        {
            command.forward = -1;
        }
        else if (input->distance < preferred_distance * 2)
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

    if (input->stuck_ticks >= ARENA_AUTOPILOT_STUCK_TICKS)
    {
        return StuckRecoveryCommand(input, aim_error);
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
    CopyField(debug->intent_status, sizeof(debug->intent_status), "active");
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
