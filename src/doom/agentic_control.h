//
// Agentic Doom state export and command parsing.
//

#ifndef __AGENTIC_CONTROL__
#define __AGENTIC_CONTROL__

typedef enum
{
    AGENTIC_CMD_NORMAL,
    AGENTIC_CMD_HOLD,
    AGENTIC_CMD_CHASE_PLAYER,
    AGENTIC_CMD_GUARD_POSITION,
    AGENTIC_CMD_FIGHT_EACH_OTHER
} agentic_command_t;

void Agentic_ExportState(void);
void Agentic_Ticker(void);
agentic_command_t Agentic_CommandForEnemy(int arena_entity_index);
const char *Agentic_CommandName(agentic_command_t command);

#endif
