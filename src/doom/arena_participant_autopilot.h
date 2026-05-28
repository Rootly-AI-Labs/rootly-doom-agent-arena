//
// Doom Agent Arena participant autopilot decision logic.
//

#ifndef __ARENA_PARTICIPANT_AUTOPILOT__
#define __ARENA_PARTICIPANT_AUTOPILOT__

#include "doomtype.h"
#include "arena_participant_intents.h"

typedef struct
{
    arena_participant_id_t participant;
    arena_participant_intent_t intent;
    int self_x;
    int self_y;
    int self_angle;
    int opponent_x;
    int opponent_y;
    int opponent_health;
    int self_ammo;
    int self_health;
    int distance;
    int relative_angle;
    int line_of_sight;
    int stuck_ticks;
    int tick;
    int phase_finished;
} arena_participant_autopilot_input_t;

typedef struct
{
    int active;
    int forward;
    int strafe;
    int turn;
    int attack;
    int use;
    int aim_error;
    int stuck_recovery;
    int replan_recommended;
    int route_waypoint_active;
    int route_target_x;
    int route_target_y;
    int route_waypoint_index;
    int route_waypoint_count;
    char replan_reasons[128];
    char action[64];
    char reason[96];
} arena_participant_autopilot_command_t;

typedef struct
{
    char controller_mode[32];
    char intent[32];
    char intent_status[32];
    char intent_id[64];
    char intent_style[32];
    char autopilot_action[64];
    char autopilot_reason[96];
    int aim_error;
    int preferred_distance;
    int stuck_recovery;
    char strafe_direction[32];
    char movement_bias[32];
    char fire_policy[32];
    char distance_policy[32];
    int aim_tolerance;
    int fire_burst_ms;
    int min_fire_alignment;
    int min_distance;
    int max_distance;
    int retreat_if_closer_than;
    int push_if_farther_than;
    char los_lost_action[32];
    char stuck_recovery_strategy[32];
    char movement_primitive[32];
    char turn_policy[32];
    char navigation_target[32];
    char fire_mode[32];
    char executed_los_lost_action[32];
    char executed_stuck_recovery_strategy[32];
    char executed_movement_primitive[32];
    char executed_turn_policy[32];
    char executed_navigation_target[32];
    char executed_fire_mode[32];
    char replan_if[128];
    int sequence_number;
    int decision_cadence_ms;
    double issued_at_ms;
    double expires_at_ms;
    int replan_recommended;
    char replan_reasons[128];
} arena_participant_autopilot_debug_t;

arena_participant_autopilot_command_t ArenaParticipantAutopilot_Decide(
    const arena_participant_autopilot_input_t *input);
void ArenaParticipantAutopilot_ResetDebug(void);
void ArenaParticipantAutopilot_RecordDecision(
    arena_participant_id_t participant,
    const arena_participant_intent_t *intent,
    const arena_participant_autopilot_command_t *command);
void ArenaParticipantAutopilot_RecordFallback(
    arena_participant_id_t participant,
    const char *reason);
arena_participant_autopilot_debug_t ArenaParticipantAutopilot_Debug(
    arena_participant_id_t participant);

#endif
