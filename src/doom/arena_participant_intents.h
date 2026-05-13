//
// Doom Agent Arena participant intent parsing.
//

#ifndef __ARENA_PARTICIPANT_INTENTS__
#define __ARENA_PARTICIPANT_INTENTS__

#include "doomtype.h"
#include "arena_participant_commands.h"

#define ARENA_PARTICIPANT_INTENT_PATH "arena_participant_intents.local.tsv"

typedef enum
{
    ARENA_PARTICIPANT_INTENT_NONE,
    ARENA_PARTICIPANT_INTENT_HOLD,
    ARENA_PARTICIPANT_INTENT_ENGAGE_OPPONENT,
    ARENA_PARTICIPANT_INTENT_STRAFE_ATTACK,
    ARENA_PARTICIPANT_INTENT_SEARCH
} arena_participant_intent_kind_t;

typedef enum
{
    ARENA_PARTICIPANT_INTENT_STYLE_BALANCED,
    ARENA_PARTICIPANT_INTENT_STYLE_AGGRESSIVE,
    ARENA_PARTICIPANT_INTENT_STYLE_EVASIVE,
    ARENA_PARTICIPANT_INTENT_STYLE_CAUTIOUS
} arena_participant_intent_style_t;

typedef struct
{
    int active;
    int valid;
    char intent_id[64];
    char intent[32];
    char style[32];
    arena_participant_id_t participant;
    arena_participant_id_t target_participant;
    int preferred_distance;
    double aggression;
    int duration_ms;
    double issued_at_ms;
    double expires_at_ms;
    char strafe_direction[32];
    char movement_bias[32];
    char fire_policy[32];
    char distance_policy[32];
    char replan_if[128];
    int sequence_number;
    int has_sequence_number;
    int decision_cadence_ms;
    char status[32];
    char reason[96];
} arena_participant_intent_t;

void ArenaParticipantIntent_Init(void);
void ArenaParticipantIntent_TickOrRefresh(void);
arena_participant_intent_t ArenaParticipantIntent_Get(arena_participant_id_t participant);
boolean ArenaParticipantIntent_HasActive(arena_participant_id_t participant);
void ArenaParticipantIntent_ClearDebugState(void);

#endif
