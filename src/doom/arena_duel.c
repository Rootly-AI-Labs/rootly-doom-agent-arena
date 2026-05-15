//
// Doom Agent Arena duel mode.
//

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "doomdef.h"
#include "doomstat.h"
#include "i_video.h"
#include "m_random.h"
#include "p_local.h"
#include "r_local.h"
#include "s_sound.h"
#include "sounds.h"
#include "tables.h"
#include "v_video.h"
#include "arena_duel.h"
#include "arena_enemies.h"
#include "arena_participant_autopilot.h"
#include "arena_participant_commands.h"
#include "arena_participant_intents.h"

#ifdef __EMSCRIPTEN__
#include <emscripten/emscripten.h>
#define ARENA_DUEL_EXPORT EMSCRIPTEN_KEEPALIVE
#else
#define ARENA_DUEL_EXPORT
#endif

#define ARENA_DUEL_MOVE_SPEED (0x32 * 2048)
#define ARENA_DUEL_SIDE_SPEED (0x28 * 2048)
#define ARENA_DUEL_TURN_SPEED 1280
#define ARENA_DUEL_ATTACK_COOLDOWN_TICS 12
#define ARENA_DUEL_MAX_EVENTS 4096
#define ARENA_DUEL_EVENTS_PATH "arena_duel_events.local.tsv"
#define ARENA_DUEL_PARTICIPANT_READY_PATH "arena_participant_ready.local.tsv"
#define ARENA_DUEL_PARTICIPANT_HEALTH 150
#define ARENA_DUEL_PLAYER2_BULLETS 50

static mobj_t *arena_duel_player2;
static int arena_duel_player2_ammo_bullets;
static int arena_duel_player2_attack_cooldown;
static int arena_duel_player2_attack_requests;
static int arena_duel_player2_shots_fired;
static int arena_duel_player1_shots_fired;
static int arena_duel_player1_shots_hit;
static int arena_duel_player2_shots_hit;
static int arena_duel_player1_damage_dealt;
static int arena_duel_player2_damage_dealt;
static int arena_duel_player1_invalid_actions;
static int arena_duel_player2_invalid_actions;
static int arena_duel_start_tick;
static int arena_duel_timeout_seconds;
static boolean arena_duel_started;
static int arena_duel_finished;
static char arena_duel_winner[16];
static char arena_duel_terminal_reason[32];
static int arena_duel_last_player1_health;
static int arena_duel_last_player2_health;
static char arena_duel_last_player1_attack_command_id[64];
static char arena_duel_events[ARENA_DUEL_MAX_EVENTS][192];
static int arena_duel_event_count;
static char arena_duel_last_intent_id[ARENA_PARTICIPANT_COUNT][64];
static boolean arena_duel_intent_was_active[ARENA_PARTICIPANT_COUNT];
static char arena_duel_last_autopilot_key[ARENA_PARTICIPANT_COUNT][192];
static boolean arena_duel_stuck_recovery_was_active[ARENA_PARTICIPANT_COUNT];
static pixel_t *arena_duel_player1_view_buffer;
static byte *arena_duel_player1_view_rgba;
static int arena_duel_player1_view_frame;
static int arena_duel_player1_view_nonzero_pixels;
static pixel_t *arena_duel_player2_view_buffer;
static byte *arena_duel_player2_view_rgba;
static int arena_duel_player2_view_frame;
static int arena_duel_player2_view_nonzero_pixels;
static fixed_t arena_duel_player2_last_autopilot_x;
static fixed_t arena_duel_player2_last_autopilot_y;
static int arena_duel_player2_autopilot_stuck_ticks;
static boolean arena_duel_player2_have_autopilot_position;
static boolean arena_duel_waiting_event_logged;
static boolean arena_duel_waiting_first_intents_event_logged;
static boolean arena_duel_player1_health_initialized;

static void ArenaDuel_CopyField(char *dest, size_t dest_size, const char *value)
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

static int ArenaDuel_AngleDegrees(angle_t angle)
{
    return (int) ((angle * 360.0) / 4294967296.0);
}

static int ArenaDuel_NormalizedAngleDegrees(angle_t angle)
{
    int degrees;

    degrees = ArenaDuel_AngleDegrees(angle);
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

static int ArenaDuel_Player1Health(void)
{
    player_t *player;

    player = &players[consoleplayer];
    if (player->mo == NULL)
    {
        return 0;
    }

    return player->mo->health;
}

static boolean ArenaDuel_EnsurePlayer1ViewBuffers(void)
{
    size_t paletted_size;
    size_t rgba_size;

    paletted_size = SCREENWIDTH * SCREENHEIGHT * sizeof(pixel_t);
    rgba_size = SCREENWIDTH * SCREENHEIGHT * 4;

    if (arena_duel_player1_view_buffer == NULL)
    {
        arena_duel_player1_view_buffer = malloc(paletted_size);
    }

    if (arena_duel_player1_view_rgba == NULL)
    {
        arena_duel_player1_view_rgba = malloc(rgba_size);
    }

    return arena_duel_player1_view_buffer != NULL
        && arena_duel_player1_view_rgba != NULL;
}

static boolean ArenaDuel_EnsurePlayer2ViewBuffers(void)
{
    size_t paletted_size;
    size_t rgba_size;

    paletted_size = SCREENWIDTH * SCREENHEIGHT * sizeof(pixel_t);
    rgba_size = SCREENWIDTH * SCREENHEIGHT * 4;

    if (arena_duel_player2_view_buffer == NULL)
    {
        arena_duel_player2_view_buffer = malloc(paletted_size);
    }

    if (arena_duel_player2_view_rgba == NULL)
    {
        arena_duel_player2_view_rgba = malloc(rgba_size);
    }

    return arena_duel_player2_view_buffer != NULL
        && arena_duel_player2_view_rgba != NULL;
}

static void ArenaDuel_AddEvent(const char *message)
{
    char row[192];
    int i;

    snprintf(row,
             sizeof(row),
             "%d\t%s",
             ArenaDuel_ElapsedMs(),
             message == NULL ? "" : message);

    if (arena_duel_event_count < ARENA_DUEL_MAX_EVENTS)
    {
        strncpy(arena_duel_events[arena_duel_event_count],
                row,
                sizeof(arena_duel_events[arena_duel_event_count]) - 1);
        arena_duel_events[arena_duel_event_count][sizeof(arena_duel_events[arena_duel_event_count]) - 1] = '\0';
        arena_duel_event_count++;
        return;
    }

    for (i = 1; i < ARENA_DUEL_MAX_EVENTS; i++)
    {
        strncpy(arena_duel_events[i - 1],
                arena_duel_events[i],
                sizeof(arena_duel_events[i - 1]) - 1);
        arena_duel_events[i - 1][sizeof(arena_duel_events[i - 1]) - 1] = '\0';
    }
    strncpy(arena_duel_events[ARENA_DUEL_MAX_EVENTS - 1],
            row,
            sizeof(arena_duel_events[ARENA_DUEL_MAX_EVENTS - 1]) - 1);
    arena_duel_events[ARENA_DUEL_MAX_EVENTS - 1][sizeof(arena_duel_events[ARENA_DUEL_MAX_EVENTS - 1]) - 1] = '\0';
}

static const char *ArenaDuel_ParticipantName(arena_participant_id_t participant)
{
    return participant == ARENA_PARTICIPANT_PLAYER_2 ? "player_2" : "player_1";
}

static void ArenaDuel_EnsurePlayer1Label(void)
{
    mobj_t *mobj;

    if (!ArenaDuel_IsEnabled())
    {
        return;
    }

    mobj = players[consoleplayer].mo;
    if (mobj == NULL)
    {
        return;
    }

    strncpy(mobj->arena_entity_id,
            "player_1",
            sizeof(mobj->arena_entity_id) - 1);
    mobj->arena_entity_id[sizeof(mobj->arena_entity_id) - 1] = '\0';
    strncpy(mobj->arena_label,
            "player_1",
            sizeof(mobj->arena_label) - 1);
    mobj->arena_label[sizeof(mobj->arena_label) - 1] = '\0';
}

static void ArenaDuel_EnsurePlayer1StartingHealth(void)
{
    player_t *player;

    if (arena_duel_player1_health_initialized)
    {
        return;
    }

    player = &players[consoleplayer];
    if (player->mo == NULL)
    {
        return;
    }

    player->health = ARENA_DUEL_PARTICIPANT_HEALTH;
    player->mo->health = ARENA_DUEL_PARTICIPANT_HEALTH;
    arena_duel_player1_health_initialized = true;
}

static void ArenaDuel_Chomp(char *line)
{
    size_t len;

    len = strlen(line);
    while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r'))
    {
        line[len - 1] = '\0';
        len--;
    }
}

static int ArenaDuel_SplitTsv(char *line, char **fields, int max_fields)
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

static boolean ArenaDuel_ParticipantReady(arena_participant_id_t participant)
{
    FILE *file;
    char line[256];
    const char *participant_name;

    participant_name = ArenaDuel_ParticipantName(participant);
    file = fopen(ARENA_DUEL_PARTICIPANT_READY_PATH, "rb");
    if (file == NULL)
    {
        return false;
    }

    if (fgets(line, sizeof(line), file) == NULL)
    {
        fclose(file);
        return false;
    }

    while (fgets(line, sizeof(line), file) != NULL)
    {
        char *fields[5];
        int count;

        ArenaDuel_Chomp(line);
        if (line[0] == '\0')
        {
            continue;
        }

        count = ArenaDuel_SplitTsv(line, fields, 5);
        if (count != 5)
        {
            continue;
        }

        if (!strcmp(fields[0], Arena_RunId())
            && !strcmp(fields[1], Arena_ScenarioId())
            && !strcmp(fields[2], participant_name)
            && !strcmp(fields[4], "ready"))
        {
            fclose(file);
            return true;
        }
    }

    fclose(file);
    return false;
}

static boolean ArenaDuel_BothParticipantsReady(void)
{
    return ArenaDuel_ParticipantReady(ARENA_PARTICIPANT_PLAYER_1)
        && ArenaDuel_ParticipantReady(ARENA_PARTICIPANT_PLAYER_2);
}

static boolean ArenaDuel_BothParticipantsHaveOpeningIntents(void)
{
    return ArenaParticipantIntent_HasActive(ARENA_PARTICIPANT_PLAYER_1)
        && ArenaParticipantIntent_HasActive(ARENA_PARTICIPANT_PLAYER_2);
}

static const char *ArenaDuel_StartWaitReason(void)
{
    if (!ArenaDuel_BothParticipantsReady())
    {
        return "waiting_for_both_agents";
    }
    if (!ArenaDuel_BothParticipantsHaveOpeningIntents())
    {
        return "waiting_for_first_intents";
    }
    return "waiting_for_start_barrier";
}

static void ArenaDuel_UpdateStartBarrier(void)
{
    if (arena_duel_started || arena_duel_finished)
    {
        return;
    }

    if (ArenaDuel_BothParticipantsReady())
    {
        if (ArenaDuel_BothParticipantsHaveOpeningIntents())
        {
            arena_duel_started = true;
            arena_duel_start_tick = leveltime;
            ArenaDuel_AddEvent("match_started: both_participants_ready_and_first_intents");
            return;
        }

        if (!arena_duel_waiting_first_intents_event_logged)
        {
            ArenaDuel_AddEvent("match_waiting_for_first_intents");
            arena_duel_waiting_first_intents_event_logged = true;
        }
        return;
    }

    if (!arena_duel_waiting_event_logged)
    {
        ArenaDuel_AddEvent("match_waiting_for_agents");
        arena_duel_waiting_event_logged = true;
    }
}

static void ArenaDuel_LogIntentEvents(void)
{
    arena_participant_id_t participant;

    for (participant = ARENA_PARTICIPANT_PLAYER_1;
         participant < ARENA_PARTICIPANT_COUNT;
         participant++)
    {
        arena_participant_intent_t intent;
        boolean active;
        char event[160];

        active = ArenaParticipantIntent_HasActive(participant);
        intent = ArenaParticipantIntent_Get(participant);

        if (active
            && (!arena_duel_intent_was_active[participant]
                || strcmp(arena_duel_last_intent_id[participant], intent.intent_id)))
        {
            snprintf(event,
                     sizeof(event),
                     "intent_set: %s intent=%s style=%s",
                     ArenaDuel_ParticipantName(participant),
                     intent.intent,
                     intent.style);
            ArenaDuel_AddEvent(event);
            ArenaDuel_CopyField(arena_duel_last_intent_id[participant],
                                sizeof(arena_duel_last_intent_id[participant]),
                                intent.intent_id);
            arena_duel_intent_was_active[participant] = true;
        }
        else if (!active && arena_duel_intent_was_active[participant])
        {
            snprintf(event,
                     sizeof(event),
                     "intent_expired: %s",
                     ArenaDuel_ParticipantName(participant));
            ArenaDuel_AddEvent(event);
            arena_duel_intent_was_active[participant] = false;
            arena_duel_last_intent_id[participant][0] = '\0';
        }
    }
}

static void ArenaDuel_LogAutopilotEvent(arena_participant_id_t participant)
{
    arena_participant_autopilot_debug_t debug;
    char key[192];
    char event[192];

    debug = ArenaParticipantAutopilot_Debug(participant);
    if (strcmp(debug.controller_mode, "autopilot"))
    {
        arena_duel_last_autopilot_key[participant][0] = '\0';
        arena_duel_stuck_recovery_was_active[participant] = false;
        return;
    }

    snprintf(key,
             sizeof(key),
             "%s|%s|%d",
             debug.autopilot_action,
             debug.autopilot_reason,
             debug.stuck_recovery);

    if (strcmp(arena_duel_last_autopilot_key[participant], key))
    {
        snprintf(event,
                 sizeof(event),
                 "autopilot_action: %s action=%s reason=%s aim_error=%d",
                 ArenaDuel_ParticipantName(participant),
                 debug.autopilot_action,
                 debug.autopilot_reason,
                 debug.aim_error);
        ArenaDuel_AddEvent(event);
        ArenaDuel_CopyField(arena_duel_last_autopilot_key[participant],
                            sizeof(arena_duel_last_autopilot_key[participant]),
                            key);
    }

    if (debug.stuck_recovery
        && !arena_duel_stuck_recovery_was_active[participant])
    {
        snprintf(event,
                 sizeof(event),
                 "stuck_recovery_started: %s",
                 ArenaDuel_ParticipantName(participant));
        ArenaDuel_AddEvent(event);
    }

    arena_duel_stuck_recovery_was_active[participant] = debug.stuck_recovery ? true : false;
}

static void ArenaDuel_Finish(const char *winner, const char *reason)
{
    char event[96];

    if (arena_duel_finished)
    {
        return;
    }

    arena_duel_finished = true;
    strncpy(arena_duel_winner, winner, sizeof(arena_duel_winner) - 1);
    arena_duel_winner[sizeof(arena_duel_winner) - 1] = '\0';
    strncpy(arena_duel_terminal_reason, reason, sizeof(arena_duel_terminal_reason) - 1);
    arena_duel_terminal_reason[sizeof(arena_duel_terminal_reason) - 1] = '\0';
    snprintf(event, sizeof(event), "match_finished: %s", reason);
    ArenaDuel_AddEvent(event);
}

static void ArenaDuel_Thrust(mobj_t *mobj, angle_t angle, fixed_t move)
{
    int fine_angle;

    fine_angle = angle >> ANGLETOFINESHIFT;
    mobj->momx += FixedMul(move, finecosine[fine_angle]);
    mobj->momy += FixedMul(move, finesine[fine_angle]);
}

static void ArenaDuel_RefillPlayer1Ammo(void)
{
    player_t *player;
    int i;

    player = &players[consoleplayer];
    for (i = 0; i < NUMAMMO; i++)
    {
        player->ammo[i] = player->maxammo[i];
    }
}

static void ArenaDuel_Player2Attack(void)
{
    fixed_t slope;
    int damage;

    if (arena_duel_player2 == NULL || arena_duel_player2->health <= 0)
    {
        return;
    }

    arena_duel_player2_attack_requests++;
    if (arena_duel_player2_attack_cooldown > 0)
    {
        return;
    }

    slope = P_AimLineAttack(arena_duel_player2,
                            arena_duel_player2->angle,
                            16 * 64 * FRACUNIT);
    if (slope == 0)
    {
        slope = P_AimLineAttack(arena_duel_player2,
                                arena_duel_player2->angle,
                                MISSILERANGE);
    }

    damage = 5 * (P_Random() % 3 + 1);
    P_LineAttack(arena_duel_player2,
                 arena_duel_player2->angle,
                 MISSILERANGE,
                 slope,
                 damage);
    S_StartSound(arena_duel_player2, sfx_pistol);

    arena_duel_player2_ammo_bullets = ARENA_DUEL_PLAYER2_BULLETS;
    arena_duel_player2_shots_fired++;
    arena_duel_player2_attack_cooldown = ARENA_DUEL_ATTACK_COOLDOWN_TICS;
    ArenaDuel_AddEvent("participant_fired: player_2");
}

static int ArenaDuel_Player2AutopilotStuckTicks(void)
{
    fixed_t delta;

    if (arena_duel_player2 == NULL)
    {
        arena_duel_player2_have_autopilot_position = false;
        arena_duel_player2_autopilot_stuck_ticks = 0;
        return 0;
    }

    if (!arena_duel_player2_have_autopilot_position)
    {
        arena_duel_player2_have_autopilot_position = true;
        arena_duel_player2_last_autopilot_x = arena_duel_player2->x;
        arena_duel_player2_last_autopilot_y = arena_duel_player2->y;
        arena_duel_player2_autopilot_stuck_ticks = 0;
        return 0;
    }

    delta = P_AproxDistance(arena_duel_player2->x - arena_duel_player2_last_autopilot_x,
                            arena_duel_player2->y - arena_duel_player2_last_autopilot_y);
    arena_duel_player2_last_autopilot_x = arena_duel_player2->x;
    arena_duel_player2_last_autopilot_y = arena_duel_player2->y;

    if ((delta >> FRACBITS) == 0)
    {
        arena_duel_player2_autopilot_stuck_ticks++;
    }
    else
    {
        arena_duel_player2_autopilot_stuck_ticks = 0;
    }

    return arena_duel_player2_autopilot_stuck_ticks;
}

static arena_participant_command_t ArenaDuel_Player2Command(void)
{
    arena_participant_command_t command;
    arena_participant_autopilot_input_t input;
    arena_participant_autopilot_command_t autopilot;
    player_t *player;
    angle_t angle_to_player1;

    command = ArenaParticipantCommands_Command(ARENA_PARTICIPANT_PLAYER_2);
    if (!ArenaParticipantIntent_HasActive(ARENA_PARTICIPANT_PLAYER_2))
    {
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_2,
                                                 "no_active_intent");
        return command;
    }

    player = &players[consoleplayer];
    if (player->mo == NULL || arena_duel_player2 == NULL)
    {
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_2,
                                                 "missing_participant_state");
        return command;
    }

    memset(&input, 0, sizeof(input));
    input.participant = ARENA_PARTICIPANT_PLAYER_2;
    input.intent = ArenaParticipantIntent_Get(ARENA_PARTICIPANT_PLAYER_2);
    input.self_x = arena_duel_player2->x >> FRACBITS;
    input.self_y = arena_duel_player2->y >> FRACBITS;
    input.self_angle = ArenaDuel_AngleDegrees(arena_duel_player2->angle);
    input.opponent_x = player->mo->x >> FRACBITS;
    input.opponent_y = player->mo->y >> FRACBITS;
    input.opponent_health = player->mo->health;
    input.self_ammo = arena_duel_player2_ammo_bullets;
    input.self_health = arena_duel_player2->health;
    input.distance = P_AproxDistance(arena_duel_player2->x - player->mo->x,
                                     arena_duel_player2->y - player->mo->y) >> FRACBITS;
    angle_to_player1 = R_PointToAngle2(arena_duel_player2->x,
                                       arena_duel_player2->y,
                                       player->mo->x,
                                       player->mo->y);
    input.relative_angle =
        -ArenaDuel_NormalizedAngleDegrees(angle_to_player1 - arena_duel_player2->angle);
    input.line_of_sight = P_CheckSight(arena_duel_player2, player->mo) ? 1 : 0;
    input.stuck_ticks = ArenaDuel_Player2AutopilotStuckTicks();
    input.tick = leveltime;
    input.phase_finished = arena_duel_finished ? 1 : 0;

    autopilot = ArenaParticipantAutopilot_Decide(&input);
    if (!autopilot.active)
    {
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_2,
                                                 autopilot.reason);
        return command;
    }

    ArenaParticipantAutopilot_RecordDecision(ARENA_PARTICIPANT_PLAYER_2,
                                             &input.intent,
                                             &autopilot);

    memset(&command, 0, sizeof(command));
    command.forward = autopilot.forward;
    command.strafe = autopilot.strafe;
    command.turn = autopilot.turn;
    command.attack = autopilot.attack;
    command.use = autopilot.use;
    command.active = true;
    command.valid = true;
    ArenaDuel_CopyField(command.command_id, sizeof(command.command_id), "player_2_autopilot");
    ArenaDuel_CopyField(command.status, sizeof(command.status), "autopilot");
    ArenaDuel_CopyField(command.last_action, sizeof(command.last_action), autopilot.action);
    return command;
}

boolean ArenaDuel_IsEnabled(void)
{
    return Arena_DuelModeEnabled()
        && gameepisode == 1
        && gamemap == 8;
}

void ArenaDuel_InitLevel(void)
{
    arena_duel_player2 = NULL;
    arena_duel_player2_ammo_bullets = ARENA_DUEL_PLAYER2_BULLETS;
    arena_duel_player2_attack_cooldown = 0;
    arena_duel_player2_attack_requests = 0;
    arena_duel_player2_shots_fired = 0;
    arena_duel_player1_shots_fired = 0;
    arena_duel_player1_shots_hit = 0;
    arena_duel_player2_shots_hit = 0;
    arena_duel_player1_damage_dealt = 0;
    arena_duel_player2_damage_dealt = 0;
    arena_duel_player1_invalid_actions = 0;
    arena_duel_player2_invalid_actions = 0;
    arena_duel_start_tick = leveltime;
    arena_duel_timeout_seconds = Arena_TimeoutSeconds();
    arena_duel_started = false;
    arena_duel_finished = false;
    arena_duel_winner[0] = '\0';
    arena_duel_terminal_reason[0] = '\0';
    arena_duel_last_player1_health = ARENA_DUEL_PARTICIPANT_HEALTH;
    arena_duel_last_player2_health = ARENA_DUEL_PARTICIPANT_HEALTH;
    arena_duel_last_player1_attack_command_id[0] = '\0';
    arena_duel_event_count = 0;
    arena_duel_player2_view_frame = 0;
    arena_duel_player2_view_nonzero_pixels = 0;
    arena_duel_player2_have_autopilot_position = false;
    arena_duel_player2_autopilot_stuck_ticks = 0;
    arena_duel_player1_health_initialized = false;
    arena_duel_waiting_event_logged = false;
    arena_duel_waiting_first_intents_event_logged = false;
    memset(arena_duel_last_intent_id, 0, sizeof(arena_duel_last_intent_id));
    memset(arena_duel_intent_was_active, 0, sizeof(arena_duel_intent_was_active));
    memset(arena_duel_last_autopilot_key, 0, sizeof(arena_duel_last_autopilot_key));
    memset(arena_duel_stuck_recovery_was_active,
           0,
           sizeof(arena_duel_stuck_recovery_was_active));
    ArenaParticipantCommands_Init();
    ArenaParticipantIntent_Init();
    ArenaParticipantAutopilot_ResetDebug();
}

void ArenaDuel_SpawnPlayer2(void)
{
    int x;
    int y;
    int angle;
    mobj_t *mobj;

    if (!ArenaDuel_IsEnabled())
    {
        return;
    }

    ArenaDuel_EnsurePlayer1Label();
    ArenaDuel_EnsurePlayer1StartingHealth();

    if (!Arena_GetSpawnSlot(0, &x, &y, &angle))
    {
        x = 424;
        y = 4041;
        angle = 267;
    }

    mobj = P_SpawnMobj(x << FRACBITS, y << FRACBITS, ONFLOORZ, MT_PLAYER);
    (void) angle;
    mobj->angle = ANG270;
    mobj->health = ARENA_DUEL_PARTICIPANT_HEALTH;
    mobj->flags &= ~(MF_PICKUP | MF_NOTDMATCH);
    mobj->arena_entity_index = ARENA_MAX_ENEMIES;
    strncpy(mobj->arena_entity_id,
            "player_2",
            sizeof(mobj->arena_entity_id) - 1);
    mobj->arena_entity_id[sizeof(mobj->arena_entity_id) - 1] = '\0';
    strncpy(mobj->arena_label,
            "player_2",
            sizeof(mobj->arena_label) - 1);
    mobj->arena_label[sizeof(mobj->arena_label) - 1] = '\0';

    arena_duel_player2 = mobj;
    arena_duel_last_player1_health = ArenaDuel_Player1Health();
    arena_duel_last_player2_health = mobj->health;

    printf("Doom Agent Arena: spawned duel player_2 at (%d, %d)\n",
           x,
           y);
    ArenaDuel_AddEvent("participant_spawned: player_2");
}

void ArenaDuel_Ticker(void)
{
    arena_participant_command_t command;
    arena_participant_command_t player1_command;
    int player1_health;
    int player2_health;
    int delta;

    if (!ArenaDuel_IsEnabled() || arena_duel_player2 == NULL)
    {
        return;
    }

    ArenaDuel_EnsurePlayer1Label();
    ArenaDuel_EnsurePlayer1StartingHealth();
    ArenaDuel_RefillPlayer1Ammo();
    arena_duel_player2_ammo_bullets = ARENA_DUEL_PLAYER2_BULLETS;

    ArenaParticipantCommands_Load();
    ArenaParticipantIntent_TickOrRefresh();
    ArenaDuel_LogIntentEvents();
    ArenaDuel_UpdateStartBarrier();

    if (!arena_duel_started)
    {
        const char *wait_reason;

        wait_reason = ArenaDuel_StartWaitReason();
        arena_duel_player2->momx = 0;
        arena_duel_player2->momy = 0;
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                 wait_reason);
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_2,
                                                 wait_reason);
        return;
    }

    ArenaDuel_LogAutopilotEvent(ARENA_PARTICIPANT_PLAYER_1);
    player1_command = ArenaParticipantCommands_Command(ARENA_PARTICIPANT_PLAYER_1);

    if (player1_command.attack
        && strcmp(player1_command.command_id, arena_duel_last_player1_attack_command_id))
    {
        strncpy(arena_duel_last_player1_attack_command_id,
                player1_command.command_id,
                sizeof(arena_duel_last_player1_attack_command_id) - 1);
        arena_duel_last_player1_attack_command_id[sizeof(arena_duel_last_player1_attack_command_id) - 1] = '\0';
        arena_duel_player1_shots_fired++;
        ArenaDuel_AddEvent("participant_fired: player_1");
    }

    player1_health = ArenaDuel_Player1Health();
    player2_health = arena_duel_player2->health;

    if (player1_health < arena_duel_last_player1_health)
    {
        delta = arena_duel_last_player1_health - player1_health;
        arena_duel_player2_damage_dealt += delta;
        arena_duel_player2_shots_hit++;
        ArenaDuel_AddEvent("participant_hit: player_2 hit player_1");
    }
    if (player2_health < arena_duel_last_player2_health)
    {
        delta = arena_duel_last_player2_health - player2_health;
        arena_duel_player1_damage_dealt += delta;
        arena_duel_player1_shots_hit++;
        ArenaDuel_AddEvent("participant_hit: player_1 hit player_2");
    }

    arena_duel_last_player1_health = player1_health;
    arena_duel_last_player2_health = player2_health;

    if (player1_health <= 0)
    {
        ArenaDuel_Finish("player_2", "player_1_dead");
    }
    else if (player2_health <= 0)
    {
        ArenaDuel_Finish("player_1", "player_2_dead");
    }
    else if (ArenaDuel_ElapsedMs() >= arena_duel_timeout_seconds * 1000)
    {
        if (player1_health > player2_health)
        {
            ArenaDuel_Finish("player_1", "timeout_health");
        }
        else if (player2_health > player1_health)
        {
            ArenaDuel_Finish("player_2", "timeout_health");
        }
        else
        {
            ArenaDuel_Finish("draw", "timeout_draw");
        }
    }

    if (arena_duel_finished)
    {
        arena_duel_player2->momx = 0;
        arena_duel_player2->momy = 0;
        return;
    }

    if (arena_duel_player2_attack_cooldown > 0)
    {
        arena_duel_player2_attack_cooldown--;
    }

    if (arena_duel_player2->health <= 0)
    {
        arena_duel_player2->momx = 0;
        arena_duel_player2->momy = 0;
        return;
    }

    command = ArenaDuel_Player2Command();
    ArenaDuel_LogAutopilotEvent(ARENA_PARTICIPANT_PLAYER_2);

    arena_duel_player2->angle += (angle_t) (-command.turn * ARENA_DUEL_TURN_SPEED) << FRACBITS;

    if (command.forward != 0)
    {
        ArenaDuel_Thrust(arena_duel_player2,
                         arena_duel_player2->angle,
                         command.forward * ARENA_DUEL_MOVE_SPEED);
    }

    if (command.strafe != 0)
    {
        ArenaDuel_Thrust(arena_duel_player2,
                         arena_duel_player2->angle - ANG90,
                         command.strafe * ARENA_DUEL_SIDE_SPEED);
    }

    if (command.attack)
    {
        ArenaDuel_Player2Attack();
    }
}

boolean ArenaDuel_IsPlayer2(const mobj_t *mobj)
{
    return mobj != NULL && mobj == arena_duel_player2;
}

boolean ArenaDuel_IsFinished(void)
{
    return arena_duel_finished;
}

boolean ArenaDuel_IsStarted(void)
{
    return arena_duel_started;
}

mobj_t *ArenaDuel_Player2Mobj(void)
{
    return arena_duel_player2;
}

int ArenaDuel_Player2AmmoBullets(void)
{
    return arena_duel_player2_ammo_bullets;
}

int ArenaDuel_ElapsedMs(void)
{
    int elapsed_ticks;

    elapsed_ticks = leveltime - arena_duel_start_tick;
    if (!arena_duel_started && !arena_duel_finished)
    {
        elapsed_ticks = 0;
    }
    if (elapsed_ticks < 0)
    {
        elapsed_ticks = 0;
    }

    return (elapsed_ticks * 1000) / TICRATE;
}

int ArenaDuel_ElapsedSecondsTenths(void)
{
    return ArenaDuel_ElapsedMs() / 100;
}

int ArenaDuel_TimeoutSeconds(void)
{
    return arena_duel_timeout_seconds;
}

const char *ArenaDuel_Phase(void)
{
    if (arena_duel_finished)
    {
        return "finished";
    }
    return arena_duel_started ? "combat" : "waiting_for_agents";
}

const char *ArenaDuel_Winner(void)
{
    return arena_duel_finished ? arena_duel_winner : "";
}

const char *ArenaDuel_TerminalReason(void)
{
    return arena_duel_finished ? arena_duel_terminal_reason : "";
}

int ArenaDuel_Player1DamageDealt(void)
{
    return arena_duel_player1_damage_dealt;
}

int ArenaDuel_Player2DamageDealt(void)
{
    return arena_duel_player2_damage_dealt;
}

int ArenaDuel_Player1ShotsFired(void)
{
    return arena_duel_player1_shots_fired;
}

int ArenaDuel_Player2AttackRequests(void)
{
    return arena_duel_player2_attack_requests;
}

int ArenaDuel_Player2ShotsFired(void)
{
    return arena_duel_player2_shots_fired;
}

int ArenaDuel_Player1ShotsHit(void)
{
    return arena_duel_player1_shots_hit;
}

int ArenaDuel_Player2ShotsHit(void)
{
    return arena_duel_player2_shots_hit;
}

int ArenaDuel_Player1InvalidActions(void)
{
    return arena_duel_player1_invalid_actions;
}

int ArenaDuel_Player2InvalidActions(void)
{
    return arena_duel_player2_invalid_actions;
}

int ArenaDuel_EventCount(void)
{
    return arena_duel_event_count;
}

const char *ArenaDuel_Event(int index)
{
    if (index < 0 || index >= arena_duel_event_count)
    {
        return "";
    }

    return arena_duel_events[index];
}

void ArenaDuel_WriteEvents(void)
{
    FILE *file;
    int i;

    if (!ArenaDuel_IsEnabled())
    {
        return;
    }

    file = fopen(ARENA_DUEL_EVENTS_PATH, "w");
    if (file == NULL)
    {
        return;
    }

    fprintf(file, "run_id\tscenario_id\ttick\ttimestamp_ms\tevent\n");
    for (i = 0; i < arena_duel_event_count; i++)
    {
        fprintf(file,
                "%s\t%s\t%d\t%s\n",
                Arena_RunId(),
                Arena_ScenarioId(),
                leveltime,
                arena_duel_events[i]);
    }

    fclose(file);
}

void ArenaDuel_RenderPlayer2View(void)
{
    pixel_t *saved_video_buffer;
    int i;
    int nonzero_pixels;

    if (!ArenaDuel_IsEnabled()
        || arena_duel_player2 == NULL
        || arena_duel_player2->health <= 0
        || !ArenaDuel_EnsurePlayer2ViewBuffers())
    {
        return;
    }

    saved_video_buffer = I_VideoBuffer;
    memset(arena_duel_player2_view_buffer,
           0,
           SCREENWIDTH * SCREENHEIGHT * sizeof(pixel_t));

    I_VideoBuffer = arena_duel_player2_view_buffer;
    V_RestoreBuffer();
    R_InitBuffer(scaledviewwidth, viewheight);
    R_RenderMobjView(arena_duel_player2, &players[displayplayer]);

    nonzero_pixels = 0;
    for (i = 0; i < SCREENWIDTH * SCREENHEIGHT; i++)
    {
        if (arena_duel_player2_view_buffer[i] != 0)
        {
            nonzero_pixels++;
        }
    }
    arena_duel_player2_view_nonzero_pixels = nonzero_pixels;

    I_ConvertPalettedBufferToRGBA(arena_duel_player2_view_buffer,
                                  arena_duel_player2_view_rgba,
                                  SCREENWIDTH * SCREENHEIGHT);
    arena_duel_player2_view_frame++;

    I_VideoBuffer = saved_video_buffer;
    V_RestoreBuffer();
    R_InitBuffer(scaledviewwidth, viewheight);
}

ARENA_DUEL_EXPORT int ArenaDuel_Player2ViewWidth(void)
{
    return SCREENWIDTH;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player2ViewHeight(void)
{
    return viewheight > 0 ? viewheight : SCREENHEIGHT;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player2ViewFrame(void)
{
    return arena_duel_player2_view_frame;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player2ViewNonzeroPixels(void)
{
    return arena_duel_player2_view_nonzero_pixels;
}

ARENA_DUEL_EXPORT uintptr_t ArenaDuel_Player2ViewPaletted(void)
{
    return (uintptr_t) arena_duel_player2_view_buffer;
}

ARENA_DUEL_EXPORT uintptr_t ArenaDuel_Player2ViewRGBA(void)
{
    return (uintptr_t) arena_duel_player2_view_rgba;
}

void ArenaDuel_RenderPlayer1View(void)
{
    pixel_t *saved_video_buffer;
    mobj_t *player1_mo;
    int i;
    int nonzero_pixels;

    if (!ArenaDuel_IsEnabled()
        || !ArenaDuel_EnsurePlayer1ViewBuffers())
    {
        return;
    }

    player1_mo = players[consoleplayer].mo;
    if (player1_mo == NULL || player1_mo->health <= 0)
    {
        return;
    }

    saved_video_buffer = I_VideoBuffer;
    memset(arena_duel_player1_view_buffer,
           0,
           SCREENWIDTH * SCREENHEIGHT * sizeof(pixel_t));

    I_VideoBuffer = arena_duel_player1_view_buffer;
    V_RestoreBuffer();
    R_InitBuffer(scaledviewwidth, viewheight);
    R_RenderMobjView(player1_mo, &players[displayplayer]);

    nonzero_pixels = 0;
    for (i = 0; i < SCREENWIDTH * SCREENHEIGHT; i++)
    {
        if (arena_duel_player1_view_buffer[i] != 0)
        {
            nonzero_pixels++;
        }
    }
    arena_duel_player1_view_nonzero_pixels = nonzero_pixels;

    I_ConvertPalettedBufferToRGBA(arena_duel_player1_view_buffer,
                                  arena_duel_player1_view_rgba,
                                  SCREENWIDTH * SCREENHEIGHT);
    arena_duel_player1_view_frame++;

    I_VideoBuffer = saved_video_buffer;
    V_RestoreBuffer();
    R_InitBuffer(scaledviewwidth, viewheight);
}

ARENA_DUEL_EXPORT int ArenaDuel_Player1ViewWidth(void)
{
    return SCREENWIDTH;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player1ViewHeight(void)
{
    return viewheight > 0 ? viewheight : SCREENHEIGHT;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player1ViewFrame(void)
{
    return arena_duel_player1_view_frame;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player1ViewNonzeroPixels(void)
{
    return arena_duel_player1_view_nonzero_pixels;
}

ARENA_DUEL_EXPORT uintptr_t ArenaDuel_Player1ViewPaletted(void)
{
    return (uintptr_t) arena_duel_player1_view_buffer;
}

ARENA_DUEL_EXPORT uintptr_t ArenaDuel_Player1ViewRGBA(void)
{
    return (uintptr_t) arena_duel_player1_view_rgba;
}

ARENA_DUEL_EXPORT uintptr_t ArenaDuel_PalettePointer(void)
{
    return I_GetPaletteData();
}
