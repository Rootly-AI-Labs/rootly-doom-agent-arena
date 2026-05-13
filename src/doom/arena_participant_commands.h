//
// Doom Agent Arena participant command parsing.
//

#ifndef __ARENA_PARTICIPANT_COMMANDS__
#define __ARENA_PARTICIPANT_COMMANDS__

#include "doomtype.h"

#define ARENA_PARTICIPANT_COMMAND_PATH "arena_participant_commands.local.tsv"

typedef enum
{
    ARENA_PARTICIPANT_PLAYER_1,
    ARENA_PARTICIPANT_PLAYER_2,
    ARENA_PARTICIPANT_COUNT
} arena_participant_id_t;

typedef struct
{
    int forward;
    int strafe;
    int turn;
    int attack;
    int use;
    int active;
    int valid;
    char command_id[64];
    char status[32];
    char last_action[64];
} arena_participant_command_t;

void ArenaParticipantCommands_Init(void);
void ArenaParticipantCommands_Load(void);
arena_participant_command_t ArenaParticipantCommands_Command(arena_participant_id_t participant);
const char *ArenaParticipantCommands_LastAction(arena_participant_id_t participant);
const char *ArenaParticipantCommands_Status(arena_participant_id_t participant);

#endif
