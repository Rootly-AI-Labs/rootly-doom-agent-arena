//
// Doom Agent Arena player input control.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "doomdef.h"
#include "doomstat.h"
#include "d_event.h"
#include "i_timer.h"
#include "p_local.h"
#include "r_main.h"
#include "tables.h"
#include "arena_duel.h"
#include "arena_enemies.h"
#include "arena_participant_autopilot.h"
#include "arena_participant_commands.h"
#include "arena_participant_intents.h"
#include "arena_player_control.h"

#define ARENA_PLAYER_COMMAND_PATH "arena_player_command.local.tsv"
#define ARENA_PLAYER_FORWARD_SPEED 0x32
#define ARENA_PLAYER_SIDE_SPEED 0x28
#define ARENA_PLAYER_ROUTE_SPEED (ARENA_PLAYER_FORWARD_SPEED * 2048)
#define ARENA_PLAYER_TURN_SPEED 1280

typedef struct
{
    char command_id[64];
    int forward;
    int strafe;
    int turn;
    int attack;
    int use;
    int duration_ms;
    int start_ms;
    boolean active;
} arena_player_command_t;

static arena_player_command_t arena_player_command;
static fixed_t arena_player_last_autopilot_x;
static fixed_t arena_player_last_autopilot_y;
static int arena_player_autopilot_stuck_ticks;
static boolean arena_player_have_autopilot_position;
static arena_participant_autopilot_command_t arena_player_last_autopilot_command;
static int arena_player_last_autopilot_command_ms;

static int Arena_PlayerAngleDegrees(angle_t angle)
{
    return (int) ((angle * 360.0) / 4294967296.0);
}

static int Arena_PlayerNormalizedAngleDegrees(angle_t angle)
{
    int degrees;

    degrees = Arena_PlayerAngleDegrees(angle);
    while (degrees > 180)
    {
        degrees -= 360;
    }
    while (degrees < -180)
    {
        degrees += 360;
    }

    return degrees;
}

static int Arena_PlayerAutopilotStuckTicks(mobj_t *mobj)
{
    fixed_t delta;

    if (mobj == NULL)
    {
        arena_player_have_autopilot_position = false;
        arena_player_autopilot_stuck_ticks = 0;
        return 0;
    }

    if (!arena_player_have_autopilot_position)
    {
        arena_player_have_autopilot_position = true;
        arena_player_last_autopilot_x = mobj->x;
        arena_player_last_autopilot_y = mobj->y;
        arena_player_autopilot_stuck_ticks = 0;
        return 0;
    }

    delta = P_AproxDistance(mobj->x - arena_player_last_autopilot_x,
                            mobj->y - arena_player_last_autopilot_y);
    arena_player_last_autopilot_x = mobj->x;
    arena_player_last_autopilot_y = mobj->y;

    if ((delta >> FRACBITS) == 0)
    {
        arena_player_autopilot_stuck_ticks++;
    }
    else
    {
        arena_player_autopilot_stuck_ticks = 0;
    }

    return arena_player_autopilot_stuck_ticks;
}

static void Arena_PlayerApplyParticipantCommand(ticcmd_t *cmd)
{
    arena_participant_command_t command;

    command = ArenaParticipantCommands_Command(ARENA_PARTICIPANT_PLAYER_1);
    cmd->forwardmove = command.forward * ARENA_PLAYER_FORWARD_SPEED;
    cmd->sidemove = command.strafe * ARENA_PLAYER_SIDE_SPEED;
    cmd->angleturn = -command.turn * ARENA_PLAYER_TURN_SPEED;

    if (command.attack)
    {
        cmd->buttons |= BT_ATTACK;
    }

    if (command.use)
    {
        cmd->buttons |= BT_USE;
    }
}

static void Arena_PlayerApplyAutopilotCommandToTiccmd(
    ticcmd_t *cmd,
    const arena_participant_autopilot_command_t *command);

static void Arena_PlayerApplyRouteWaypointMovement(
    player_t *player,
    const arena_participant_autopilot_command_t *command)
{
    angle_t angle;
    int fine_angle;

    if (player == NULL
        || player->mo == NULL
        || command == NULL
        || !command->route_waypoint_active)
    {
        return;
    }

    angle = R_PointToAngle2(player->mo->x,
                            player->mo->y,
                            command->route_target_x * FRACUNIT,
                            command->route_target_y * FRACUNIT);
    fine_angle = angle >> ANGLETOFINESHIFT;
    player->mo->momx += FixedMul(ARENA_PLAYER_ROUTE_SPEED, finecosine[fine_angle]);
    player->mo->momy += FixedMul(ARENA_PLAYER_ROUTE_SPEED, finesine[fine_angle]);
}

static boolean Arena_PlayerApplyAutopilotCommand(ticcmd_t *cmd)
{
    int now_ms;
    player_t *player;
    mobj_t *player2;
    angle_t angle_to_player2;
    arena_participant_autopilot_input_t input;
    arena_participant_autopilot_command_t command;

    now_ms = I_GetTimeMS();

    if (!ArenaParticipantIntent_HasActive(ARENA_PARTICIPANT_PLAYER_1))
    {
        if (arena_player_last_autopilot_command.active
            && now_ms - arena_player_last_autopilot_command_ms <= 250)
        {
            Arena_PlayerApplyAutopilotCommandToTiccmd(
                cmd,
                &arena_player_last_autopilot_command);
            ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                     "retaining_last_autopilot_command");
            return true;
        }

        memset(&arena_player_last_autopilot_command, 0, sizeof(arena_player_last_autopilot_command));
        arena_player_last_autopilot_command_ms = 0;
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                 "no_active_intent");
        return false;
    }

    player = &players[consoleplayer];
    player2 = ArenaDuel_Player2Mobj();
    if (player->mo == NULL || player2 == NULL)
    {
        memset(&arena_player_last_autopilot_command, 0, sizeof(arena_player_last_autopilot_command));
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                 "missing_participant_state");
        return false;
    }

    memset(&input, 0, sizeof(input));
    input.participant = ARENA_PARTICIPANT_PLAYER_1;
    input.intent = ArenaParticipantIntent_Get(ARENA_PARTICIPANT_PLAYER_1);
    input.self_x = player->mo->x >> FRACBITS;
    input.self_y = player->mo->y >> FRACBITS;
    input.self_angle = Arena_PlayerAngleDegrees(player->mo->angle);
    input.opponent_x = player2->x >> FRACBITS;
    input.opponent_y = player2->y >> FRACBITS;
    input.opponent_health = player2->health;
    input.self_ammo = player->ammo[am_clip];
    input.self_health = player->mo->health;
    input.distance = P_AproxDistance(player2->x - player->mo->x,
                                     player2->y - player->mo->y) >> FRACBITS;
    angle_to_player2 = R_PointToAngle2(player->mo->x,
                                       player->mo->y,
                                       player2->x,
                                       player2->y);
    input.relative_angle =
        -Arena_PlayerNormalizedAngleDegrees(angle_to_player2 - player->mo->angle);
    input.line_of_sight = P_CheckSight(player->mo, player2) ? 1 : 0;
    input.stuck_ticks = Arena_PlayerAutopilotStuckTicks(player->mo);
    input.tick = leveltime;
    input.phase_finished = ArenaDuel_IsFinished() ? 1 : 0;

    command = ArenaParticipantAutopilot_Decide(&input);
    arena_player_last_autopilot_command = command;
    arena_player_last_autopilot_command_ms = now_ms;
    if (!command.active)
    {
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                 command.reason);
        return false;
    }

    ArenaParticipantAutopilot_RecordDecision(ARENA_PARTICIPANT_PLAYER_1,
                                             &input.intent,
                                             &command);

    if (command.route_waypoint_active)
    {
        Arena_PlayerApplyRouteWaypointMovement(player, &command);
    }
    Arena_PlayerApplyAutopilotCommandToTiccmd(cmd, &command);

    return true;
}

static void Arena_PlayerApplyAutopilotCommandToTiccmd(
    ticcmd_t *cmd,
    const arena_participant_autopilot_command_t *command)
{
    cmd->forwardmove = command->route_waypoint_active ? 0 : command->forward * ARENA_PLAYER_FORWARD_SPEED;
    cmd->sidemove = command->route_waypoint_active ? 0 : command->strafe * ARENA_PLAYER_SIDE_SPEED;
    cmd->angleturn = -command->turn * ARENA_PLAYER_TURN_SPEED;

    if (command->attack)
    {
        cmd->buttons |= BT_ATTACK;
    }

    if (command->use)
    {
        cmd->buttons |= BT_USE;
    }
}

static void Arena_PlayerChomp(char *line)
{
    size_t len;

    len = strlen(line);
    while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r'))
    {
        line[len - 1] = '\0';
        len--;
    }
}

static int Arena_PlayerSplitTsv(char *line, char **fields, int max_fields)
{
    int count;
    char *cursor;
    char *tab;

    count = 0;
    cursor = line;

    while (count < max_fields)
    {
        fields[count] = cursor;
        count++;

        tab = strchr(cursor, '\t');
        if (tab == NULL)
        {
            break;
        }

        *tab = '\0';
        cursor = tab + 1;
    }

    return count;
}

static int Arena_PlayerClamp(int value, int min_value, int max_value)
{
    if (value < min_value)
    {
        return min_value;
    }

    if (value > max_value)
    {
        return max_value;
    }

    return value;
}

static int Arena_PlayerParseBool(const char *value)
{
    return !strcmp(value, "true") || !strcmp(value, "1") || !strcmp(value, "yes");
}

static void Arena_PlayerLoadCommand(void)
{
    FILE *file;
    char line[256];
    char *fields[11];
    int line_number;
    int field_count;
    const char *command_id;
    int duration_ms;

    file = fopen(ARENA_PLAYER_COMMAND_PATH, "r");
    if (file == NULL)
    {
        file = fopen("/" ARENA_PLAYER_COMMAND_PATH, "r");
    }

    if (file == NULL)
    {
        return;
    }

    line_number = 0;
    while (fgets(line, sizeof(line), file) != NULL)
    {
        line_number++;
        Arena_PlayerChomp(line);

        if (line[0] == '\0')
        {
            continue;
        }

        if (line_number == 1 && !strncmp(line, "run_id", 6))
        {
            continue;
        }

        field_count = Arena_PlayerSplitTsv(line, fields, 11);
        if (field_count < 11)
        {
            continue;
        }

        command_id = fields[2];
        if (!strcmp(command_id, arena_player_command.command_id))
        {
            continue;
        }

        duration_ms = atoi(fields[10]);
        if (duration_ms <= 0)
        {
            duration_ms = 100;
        }

        memset(&arena_player_command, 0, sizeof(arena_player_command));
        strncpy(arena_player_command.command_id,
                command_id,
                sizeof(arena_player_command.command_id) - 1);
        arena_player_command.forward = Arena_PlayerClamp(atoi(fields[5]), -1, 1);
        arena_player_command.strafe = Arena_PlayerClamp(atoi(fields[6]), -1, 1);
        arena_player_command.turn = Arena_PlayerClamp(atoi(fields[7]), -1, 1);
        arena_player_command.attack = Arena_PlayerParseBool(fields[8]);
        arena_player_command.use = Arena_PlayerParseBool(fields[9]);
        arena_player_command.duration_ms = duration_ms;
        arena_player_command.start_ms = I_GetTimeMS();
        arena_player_command.active = true;
    }

    fclose(file);
}

boolean Arena_PlayerControlBuildTiccmd(ticcmd_t *cmd)
{
    int now;

    ArenaDuel_RestorePlayer1Mobj();
    Arena_PlayerLoadCommand();

    cmd->forwardmove = 0;
    cmd->sidemove = 0;
    cmd->angleturn = 0;
    cmd->buttons = 0;

    if (Arena_DuelModeEnabled())
    {
        if (ArenaDuel_IsFinished())
        {
            return true;
        }
        Arena_LoadRunMetadata();
        ArenaParticipantCommands_Load();
        ArenaParticipantIntent_TickOrRefresh();
        if (!ArenaDuel_IsStarted())
        {
            ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                     "waiting_for_both_agents");
            return true;
        }
        if (Arena_PlayerApplyAutopilotCommand(cmd))
        {
            return true;
        }
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                 "no_active_intent");
        Arena_PlayerApplyParticipantCommand(cmd);
        return true;
    }

    now = I_GetTimeMS();
    if (arena_player_command.active
        && now - arena_player_command.start_ms > arena_player_command.duration_ms)
    {
        arena_player_command.active = false;
    }

    if (!arena_player_command.active)
    {
        return true;
    }

    cmd->forwardmove = arena_player_command.forward * ARENA_PLAYER_FORWARD_SPEED;
    cmd->sidemove = arena_player_command.strafe * ARENA_PLAYER_SIDE_SPEED;
    cmd->angleturn = -arena_player_command.turn * ARENA_PLAYER_TURN_SPEED;

    if (arena_player_command.attack)
    {
        cmd->buttons |= BT_ATTACK;
    }

    if (arena_player_command.use)
    {
        cmd->buttons |= BT_USE;
    }

    return true;
}

arena_participant_autopilot_command_t Arena_PlayerLastAutopilotCommand(void)
{
    return arena_player_last_autopilot_command;
}
