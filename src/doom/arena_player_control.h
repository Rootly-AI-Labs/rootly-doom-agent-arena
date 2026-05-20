//
// Doom Agent Arena player input control.
//

#ifndef __ARENA_PLAYER_CONTROL__
#define __ARENA_PLAYER_CONTROL__

#include "doomtype.h"
#include "d_ticcmd.h"
#include "arena_participant_autopilot.h"

boolean Arena_PlayerControlBuildTiccmd(ticcmd_t *cmd);
arena_participant_autopilot_command_t Arena_PlayerLastAutopilotCommand(void);

#endif
