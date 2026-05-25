//
// Agentic Doom state export and command parsing.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "doomdef.h"
#include "doomstat.h"
#include "r_main.h"
#include "p_local.h"
#include "arena_duel.h"
#include "arena_enemies.h"
#include "arena_participant_autopilot.h"
#include "arena_participant_commands.h"
#include "agentic_control.h"

#define AGENTIC_STATE_PATH "arena_game_state.local.tsv"
#define AGENTIC_COMMAND_PATH "arena_enemy_commands.local.tsv"

static int agentic_last_export_leveltime = -1;
static agentic_command_t agentic_enemy_commands[ARENA_MAX_ENEMIES];
static char agentic_enemy_command_ids[ARENA_MAX_ENEMIES][64];
static int agentic_enemy_command_start_ms[ARENA_MAX_ENEMIES];
static int agentic_enemy_command_duration_ms[ARENA_MAX_ENEMIES];
static fixed_t agentic_last_player_x;
static fixed_t agentic_last_player_y;
static int agentic_player_stuck_ticks;
static boolean agentic_have_last_player_position;

static void Agentic_ResetCommands(void)
{
    int i;

    for (i = 0; i < ARENA_MAX_ENEMIES; i++)
    {
        agentic_enemy_commands[i] = AGENTIC_CMD_NORMAL;
    }
}

const char *Agentic_CommandName(agentic_command_t command)
{
    switch (command)
    {
        case AGENTIC_CMD_NORMAL:
            return "normal";
        case AGENTIC_CMD_HOLD:
            return "hold";
        case AGENTIC_CMD_CHASE_PLAYER:
            return "chase_player";
        case AGENTIC_CMD_GUARD_POSITION:
            return "guard_position";
        case AGENTIC_CMD_FIGHT_EACH_OTHER:
            return "fight_each_other";
        default:
            return "normal";
    }
}

agentic_command_t Agentic_CommandForEnemy(int arena_entity_index)
{
    if (arena_entity_index < 0 || arena_entity_index >= ARENA_MAX_ENEMIES)
    {
        return AGENTIC_CMD_NORMAL;
    }

    return agentic_enemy_commands[arena_entity_index];
}

static boolean Agentic_ParseCommand(const char *value, agentic_command_t *command)
{
    if (!strcmp(value, "normal"))
    {
        *command = AGENTIC_CMD_NORMAL;
        return true;
    }

    if (!strcmp(value, "hold"))
    {
        *command = AGENTIC_CMD_HOLD;
        return true;
    }

    if (!strcmp(value, "chase_player"))
    {
        *command = AGENTIC_CMD_CHASE_PLAYER;
        return true;
    }

    if (!strcmp(value, "guard_position"))
    {
        *command = AGENTIC_CMD_GUARD_POSITION;
        return true;
    }

    if (!strcmp(value, "fight_each_other"))
    {
        *command = AGENTIC_CMD_FIGHT_EACH_OTHER;
        return true;
    }

    return false;
}

static void Agentic_Chomp(char *line)
{
    size_t len;

    len = strlen(line);

    while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r'))
    {
        line[len - 1] = '\0';
        len--;
    }
}

static int Agentic_SplitTsv(char *line, char **fields, int max_fields)
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

static void Agentic_CopyField(char *dest, size_t dest_size, const char *value)
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

static int Agentic_CommandDurationMs(const char *issued_at_ms,
                                     const char *expires_at_ms)
{
    double issued;
    double expires;
    double duration;

    issued = strtod(issued_at_ms, NULL);
    expires = strtod(expires_at_ms, NULL);
    duration = expires - issued;

    if (duration <= 0)
    {
        return 0;
    }

    if (duration > 60000)
    {
        return 60000;
    }

    return (int) duration;
}

static boolean Agentic_CommandStillActive(int arena_entity_index,
                                          const char *command_id,
                                          int duration_ms)
{
    int now;

    if (arena_entity_index < 0 || arena_entity_index >= ARENA_MAX_ENEMIES)
    {
        return false;
    }

    if (command_id == NULL || command_id[0] == '\0' || duration_ms <= 0)
    {
        return false;
    }

    now = I_GetTimeMS();
    if (strcmp(agentic_enemy_command_ids[arena_entity_index], command_id))
    {
        Agentic_CopyField(agentic_enemy_command_ids[arena_entity_index],
                          sizeof(agentic_enemy_command_ids[arena_entity_index]),
                          command_id);
        agentic_enemy_command_start_ms[arena_entity_index] = now;
        agentic_enemy_command_duration_ms[arena_entity_index] = duration_ms;
    }

    return now - agentic_enemy_command_start_ms[arena_entity_index]
           <= agentic_enemy_command_duration_ms[arena_entity_index];
}

static void Agentic_ApplyTeamCommand(const char *team,
                                     agentic_command_t command,
                                     const char *command_id,
                                     int duration_ms)
{
    int i;
    int count;

    if (strcmp(team, "enemy"))
    {
        return;
    }

    count = Arena_EnemyCount();

    for (i = 0; i < count && i < ARENA_MAX_ENEMIES; i++)
    {
        if (Agentic_CommandStillActive(i, command_id, duration_ms))
        {
            agentic_enemy_commands[i] = command;
        }
    }
}

static void Agentic_ApplyEnemyCommand(const char *target,
                                      agentic_command_t command,
                                      const char *command_id,
                                      int duration_ms)
{
    int arena_entity_index;
    int i;
    int count;

    count = Arena_EnemyCount();

    arena_entity_index = -1;
    for (i = 0; i < count && i < ARENA_MAX_ENEMIES; i++)
    {
        if (!strcmp(Arena_EnemyId(i), target))
        {
            arena_entity_index = i;
            break;
        }
    }

    if (arena_entity_index < 0 && !strncmp(target, "enemy_", 6))
    {
        arena_entity_index = atoi(target + 6);
    }

    if (arena_entity_index < 0 || arena_entity_index >= count
        || arena_entity_index >= ARENA_MAX_ENEMIES)
    {
        printf("Doom Agent Arena: ignoring invalid enemy target %s\n",
               target);
        return;
    }

    if (Agentic_CommandStillActive(arena_entity_index, command_id, duration_ms))
    {
        agentic_enemy_commands[arena_entity_index] = command;
    }
}

static void Agentic_LoadCommands(void)
{
    FILE *file;
    char line[256];
    char *fields[10];
    char *target_type;
    char *target;
    char *command_value;
    char *command_id;
    int line_number;
    int field_count;
    int duration_ms;
    agentic_command_t command;

    Agentic_ResetCommands();

    file = fopen(AGENTIC_COMMAND_PATH, "r");
    if (file == NULL)
    {
        file = fopen("/" AGENTIC_COMMAND_PATH, "r");
    }

    if (file == NULL)
    {
        return;
    }

    line_number = 0;

    while (fgets(line, sizeof(line), file) != NULL)
    {
        line_number++;
        Agentic_Chomp(line);

        if (line[0] == '\0')
        {
            continue;
        }

        if (line_number == 1
            && (!strncmp(line, "target_type", 11)
                || !strncmp(line, "run_id", 6)))
        {
            continue;
        }

        field_count = Agentic_SplitTsv(line, fields, 10);
        if (field_count >= 8)
        {
            command_id = fields[2];
            duration_ms = Agentic_CommandDurationMs(fields[3], fields[4]);
            target_type = fields[5];
            target = fields[6];
            command_value = fields[7];
        }
        else if (field_count >= 3)
        {
            command_id = line;
            duration_ms = 1000;
            target_type = fields[0];
            target = fields[1];
            command_value = fields[2];
        }
        else
        {
            printf("Doom Agent Arena: skipping malformed command line %d\n",
                   line_number);
            continue;
        }

        if (!Agentic_ParseCommand(command_value, &command))
        {
            printf("Doom Agent Arena: ignoring invalid command '%s' on line %d\n",
                   command_value,
                   line_number);
            continue;
        }

        if (!strcmp(target_type, "team"))
        {
            Agentic_ApplyTeamCommand(target, command, command_id, duration_ms);
        }
        else if (!strcmp(target_type, "enemy_id"))
        {
            Agentic_ApplyEnemyCommand(target, command, command_id, duration_ms);
        }
        else
        {
            printf("Doom Agent Arena: ignoring invalid target_type '%s' on line %d\n",
                   target_type,
                   line_number);
        }
    }

    fclose(file);
}

static int Agentic_AngleDegrees(angle_t angle)
{
    return (int) ((angle * 360.0) / 4294967296.0);
}

static int Agentic_NormalizedAngleDegrees(angle_t angle)
{
    int degrees;

    degrees = Agentic_AngleDegrees(angle);
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

static void Agentic_WriteTsvField(FILE *file, const char *value)
{
    const char *cursor;

    if (value == NULL)
    {
        return;
    }

    for (cursor = value; *cursor != '\0'; cursor++)
    {
        if (*cursor == '\t' || *cursor == '\n' || *cursor == '\r')
        {
            fputc(' ', file);
        }
        else
        {
            fputc(*cursor, file);
        }
    }
}

void Agentic_ExportState(void)
{
    FILE *file;
    thinker_t *thinker;
    mobj_t *mobj;
    player_t *player;
    int alive;
    int distance_to_player;
    int relative_angle_to_player;
    int line_of_sight;
    int position_delta;
    int participant_distance;
    int participant_relative_angle;
    int participant_line_of_sight;

    if (!Arena_ModeEnabled())
    {
        return;
    }

    Arena_LoadRunMetadata();
    Agentic_LoadCommands();
    if (ArenaDuel_IsEnabled())
    {
        ArenaParticipantCommands_Load();
    }

    file = fopen(AGENTIC_STATE_PATH, "w");
    if (file == NULL)
    {
        printf("Agentic Doom: could not write %s\n", AGENTIC_STATE_PATH);
        return;
    }

    fprintf(file,
            "run_id\tscenario_id\ttick\tkind\tentity_id\tteam\ttype\tlabel\tx\ty\tz\tangle\thealth\talive\tdistance_to_player\trelative_angle_to_player\tline_of_sight\tcurrent_command\tready_weapon\tammo_bullets\tammo_shells\tammo_cells\tammo_rockets\tlast_x\tlast_y\tposition_delta\tstuck_ticks\tcommand_status\tlast_action\tmode\tphase\twinner\tterminal_reason\telapsed_time_seconds\ttimeout_seconds\tmodel\tdamage_dealt\tshots_fired\tshots_hit\tinvalid_actions\tround\tseed\tintent\tintent_status\tintent_id\tintent_style\tautopilot_action\tautopilot_reason\taim_error\tpreferred_distance\tstuck_recovery\tcontroller_mode\tstrafe_direction\tmovement_bias\tfire_policy\tdistance_policy\treplan_if\tsequence_number\tdecision_cadence_ms\tissued_at_ms\texpires_at_ms\treplan_recommended\treplan_reasons\taim_tolerance\tfire_burst_ms\tmin_fire_alignment\tmin_distance\tmax_distance\tretreat_if_closer_than\tpush_if_farther_than\tlos_lost_action\tstuck_recovery_strategy\tmovement_primitive\tturn_policy\tnavigation_target\tfire_mode\texecuted_los_lost_action\texecuted_stuck_recovery_strategy\texecuted_movement_primitive\texecuted_turn_policy\texecuted_navigation_target\texecuted_fire_mode\n");

    if (ArenaDuel_IsEnabled())
    {
        fprintf(file,
                "%s\t%s\t%d\tmatch\tduel\tarena\tduel\tduel\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\tduel\t%s\t%s\t%s\t%d.%d\t%d\t\t\t\t\t\t%d\t%d\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n",
                Arena_RunId(),
                Arena_ScenarioId(),
                leveltime,
                ArenaDuel_Phase(),
                ArenaDuel_Winner(),
                ArenaDuel_TerminalReason(),
                ArenaDuel_ElapsedSecondsTenths() / 10,
                ArenaDuel_ElapsedSecondsTenths() % 10,
                ArenaDuel_TimeoutSeconds(),
                Arena_Round(),
                Arena_Seed());
    }

    player = &players[consoleplayer];
    if (player->mo != NULL)
    {
        mobj_t *player2;
        arena_participant_autopilot_debug_t debug;

        alive = player->playerstate != PST_DEAD && player->mo->health > 0;
        participant_distance = 0;
        participant_relative_angle = 0;
        participant_line_of_sight = 1;
        player2 = ArenaDuel_IsEnabled() ? ArenaDuel_Player2Mobj() : NULL;
        if (player2 != NULL)
        {
            angle_t angle_to_player2;

            participant_distance = P_AproxDistance(player2->x - player->mo->x,
                                                   player2->y - player->mo->y) >> FRACBITS;
            angle_to_player2 = R_PointToAngle2(player->mo->x,
                                               player->mo->y,
                                               player2->x,
                                               player2->y);
            participant_relative_angle =
                Agentic_NormalizedAngleDegrees(angle_to_player2 - player->mo->angle);
            participant_line_of_sight = P_CheckSight(player->mo, player2) ? 1 : 0;
        }

        if (agentic_have_last_player_position)
        {
            position_delta = P_AproxDistance(player->mo->x - agentic_last_player_x,
                                             player->mo->y - agentic_last_player_y) >> FRACBITS;
            if (position_delta == 0)
            {
                agentic_player_stuck_ticks++;
            }
            else
            {
                agentic_player_stuck_ticks = 0;
            }
        }
        else
        {
            position_delta = 0;
            agentic_player_stuck_ticks = 0;
            agentic_have_last_player_position = true;
        }

        debug = ArenaDuel_IsEnabled()
            ? ArenaParticipantAutopilot_Debug(ARENA_PARTICIPANT_PLAYER_1)
            : ArenaParticipantAutopilot_Debug(ARENA_PARTICIPANT_COUNT);

        fprintf(file,
                "%s\t%s\t%d\t%s\t%s\tplayer\tdoomguy\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\tnone\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%d.%d\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%d\t%.0f\t%.0f\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
                Arena_RunId(),
                Arena_ScenarioId(),
                leveltime,
                ArenaDuel_IsEnabled() ? "participant" : "player",
                ArenaDuel_IsEnabled() ? "player_1" : "player_0",
                ArenaDuel_IsEnabled() ? "player_1" : "player_0",
                player->mo->x >> FRACBITS,
                player->mo->y >> FRACBITS,
                player->mo->z >> FRACBITS,
                Agentic_AngleDegrees(player->mo->angle),
                player->mo->health,
                alive ? 1 : 0,
                participant_distance,
                participant_relative_angle,
                participant_line_of_sight,
                player->readyweapon,
                player->ammo[am_clip],
                player->ammo[am_shell],
                player->ammo[am_cell],
                player->ammo[am_misl],
                agentic_last_player_x >> FRACBITS,
                agentic_last_player_y >> FRACBITS,
                position_delta,
                agentic_player_stuck_ticks,
                ArenaDuel_IsEnabled()
                    ? ArenaParticipantCommands_Status(ARENA_PARTICIPANT_PLAYER_1)
                    : "legacy",
                ArenaDuel_IsEnabled()
                    ? ArenaParticipantCommands_LastAction(ARENA_PARTICIPANT_PLAYER_1)
                    : "none",
                ArenaDuel_IsEnabled() ? "duel" : Arena_Mode(),
                ArenaDuel_IsEnabled() ? ArenaDuel_Phase() : "",
                ArenaDuel_IsEnabled() ? ArenaDuel_Winner() : "",
                ArenaDuel_IsEnabled() ? ArenaDuel_TerminalReason() : "",
                ArenaDuel_IsEnabled() ? ArenaDuel_ElapsedSecondsTenths() / 10 : 0,
                ArenaDuel_IsEnabled() ? ArenaDuel_ElapsedSecondsTenths() % 10 : 0,
                ArenaDuel_IsEnabled() ? ArenaDuel_TimeoutSeconds() : 0,
                ArenaDuel_IsEnabled() ? Arena_Player1Model() : "",
                ArenaDuel_IsEnabled() ? ArenaDuel_Player1DamageDealt() : 0,
                ArenaDuel_IsEnabled() ? ArenaDuel_Player1ShotsFired() : 0,
                ArenaDuel_IsEnabled() ? ArenaDuel_Player1ShotsHit() : 0,
                ArenaDuel_IsEnabled() ? ArenaDuel_Player1InvalidActions() : 0,
                ArenaDuel_IsEnabled() ? Arena_Round() : 0,
                ArenaDuel_IsEnabled() ? Arena_Seed() : 0,
                debug.intent,
                debug.intent_status,
                debug.intent_id,
                debug.intent_style,
                debug.autopilot_action,
                debug.autopilot_reason,
                debug.aim_error,
                debug.preferred_distance,
                debug.stuck_recovery,
                debug.controller_mode,
                debug.strafe_direction,
                debug.movement_bias,
                debug.fire_policy,
                debug.distance_policy,
                debug.replan_if,
                debug.sequence_number,
                debug.decision_cadence_ms,
                debug.issued_at_ms,
                debug.expires_at_ms,
                debug.replan_recommended,
                debug.replan_reasons,
                debug.aim_tolerance,
                debug.fire_burst_ms,
                debug.min_fire_alignment,
                debug.min_distance,
                debug.max_distance,
                debug.retreat_if_closer_than,
                debug.push_if_farther_than,
                debug.los_lost_action,
                debug.stuck_recovery_strategy,
                debug.movement_primitive,
                debug.turn_policy,
                debug.navigation_target,
                debug.fire_mode,
                debug.executed_los_lost_action,
                debug.executed_stuck_recovery_strategy,
                debug.executed_movement_primitive,
                debug.executed_turn_policy,
                debug.executed_navigation_target,
                debug.executed_fire_mode);

        agentic_last_player_x = player->mo->x;
        agentic_last_player_y = player->mo->y;
    }

    for (thinker = thinkercap.next; thinker != &thinkercap; thinker = thinker->next)
    {
        if (thinker->function.acp1 != (actionf_p1) P_MobjThinker)
        {
            continue;
        }

        mobj = (mobj_t *) thinker;
        if (mobj->arena_entity_index < 0)
        {
            continue;
        }

        alive = mobj->health > 0;
        if (ArenaDuel_IsPlayer2(mobj))
        {
            arena_participant_autopilot_debug_t debug;

            distance_to_player = 0;
            relative_angle_to_player = 0;
            line_of_sight = 0;
            if (player->mo != NULL)
            {
                angle_t angle_to_player1;

                distance_to_player = P_AproxDistance(mobj->x - player->mo->x,
                                                     mobj->y - player->mo->y) >> FRACBITS;
                angle_to_player1 = R_PointToAngle2(mobj->x,
                                                   mobj->y,
                                                   player->mo->x,
                                                   player->mo->y);
                relative_angle_to_player =
                    Agentic_NormalizedAngleDegrees(angle_to_player1 - mobj->angle);
                line_of_sight = P_CheckSight(mobj, player->mo) ? 1 : 0;
            }

            debug = ArenaParticipantAutopilot_Debug(ARENA_PARTICIPANT_PLAYER_2);

            fprintf(file,
                    "%s\t%s\t%d\tparticipant\tplayer_2\tplayer\tdoomguy_actor\tplayer_2\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\tnone\t1\t%d\t0\t0\t0\t\t\t\t\t%s\t%s\tduel\t%s\t%s\t%s\t%d.%d\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%d\t%.0f\t%.0f\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
                    Arena_RunId(),
                    Arena_ScenarioId(),
                    leveltime,
                    mobj->x >> FRACBITS,
                    mobj->y >> FRACBITS,
                    mobj->z >> FRACBITS,
                    Agentic_AngleDegrees(mobj->angle),
                    mobj->health,
                    alive ? 1 : 0,
                    distance_to_player,
                    relative_angle_to_player,
                    line_of_sight,
                    ArenaDuel_Player2AmmoBullets(),
                    ArenaParticipantCommands_Status(ARENA_PARTICIPANT_PLAYER_2),
                    ArenaParticipantCommands_LastAction(ARENA_PARTICIPANT_PLAYER_2),
                    ArenaDuel_Phase(),
                    ArenaDuel_Winner(),
                    ArenaDuel_TerminalReason(),
                    ArenaDuel_ElapsedSecondsTenths() / 10,
                    ArenaDuel_ElapsedSecondsTenths() % 10,
                    ArenaDuel_TimeoutSeconds(),
                    Arena_Player2Model(),
                    ArenaDuel_Player2DamageDealt(),
                    ArenaDuel_Player2ShotsFired(),
                    ArenaDuel_Player2ShotsHit(),
                    ArenaDuel_Player2InvalidActions(),
                    Arena_Round(),
                    Arena_Seed(),
                    debug.intent,
                    debug.intent_status,
                    debug.intent_id,
                    debug.intent_style,
                    debug.autopilot_action,
                    debug.autopilot_reason,
                    debug.aim_error,
                    debug.preferred_distance,
                    debug.stuck_recovery,
                    debug.controller_mode,
                    debug.strafe_direction,
                    debug.movement_bias,
                    debug.fire_policy,
                    debug.distance_policy,
                    debug.replan_if,
                    debug.sequence_number,
                    debug.decision_cadence_ms,
                    debug.issued_at_ms,
                    debug.expires_at_ms,
                    debug.replan_recommended,
                    debug.replan_reasons,
                    debug.aim_tolerance,
                    debug.fire_burst_ms,
                    debug.min_fire_alignment,
                    debug.min_distance,
                    debug.max_distance,
                    debug.retreat_if_closer_than,
                    debug.push_if_farther_than,
                    debug.los_lost_action,
                    debug.stuck_recovery_strategy,
                    debug.movement_primitive,
                    debug.turn_policy,
                    debug.navigation_target,
                    debug.fire_mode,
                    debug.executed_los_lost_action,
                    debug.executed_stuck_recovery_strategy,
                    debug.executed_movement_primitive,
                    debug.executed_turn_policy,
                    debug.executed_navigation_target,
                    debug.executed_fire_mode);
            continue;
        }

        fprintf(file,
                "%s\t%s\t%d\tenemy\t",
                Arena_RunId(),
                Arena_ScenarioId(),
                leveltime);
        Agentic_WriteTsvField(file, mobj->arena_entity_id);
        fputc('\t', file);
        fputs("enemy\t", file);
        Agentic_WriteTsvField(file,
                              Arena_EnemyType(mobj->arena_entity_index));
        fputc('\t', file);
        Agentic_WriteTsvField(file, mobj->arena_label);

        distance_to_player = 0;
        relative_angle_to_player = 0;
        line_of_sight = 0;
        if (player->mo != NULL)
        {
            angle_t angle_to_enemy;

            distance_to_player = P_AproxDistance(mobj->x - player->mo->x,
                                                 mobj->y - player->mo->y) >> FRACBITS;
            angle_to_enemy = R_PointToAngle2(player->mo->x,
                                             player->mo->y,
                                             mobj->x,
                                             mobj->y);
            relative_angle_to_player =
                Agentic_NormalizedAngleDegrees(angle_to_enemy - player->mo->angle);
            line_of_sight = P_CheckSight(player->mo, mobj) ? 1 : 0;
        }

        fprintf(file,
                "\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n",
                mobj->x >> FRACBITS,
                mobj->y >> FRACBITS,
                mobj->z >> FRACBITS,
                Agentic_AngleDegrees(mobj->angle),
                mobj->health,
                alive ? 1 : 0,
                distance_to_player,
                relative_angle_to_player,
                line_of_sight,
                Agentic_CommandName(Agentic_CommandForEnemy(mobj->arena_entity_index)));
    }

    fclose(file);
    if (ArenaDuel_IsEnabled())
    {
        ArenaDuel_WriteEvents();
    }
}

void Agentic_Ticker(void)
{
    if (leveltime == agentic_last_export_leveltime)
    {
        return;
    }

    if (leveltime % TICRATE != 0)
    {
        return;
    }

    agentic_last_export_leveltime = leveltime;
    Agentic_ExportState();
}
