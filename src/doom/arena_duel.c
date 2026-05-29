//
// Doom Agent Arena duel mode.
//

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <limits.h>
#include <string.h>

#include "doomdef.h"
#include "doomstat.h"
#include "d_items.h"
#include "info.h"
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
#include "arena_player_control.h"

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
#define ARENA_DUEL_SHOTGUN_COOLDOWN_TICS 28
#define ARENA_DUEL_UNSTICK_DISTANCE 128
#define ARENA_DUEL_UNSTICK_PUSH_SPEED (0x24 * 2048)
#define ARENA_DUEL_MAX_EVENTS 4096
#define ARENA_DUEL_PATH_LOG_INTERVAL_TICKS 9

typedef enum
{
    ARENA_DUEL_SPAWN_OPEN = 0,
    ARENA_DUEL_SPAWN_BLIND = 1,
    ARENA_DUEL_SPAWN_CORNER = 2,
    ARENA_DUEL_SPAWN_CENTER = 3,
} arena_duel_spawn_variant_t;

static arena_duel_spawn_variant_t ArenaDuel_SpawnVariant(void)
{
    const char *scenario_id = Arena_ScenarioId();
    if (scenario_id == NULL)
    {
        return ARENA_DUEL_SPAWN_OPEN;
    }
    if (!strcmp(scenario_id, "duel_e1m8_blind_spawn"))
    {
        return ARENA_DUEL_SPAWN_BLIND;
    }
    if (!strcmp(scenario_id, "duel_e1m8_corner_spawn"))
    {
        return ARENA_DUEL_SPAWN_CORNER;
    }
    if (!strcmp(scenario_id, "duel_e1m8_center_spawn"))
    {
        return ARENA_DUEL_SPAWN_CENTER;
    }
    return ARENA_DUEL_SPAWN_OPEN;
}

static mobj_t *arena_duel_player2;
static mobj_t *arena_duel_player1_cached_mo;
#define ARENA_DUEL_EVENTS_PATH "arena_duel_events.local.tsv"
#define ARENA_DUEL_PARTICIPANT_READY_PATH "arena_participant_ready.local.tsv"
#define ARENA_DUEL_PARTICIPANT_HEALTH 150
#define ARENA_DUEL_PLAYER2_BULLETS 200
#define ARENA_DUEL_AUTOMAP_WIDTH 512
#define ARENA_DUEL_AUTOMAP_HEIGHT 384
#define ARENA_DUEL_VIEW_HALF_ANGLE_DEGREES 45
#define ARENA_DUEL_HIT_REVEAL_TICKS 140

// players[consoleplayer].mo gets nulled by Doom's deathmatch init flow after
// P_SpawnPlayer runs (the exact null-out path isn't pinned down), which breaks
// ArenaDuel_RenderPlayer1View. We cache the most recently spawned player_1
// mobj here from P_SpawnPlayer and use it as a fallback. The cache is cleared
// in ArenaDuel_InitLevel so dangling pointers don't survive a level reload.
static int arena_duel_player2_ammo_bullets;
static int arena_duel_player2_ammo_shells;
static int arena_duel_player1_attack_cooldown;
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
static int arena_duel_player1_reveal_until_tick;
static int arena_duel_player2_reveal_until_tick;
static int arena_duel_start_tick;
static int arena_duel_timeout_seconds;
static boolean arena_duel_started;
static int arena_duel_finished;
static char arena_duel_winner[16];
static char arena_duel_terminal_reason[32];
static int arena_duel_last_player1_health;
static int arena_duel_last_player2_health;
static char arena_duel_events[ARENA_DUEL_MAX_EVENTS][192];
static int arena_duel_event_count;
static char arena_duel_last_intent_id[ARENA_PARTICIPANT_COUNT][64];
static boolean arena_duel_intent_was_active[ARENA_PARTICIPANT_COUNT];
static char arena_duel_last_autopilot_key[ARENA_PARTICIPANT_COUNT][192];
static boolean arena_duel_stuck_recovery_was_active[ARENA_PARTICIPANT_COUNT];
static boolean arena_duel_path_log_have_position[ARENA_PARTICIPANT_COUNT];
static int arena_duel_path_log_last_tick[ARENA_PARTICIPANT_COUNT];
static int arena_duel_path_log_last_x[ARENA_PARTICIPANT_COUNT];
static int arena_duel_path_log_last_y[ARENA_PARTICIPANT_COUNT];
static int arena_duel_path_log_last_angle[ARENA_PARTICIPANT_COUNT];
static pixel_t *arena_duel_player1_view_buffer;
static byte *arena_duel_player1_view_rgba;
static int arena_duel_player1_view_frame;
static int arena_duel_player1_view_nonzero_pixels;
static byte *arena_duel_player1_automap_rgba;
static int arena_duel_player1_automap_frame;
static int arena_duel_player1_automap_nonzero_pixels;
static pixel_t *arena_duel_player2_view_buffer;
static byte *arena_duel_player2_view_rgba;
static int arena_duel_player2_view_frame;
static int arena_duel_player2_view_nonzero_pixels;
static fixed_t arena_duel_player2_last_autopilot_x;
static fixed_t arena_duel_player2_last_autopilot_y;
static fixed_t arena_duel_player1_last_autopilot_x;
static fixed_t arena_duel_player1_last_autopilot_y;
static int arena_duel_player1_autopilot_stuck_ticks;
static int arena_duel_player2_autopilot_stuck_ticks;
static boolean arena_duel_player1_have_autopilot_position;
static boolean arena_duel_player2_have_autopilot_position;
static arena_participant_autopilot_command_t arena_duel_player1_last_autopilot_command;
static arena_participant_autopilot_command_t arena_duel_player2_last_autopilot_command;
static boolean arena_duel_waiting_event_logged;
static boolean arena_duel_waiting_first_intents_event_logged;
static boolean arena_duel_player1_health_initialized;
static player_t arena_duel_player2_view_player;
static boolean arena_duel_player2_view_player_initialized;
static int arena_duel_player2_view_player_last_tick;
static weapontype_t arena_duel_player2_ready_weapon;

static void ArenaDuel_AddEvent(const char *message);

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

static player_t *ArenaDuel_Player2ViewPlayer(void)
{
    int i;
    weapontype_t ready_weapon;

    if (arena_duel_player2 == NULL)
    {
        return &players[displayplayer];
    }

    ready_weapon = arena_duel_player2_ready_weapon;
    if (ready_weapon <= wp_fist || ready_weapon >= NUMWEAPONS)
    {
        ready_weapon = wp_pistol;
    }

    if (!arena_duel_player2_view_player_initialized)
    {
        memset(&arena_duel_player2_view_player, 0, sizeof(arena_duel_player2_view_player));
        arena_duel_player2_view_player = players[displayplayer];
        arena_duel_player2_view_player.mo = arena_duel_player2;
        arena_duel_player2_view_player.health = arena_duel_player2->health;
        arena_duel_player2_view_player.readyweapon = ready_weapon;
        arena_duel_player2_view_player.pendingweapon = ready_weapon;
        for (i = 0; i < NUMWEAPONS; i++)
        {
            arena_duel_player2_view_player.weaponowned[i] = false;
        }
        for (i = 0; i < NUMAMMO; i++)
        {
            arena_duel_player2_view_player.ammo[i] = 0;
            arena_duel_player2_view_player.maxammo[i] = 0;
        }
        arena_duel_player2_view_player.weaponowned[wp_fist] = true;
        arena_duel_player2_view_player.weaponowned[wp_pistol] = true;
        arena_duel_player2_view_player.weaponowned[ready_weapon] = true;
        arena_duel_player2_view_player.ammo[am_clip] = ARENA_DUEL_PLAYER2_BULLETS;
        arena_duel_player2_view_player.maxammo[am_clip] = ARENA_DUEL_PLAYER2_BULLETS;
        arena_duel_player2_view_player.ammo[am_shell] = arena_duel_player2_ammo_shells;
        arena_duel_player2_view_player.maxammo[am_shell] = 200;
        P_SetupPsprites(&arena_duel_player2_view_player);
        arena_duel_player2_view_player_initialized = true;
        arena_duel_player2_view_player_last_tick = -1;
    }

    arena_duel_player2_view_player.mo = arena_duel_player2;
    arena_duel_player2_view_player.health = arena_duel_player2->health;
    arena_duel_player2_view_player.readyweapon = ready_weapon;
    arena_duel_player2_view_player.weaponowned[wp_fist] = true;
    arena_duel_player2_view_player.weaponowned[wp_pistol] = true;
    arena_duel_player2_view_player.weaponowned[ready_weapon] = true;
    arena_duel_player2_view_player.ammo[am_clip] = arena_duel_player2_ammo_bullets;
    arena_duel_player2_view_player.maxammo[am_clip] = ARENA_DUEL_PLAYER2_BULLETS;
    arena_duel_player2_view_player.ammo[am_shell] = arena_duel_player2_ammo_shells;
    arena_duel_player2_view_player.maxammo[am_shell] = 200;

    if (arena_duel_player2_view_player_last_tick != leveltime)
    {
        P_MovePsprites(&arena_duel_player2_view_player);
        arena_duel_player2_view_player_last_tick = leveltime;
    }

    return &arena_duel_player2_view_player;
}

static void ArenaDuel_SetPlayer2ViewPsprite(int position, statenum_t state)
{
    pspdef_t *psp;

    if (position < 0 || position >= NUMPSPRITES || state <= S_NULL || state >= NUMSTATES)
    {
        return;
    }

    psp = &arena_duel_player2_view_player.psprites[position];
    psp->state = &states[state];
    psp->tics = states[state].tics;
    psp->sx = states[state].misc1;
    psp->sy = states[state].misc2;
}

static void ArenaDuel_SetPlayer1ViewPsprite(int position, statenum_t state)
{
    player_t *player;
    pspdef_t *psp;

    if (position < 0 || position >= NUMPSPRITES || state <= S_NULL || state >= NUMSTATES)
    {
        return;
    }

    player = &players[consoleplayer];
    psp = &player->psprites[position];
    psp->state = &states[state];
    psp->tics = states[state].tics;
    psp->sx = states[state].misc1;
    psp->sy = states[state].misc2;
}

static void ArenaDuel_TriggerPlayer1ViewFire(weapontype_t ready_weapon)
{
    statenum_t weapon_state;
    statenum_t flash_state;

    if (ready_weapon <= wp_fist || ready_weapon >= NUMWEAPONS)
    {
        ready_weapon = wp_pistol;
    }

    weapon_state = weaponinfo[ready_weapon].atkstate;
    flash_state = weaponinfo[ready_weapon].flashstate;
    if (ready_weapon == wp_pistol && weapon_state == S_PISTOL1)
    {
        weapon_state = S_PISTOL2;
    }
    else if (ready_weapon == wp_shotgun && weapon_state == S_SGUN1)
    {
        weapon_state = S_SGUN2;
    }

    ArenaDuel_SetPlayer1ViewPsprite(ps_weapon, weapon_state);
    ArenaDuel_SetPlayer1ViewPsprite(ps_flash, flash_state);
}

static void ArenaDuel_TriggerPlayer2ViewFire(void)
{
    weapontype_t ready_weapon;
    statenum_t weapon_state;
    statenum_t flash_state;

    if (arena_duel_player2 == NULL)
    {
        return;
    }

    ArenaDuel_Player2ViewPlayer();
    ready_weapon = arena_duel_player2_ready_weapon;
    if (ready_weapon <= wp_fist || ready_weapon >= NUMWEAPONS)
    {
        ready_weapon = wp_pistol;
    }

    weapon_state = weaponinfo[ready_weapon].atkstate;
    flash_state = weaponinfo[ready_weapon].flashstate;
    if (ready_weapon == wp_pistol && weapon_state == S_PISTOL1)
    {
        weapon_state = S_PISTOL2;
    }
    else if (ready_weapon == wp_shotgun && weapon_state == S_SGUN1)
    {
        weapon_state = S_SGUN2;
    }

    ArenaDuel_SetPlayer2ViewPsprite(ps_weapon, weapon_state);
    ArenaDuel_SetPlayer2ViewPsprite(ps_flash, flash_state);
}

static void ArenaDuel_SetPlayer2ViewReadyWeapon(weapontype_t ready_weapon)
{
    if (ready_weapon <= wp_fist || ready_weapon >= NUMWEAPONS)
    {
        ready_weapon = wp_pistol;
    }

    ArenaDuel_Player2ViewPlayer();
    arena_duel_player2_view_player.readyweapon = ready_weapon;
    arena_duel_player2_view_player.pendingweapon = ready_weapon;
    arena_duel_player2_view_player.weaponowned[ready_weapon] = true;
    arena_duel_player2_view_player.ammo[am_clip] = arena_duel_player2_ammo_bullets;
    arena_duel_player2_view_player.maxammo[am_clip] = ARENA_DUEL_PLAYER2_BULLETS;
    arena_duel_player2_view_player.ammo[am_shell] = arena_duel_player2_ammo_shells;
    arena_duel_player2_view_player.maxammo[am_shell] = 200;
    ArenaDuel_SetPlayer2ViewPsprite(ps_weapon, weaponinfo[ready_weapon].readystate);
}

static int ArenaDuel_AbsInt(int value)
{
    return value < 0 ? -value : value;
}

static void ArenaDuel_LogCollisionProfile(const char *participant, const mobj_t *mobj)
{
    char event[192];

    if (participant == NULL || mobj == NULL)
    {
        return;
    }

    snprintf(event,
             sizeof(event),
             "collision_profile: %s radius=%d height=%d flags=%d type=%d",
             participant,
             mobj->radius >> FRACBITS,
             mobj->height >> FRACBITS,
             mobj->flags,
             mobj->type);
    ArenaDuel_AddEvent(event);
}

boolean ArenaDuel_Player1CanSeePlayer2(int relative_angle, int geometric_line_of_sight)
{
    if (!geometric_line_of_sight)
    {
        return false;
    }

    return ArenaDuel_AbsInt(relative_angle) <= ARENA_DUEL_VIEW_HALF_ANGLE_DEGREES
        || leveltime <= arena_duel_player1_reveal_until_tick;
}

boolean ArenaDuel_Player2CanSeePlayer1(int relative_angle, int geometric_line_of_sight)
{
    if (!geometric_line_of_sight)
    {
        return false;
    }

    return ArenaDuel_AbsInt(relative_angle) <= ARENA_DUEL_VIEW_HALF_ANGLE_DEGREES
        || leveltime <= arena_duel_player2_reveal_until_tick;
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

static mobj_t *ArenaDuel_Player1Mobj(void)
{
    if (players[consoleplayer].mo != NULL)
    {
        return players[consoleplayer].mo;
    }

    return arena_duel_player1_cached_mo;
}

static boolean ArenaDuel_EnsurePlayer1ViewBuffers(void)
{
    size_t paletted_size;
    size_t rgba_size;

    paletted_size = SCREENWIDTH * SCREENHEIGHT * sizeof(pixel_t);
    rgba_size = ARENA_DUEL_AUTOMAP_WIDTH * ARENA_DUEL_AUTOMAP_HEIGHT * 4;

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
    rgba_size = ARENA_DUEL_AUTOMAP_WIDTH * ARENA_DUEL_AUTOMAP_HEIGHT * 4;

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

static boolean ArenaDuel_EnsurePlayer1AutomapBuffer(void)
{
    size_t rgba_size;

    rgba_size = ARENA_DUEL_AUTOMAP_WIDTH * ARENA_DUEL_AUTOMAP_HEIGHT * 4;
    if (arena_duel_player1_automap_rgba == NULL)
    {
        arena_duel_player1_automap_rgba = malloc(rgba_size);
    }

    return arena_duel_player1_automap_rgba != NULL;
}

static void ArenaDuel_AutomapPutPixel(byte *buffer,
                                      int x,
                                      int y,
                                      byte r,
                                      byte g,
                                      byte b)
{
    int index;

    if (x < 0 || x >= ARENA_DUEL_AUTOMAP_WIDTH || y < 0 || y >= ARENA_DUEL_AUTOMAP_HEIGHT)
    {
        return;
    }

    index = (y * ARENA_DUEL_AUTOMAP_WIDTH + x) * 4;
    buffer[index + 0] = r;
    buffer[index + 1] = g;
    buffer[index + 2] = b;
    buffer[index + 3] = 255;
}

static void ArenaDuel_AutomapDrawLine(byte *buffer,
                                      int x0,
                                      int y0,
                                      int x1,
                                      int y1,
                                      byte r,
                                      byte g,
                                      byte b)
{
    int dx;
    int sx;
    int dy;
    int sy;
    int err;
    int e2;

    dx = abs(x1 - x0);
    sx = x0 < x1 ? 1 : -1;
    dy = -abs(y1 - y0);
    sy = y0 < y1 ? 1 : -1;
    err = dx + dy;

    for (;;)
    {
        ArenaDuel_AutomapPutPixel(buffer, x0, y0, r, g, b);
        if (x0 == x1 && y0 == y1)
        {
            break;
        }
        e2 = 2 * err;
        if (e2 >= dy)
        {
            err += dy;
            x0 += sx;
        }
        if (e2 <= dx)
        {
            err += dx;
            y0 += sy;
        }
    }
}

static void ArenaDuel_AutomapFillRect(byte *buffer,
                                      int x0,
                                      int y0,
                                      int x1,
                                      int y1,
                                      byte r,
                                      byte g,
                                      byte b)
{
    int x;
    int y;
    int min_x;
    int max_x;
    int min_y;
    int max_y;

    min_x = x0 < x1 ? x0 : x1;
    max_x = x0 > x1 ? x0 : x1;
    min_y = y0 < y1 ? y0 : y1;
    max_y = y0 > y1 ? y0 : y1;

    for (y = min_y; y <= max_y; y++)
    {
        for (x = min_x; x <= max_x; x++)
        {
            ArenaDuel_AutomapPutPixel(buffer, x, y, r, g, b);
        }
    }
}
static void ArenaDuel_AutomapDrawBox(byte *buffer,
                                     int x,
                                     int y,
                                     int radius,
                                     byte r,
                                     byte g,
                                     byte b)
{
    int dx;
    int dy;

    for (dy = -radius; dy <= radius; dy++)
    {
        for (dx = -radius; dx <= radius; dx++)
        {
            ArenaDuel_AutomapPutPixel(buffer, x + dx, y + dy, r, g, b);
        }
    }
}

static void ArenaDuel_AutomapBounds(int *min_x, int *max_x, int *min_y, int *max_y)
{
    int i;
    int x;
    int y;

    *min_x = INT_MAX;
    *max_x = INT_MIN;
    *min_y = INT_MAX;
    *max_y = INT_MIN;

    for (i = 0; i < numvertexes; i++)
    {
        x = vertexes[i].x >> FRACBITS;
        y = vertexes[i].y >> FRACBITS;
        if (x < *min_x)
        {
            *min_x = x;
        }
        if (x > *max_x)
        {
            *max_x = x;
        }
        if (y < *min_y)
        {
            *min_y = y;
        }
        if (y > *max_y)
        {
            *max_y = y;
        }
    }

    if (*min_x == INT_MAX || *max_x <= *min_x || *max_y <= *min_y)
    {
        *min_x = -1024;
        *max_x = 1024;
        *min_y = -768;
        *max_y = 768;
    }
}

static int ArenaDuel_AutomapScreenX(fixed_t world_x,
                                    int min_x,
                                    double scale,
                                    int padding)
{
    return padding + (int) (((world_x >> FRACBITS) - min_x) * scale + 0.5);
}

static int ArenaDuel_AutomapScreenY(fixed_t world_y,
                                    int min_y,
                                    double scale,
                                    int padding)
{
    return ARENA_DUEL_AUTOMAP_HEIGHT - 1 - padding - (int) (((world_y >> FRACBITS) - min_y) * scale + 0.5);
}

static void ArenaDuel_AutomapDrawPlayer(byte *buffer,
                                        mobj_t *mobj,
                                        int min_x,
                                        int min_y,
                                        double scale,
                                        int padding,
                                        byte r,
                                        byte g,
                                        byte b)
{
    int x;
    int y;
    int angle_index;
    int dx;
    int dy;

    if (mobj == NULL)
    {
        return;
    }

    x = ArenaDuel_AutomapScreenX(mobj->x, min_x, scale, padding);
    y = ArenaDuel_AutomapScreenY(mobj->y, min_y, scale, padding);
    ArenaDuel_AutomapDrawBox(buffer, x, y, 2, r, g, b);

    angle_index = mobj->angle >> ANGLETOFINESHIFT;
    dx = (int) (((int64_t) finecosine[angle_index] * 14) >> FRACBITS);
    dy = (int) (((int64_t) finesine[angle_index] * 14) >> FRACBITS);
    ArenaDuel_AutomapDrawLine(buffer, x, y, x + dx, y - dy, r, g, b);
}

void ArenaDuel_RenderPlayer1Automap(void)
{
    mobj_t *player1_mo;
    int min_x;
    int max_x;
    int min_y;
    int max_y;
    int padding;
    int map_width;
    int map_height;
    double scale_x;
    double scale_y;
    double scale;
    int i;
    int j;
    int k;
    int target;
    int wall_count;
    int x0;
    int y0;
    int x1;
    int y1;
    int line_x0;
    int line_y0;
    int line_x1;
    int line_y1;
    int line_min_x;
    int line_max_x;
    int line_min_y;
    int line_max_y;
    int wall_min_x[16];
    int wall_max_x[16];
    int wall_min_y[16];
    int wall_max_y[16];
    boolean line_on_map_border;
    boolean line_inside_wall_fill;
    boolean overlaps;
    line_t *line;

    if (!ArenaDuel_IsEnabled() || !ArenaDuel_EnsurePlayer1AutomapBuffer())
    {
        return;
    }

    for (i = 0; i < ARENA_DUEL_AUTOMAP_WIDTH * ARENA_DUEL_AUTOMAP_HEIGHT; i++)
    {
        arena_duel_player1_automap_rgba[i * 4 + 0] = 11;
        arena_duel_player1_automap_rgba[i * 4 + 1] = 15;
        arena_duel_player1_automap_rgba[i * 4 + 2] = 13;
        arena_duel_player1_automap_rgba[i * 4 + 3] = 255;
    }

    ArenaDuel_AutomapBounds(&min_x, &max_x, &min_y, &max_y);
    padding = 0;
    map_width = max_x - min_x;
    map_height = max_y - min_y;
    scale_x = (double) (ARENA_DUEL_AUTOMAP_WIDTH - 1 - padding * 2) / (double) (map_width > 0 ? map_width : 1);
    scale_y = (double) (ARENA_DUEL_AUTOMAP_HEIGHT - 1 - padding * 2) / (double) (map_height > 0 ? map_height : 1);
    scale = scale_x < scale_y ? scale_x : scale_y;

    wall_count = 0;

    for (i = 0; i < numlines; i++)
    {
        line = &lines[i];
        if (line->backsector)
        {
            continue;
        }

        line_x0 = line->v1->x >> FRACBITS;
        line_y0 = line->v1->y >> FRACBITS;
        line_x1 = line->v2->x >> FRACBITS;
        line_y1 = line->v2->y >> FRACBITS;
        line_on_map_border = ((line_x0 == min_x && line_x1 == min_x)
                              || (line_x0 == max_x && line_x1 == max_x)
                              || (line_y0 == min_y && line_y1 == min_y)
                              || (line_y0 == max_y && line_y1 == max_y));
        if (line_on_map_border)
        {
            continue;
        }

        line_min_x = line_x0 < line_x1 ? line_x0 : line_x1;
        line_max_x = line_x0 > line_x1 ? line_x0 : line_x1;
        line_min_y = line_y0 < line_y1 ? line_y0 : line_y1;
        line_max_y = line_y0 > line_y1 ? line_y0 : line_y1;
        target = -1;

        for (j = 0; j < wall_count; j++)
        {
            overlaps = line_max_x >= wall_min_x[j]
                && line_min_x <= wall_max_x[j]
                && line_max_y >= wall_min_y[j]
                && line_min_y <= wall_max_y[j];
            if (!overlaps)
            {
                continue;
            }

            if (target < 0)
            {
                target = j;
            }
            else
            {
                if (wall_min_x[j] < wall_min_x[target]) wall_min_x[target] = wall_min_x[j];
                if (wall_max_x[j] > wall_max_x[target]) wall_max_x[target] = wall_max_x[j];
                if (wall_min_y[j] < wall_min_y[target]) wall_min_y[target] = wall_min_y[j];
                if (wall_max_y[j] > wall_max_y[target]) wall_max_y[target] = wall_max_y[j];
                for (k = j; k < wall_count - 1; k++)
                {
                    wall_min_x[k] = wall_min_x[k + 1];
                    wall_max_x[k] = wall_max_x[k + 1];
                    wall_min_y[k] = wall_min_y[k + 1];
                    wall_max_y[k] = wall_max_y[k + 1];
                }
                wall_count--;
                j--;
            }
        }

        if (target < 0)
        {
            if (wall_count >= 16)
            {
                continue;
            }
            target = wall_count;
            wall_min_x[target] = line_min_x;
            wall_max_x[target] = line_max_x;
            wall_min_y[target] = line_min_y;
            wall_max_y[target] = line_max_y;
            wall_count++;
        }

        if (line_min_x < wall_min_x[target]) wall_min_x[target] = line_min_x;
        if (line_max_x > wall_max_x[target]) wall_max_x[target] = line_max_x;
        if (line_min_y < wall_min_y[target]) wall_min_y[target] = line_min_y;
        if (line_max_y > wall_max_y[target]) wall_max_y[target] = line_max_y;
    }

    for (i = 0; i < wall_count; i++)
    {
        if (wall_max_x[i] <= wall_min_x[i] || wall_max_y[i] <= wall_min_y[i])
        {
            continue;
        }
        x0 = ArenaDuel_AutomapScreenX(wall_min_x[i] << FRACBITS, min_x, scale, padding);
        y0 = ArenaDuel_AutomapScreenY(wall_max_y[i] << FRACBITS, min_y, scale, padding);
        x1 = ArenaDuel_AutomapScreenX(wall_max_x[i] << FRACBITS, min_x, scale, padding);
        y1 = ArenaDuel_AutomapScreenY(wall_min_y[i] << FRACBITS, min_y, scale, padding);
        ArenaDuel_AutomapFillRect(arena_duel_player1_automap_rgba, x0, y0, x1, y1, 123, 139, 132);
    }

    for (i = 0; i < numlines; i++)
    {
        line = &lines[i];
        x0 = ArenaDuel_AutomapScreenX(line->v1->x, min_x, scale, padding);
        y0 = ArenaDuel_AutomapScreenY(line->v1->y, min_y, scale, padding);
        x1 = ArenaDuel_AutomapScreenX(line->v2->x, min_x, scale, padding);
        y1 = ArenaDuel_AutomapScreenY(line->v2->y, min_y, scale, padding);

        if (line->backsector)
        {
            continue;
        }

        line_x0 = line->v1->x >> FRACBITS;
        line_y0 = line->v1->y >> FRACBITS;
        line_x1 = line->v2->x >> FRACBITS;
        line_y1 = line->v2->y >> FRACBITS;
        line_inside_wall_fill = false;
        for (j = 0; j < wall_count; j++)
        {
            if (line_x0 >= wall_min_x[j] && line_x0 <= wall_max_x[j]
                && line_x1 >= wall_min_x[j] && line_x1 <= wall_max_x[j]
                && line_y0 >= wall_min_y[j] && line_y0 <= wall_max_y[j]
                && line_y1 >= wall_min_y[j] && line_y1 <= wall_max_y[j])
            {
                line_inside_wall_fill = true;
                break;
            }
        }
        if (line_inside_wall_fill)
        {
            continue;
        }

        ArenaDuel_AutomapDrawLine(arena_duel_player1_automap_rgba, x0, y0, x1, y1, 210, 224, 216);
    }

    player1_mo = players[consoleplayer].mo;
    if (player1_mo == NULL)
    {
        player1_mo = arena_duel_player1_cached_mo;
    }
    ArenaDuel_AutomapDrawPlayer(arena_duel_player1_automap_rgba, player1_mo, min_x, min_y, scale, padding, 125, 220, 255);
    ArenaDuel_AutomapDrawPlayer(arena_duel_player1_automap_rgba, arena_duel_player2, min_x, min_y, scale, padding, 255, 122, 122);

    arena_duel_player1_automap_nonzero_pixels = ARENA_DUEL_AUTOMAP_WIDTH * ARENA_DUEL_AUTOMAP_HEIGHT;
    arena_duel_player1_automap_frame++;
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

static void ArenaDuel_Player1Spawn(int *x, int *y, angle_t *angle)
{
    switch (ArenaDuel_SpawnVariant())
    {
    case ARENA_DUEL_SPAWN_BLIND:
        *x = -992;
        *y = 736;
        *angle = ANG270 + ANG45;
        break;
    case ARENA_DUEL_SPAWN_CORNER:
        *x = -992;
        *y = 736;
        *angle = ANG270 + ANG45;
        break;
    case ARENA_DUEL_SPAWN_CENTER:
        *x = -320;
        *y = -520;
        *angle = 0;
        break;
    case ARENA_DUEL_SPAWN_OPEN:
    default:
        *x = -992;
        *y = 736;
        *angle = ANG270 + ANG45;
        break;
    }
}

static void ArenaDuel_EnsurePlayer1StartingHealth(void)
{
    player_t *player;
    mobj_t *mobj;
    int x;
    int y;
    angle_t angle;

    if (arena_duel_player1_health_initialized)
    {
        return;
    }

    player = &players[consoleplayer];
    if (player->mo == NULL)
    {
        return;
    }

    mobj = player->mo;
    ArenaDuel_Player1Spawn(&x, &y, &angle);
    P_UnsetThingPosition(mobj);
    mobj->x = x << FRACBITS;
    mobj->y = y << FRACBITS;
    mobj->angle = angle;
    P_SetThingPosition(mobj);
    mobj->momx = 0;
    mobj->momy = 0;
    mobj->z = mobj->floorz;

    player->health = ARENA_DUEL_PARTICIPANT_HEALTH;
    mobj->health = ARENA_DUEL_PARTICIPANT_HEALTH;
    player->armortype = 0;
    player->armorpoints = 0;
    arena_duel_player1_health_initialized = true;
    printf("Doom Agent Arena: spawned duel player_1 at (%d, %d)\n",
           x,
           y);
    ArenaDuel_AddEvent("participant_spawned: player_1");
    ArenaDuel_LogCollisionProfile("player_1", mobj);
}

static void ArenaDuel_EnsurePlayer1CombatState(void)
{
    player_t *player;

    player = &players[consoleplayer];
    if (player->mo == NULL)
    {
        return;
    }

    // Duel playback is on a flat arena floor. Keep the real player grounded
    // and unarmored so arena movement/damage reflect visible combat instead
    // of inheriting incidental single-player spawn state.
    player->armortype = 0;
    player->armorpoints = 0;
    player->mo->z = player->mo->floorz;
    player->mo->momz = 0;
    player->mo->reactiontime = 0;
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

static void ArenaDuel_LogPathPoint(arena_participant_id_t participant)
{
    mobj_t *mobj;
    arena_participant_autopilot_debug_t debug;
    char event[192];
    int x;
    int y;
    int angle;

    if (!arena_duel_started || arena_duel_finished)
    {
        return;
    }

    mobj = participant == ARENA_PARTICIPANT_PLAYER_2
        ? arena_duel_player2
        : ArenaDuel_Player1Mobj();
    if (mobj == NULL)
    {
        return;
    }

    if (arena_duel_path_log_have_position[participant]
        && leveltime - arena_duel_path_log_last_tick[participant] < ARENA_DUEL_PATH_LOG_INTERVAL_TICKS)
    {
        return;
    }

    x = mobj->x >> FRACBITS;
    y = mobj->y >> FRACBITS;
    angle = ArenaDuel_NormalizedAngleDegrees(mobj->angle);
    debug = ArenaParticipantAutopilot_Debug(participant);

    snprintf(event,
             sizeof(event),
             "path_point: %s x=%d y=%d angle=%d dx=%d dy=%d dangle=%d action=%s aim_error=%d",
             ArenaDuel_ParticipantName(participant),
             x,
             y,
             angle,
             arena_duel_path_log_have_position[participant] ? x - arena_duel_path_log_last_x[participant] : 0,
             arena_duel_path_log_have_position[participant] ? y - arena_duel_path_log_last_y[participant] : 0,
             arena_duel_path_log_have_position[participant] ? angle - arena_duel_path_log_last_angle[participant] : 0,
             debug.autopilot_action,
             debug.aim_error);
    ArenaDuel_AddEvent(event);

    arena_duel_path_log_have_position[participant] = true;
    arena_duel_path_log_last_tick[participant] = leveltime;
    arena_duel_path_log_last_x[participant] = x;
    arena_duel_path_log_last_y[participant] = y;
    arena_duel_path_log_last_angle[participant] = angle;
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

static void ArenaDuel_ThrustTowardRouteWaypoint(
    mobj_t *mobj,
    const arena_participant_autopilot_command_t *command)
{
    angle_t angle;

    if (mobj == NULL
        || command == NULL
        || !command->route_waypoint_active)
    {
        return;
    }

    angle = R_PointToAngle2(mobj->x,
                            mobj->y,
                            command->route_target_x * FRACUNIT,
                            command->route_target_y * FRACUNIT);
    ArenaDuel_Thrust(mobj, angle, ARENA_DUEL_MOVE_SPEED);
}

static void ArenaDuel_SeparateParticipantsIfStuck(void)
{
    arena_participant_autopilot_debug_t player1_debug;
    arena_participant_autopilot_debug_t player2_debug;
    mobj_t *player1;
    int distance;
    angle_t angle_to_player2;

    player1 = ArenaDuel_Player1Mobj();
    if (player1 == NULL || arena_duel_player2 == NULL)
    {
        return;
    }
    if (player1->health <= 0 || arena_duel_player2->health <= 0)
    {
        return;
    }

    player1_debug = ArenaParticipantAutopilot_Debug(ARENA_PARTICIPANT_PLAYER_1);
    player2_debug = ArenaParticipantAutopilot_Debug(ARENA_PARTICIPANT_PLAYER_2);
    if (!player1_debug.stuck_recovery && !player2_debug.stuck_recovery)
    {
        return;
    }

    distance = P_AproxDistance(arena_duel_player2->x - player1->x,
                               arena_duel_player2->y - player1->y) >> FRACBITS;
    if (distance > ARENA_DUEL_UNSTICK_DISTANCE)
    {
        return;
    }

    angle_to_player2 = R_PointToAngle2(player1->x,
                                       player1->y,
                                       arena_duel_player2->x,
                                       arena_duel_player2->y);
    ArenaDuel_Thrust(player1, angle_to_player2 + ANG180, ARENA_DUEL_UNSTICK_PUSH_SPEED);
    ArenaDuel_Thrust(arena_duel_player2, angle_to_player2, ARENA_DUEL_UNSTICK_PUSH_SPEED);
}

static void ArenaDuel_EnsurePlayer1AutopilotMomentum(void)
{
    player_t *player;
    arena_participant_autopilot_command_t command;

    player = &players[consoleplayer];
    if (player->mo == NULL)
    {
        return;
    }

    command = Arena_PlayerLastAutopilotCommand();
    if (!command.active || (!command.forward && !command.strafe))
    {
        return;
    }

    // P_PlayerThink should normally convert player_1's ticcmd into XY
    // momentum. On the duel path we have observed runs where turn/fire are
    // applied but movement thrust never materializes, leaving momx/momy at
    // zero and the player pinned at spawn. Inject the same autopilot thrust
    // here only when no XY momentum was produced.
    if (player->mo->momx || player->mo->momy)
    {
        return;
    }

    if (command.forward != 0)
    {
        ArenaDuel_Thrust(player->mo,
                         player->mo->angle,
                         command.forward * ARENA_DUEL_MOVE_SPEED);
    }

    if (command.strafe != 0)
    {
        ArenaDuel_Thrust(player->mo,
                         player->mo->angle - ANG90,
                         command.strafe * ARENA_DUEL_SIDE_SPEED);
    }
}

static void ArenaDuel_RefillPlayer1Ammo(void)
{
    player_t *player;

    player = &players[consoleplayer];
    // Hardcode maxammo + ammo. On builds where players[consoleplayer]'s
    // maxammo array stays at zeros (which has been observed when
    // P_SpawnPlayer runs after the deathmatch init resets the player
    // struct), the previous "ammo[i] = maxammo[i]" copy left every
    // weapon empty and player_1 could never fire.
    player->maxammo[0] = 200;   // am_clip
    player->maxammo[1] = 200;   // am_shell
    player->maxammo[2] = 200;   // am_cell
    player->maxammo[3] = 200;   // am_misl
    player->ammo[0] = 200;
    player->ammo[1] = 200;
    player->ammo[2] = 200;
    player->ammo[3] = 200;

    // The deathmatch init / level reload flow zeros player_t for
    // player_1, including readyweapon and weaponowned[]. After that
    // the player ends up holding wp_fist (readyweapon=0) with nothing
    // owned, so the autopilot swings a fist at thin air even when the
    // opponent is 1500 units away. Re-stamp the basic loadout every
    // tick so the state stays consistent.
    if (player->readyweapon == 0 /* wp_fist */
        || !player->weaponowned[1] /* wp_pistol */)
    {
        player->weaponowned[0] = true;   // wp_fist (always)
        player->weaponowned[1] = true;   // wp_pistol
        player->readyweapon = 1;          // wp_pistol
        player->pendingweapon = 1;        // wp_pistol
    }
}

static int ArenaDuel_Player1AutopilotStuckTicks(void)
{
    mobj_t *mobj;
    fixed_t delta;

    mobj = ArenaDuel_Player1Mobj();
    if (mobj == NULL)
    {
        arena_duel_player1_have_autopilot_position = false;
        arena_duel_player1_autopilot_stuck_ticks = 0;
        return 0;
    }

    if (!arena_duel_player1_have_autopilot_position)
    {
        arena_duel_player1_have_autopilot_position = true;
        arena_duel_player1_last_autopilot_x = mobj->x;
        arena_duel_player1_last_autopilot_y = mobj->y;
        arena_duel_player1_autopilot_stuck_ticks = 0;
        return 0;
    }

    delta = P_AproxDistance(mobj->x - arena_duel_player1_last_autopilot_x,
                            mobj->y - arena_duel_player1_last_autopilot_y);
    arena_duel_player1_last_autopilot_x = mobj->x;
    arena_duel_player1_last_autopilot_y = mobj->y;

    if ((delta >> FRACBITS) == 0)
    {
        arena_duel_player1_autopilot_stuck_ticks++;
    }
    else
    {
        arena_duel_player1_autopilot_stuck_ticks = 0;
    }

    return arena_duel_player1_autopilot_stuck_ticks;
}

static void ArenaDuel_Player1Attack(void)
{
    player_t *player;
    mobj_t *mobj;
    fixed_t slope;
    int damage;
    int i;
    weapontype_t ready_weapon;

    player = &players[consoleplayer];
    mobj = ArenaDuel_Player1Mobj();
    if (mobj == NULL || mobj->health <= 0)
    {
        return;
    }

    if (arena_duel_player1_attack_cooldown > 0)
    {
        return;
    }

    ready_weapon = player->readyweapon;
    if (ready_weapon <= wp_fist || ready_weapon >= NUMWEAPONS)
    {
        ready_weapon = wp_pistol;
    }

    slope = P_AimLineAttack(mobj, mobj->angle, 16 * 64 * FRACUNIT);
    if (slope == 0)
    {
        slope = P_AimLineAttack(mobj, mobj->angle, MISSILERANGE);
    }

    if (ready_weapon == wp_shotgun && player->ammo[am_shell] > 0)
    {
        for (i = 0; i < 5; i++)
        {
            angle_t pellet_angle;

            pellet_angle = mobj->angle + (P_SubRandom() << 18);
            damage = (P_Random() & 1) ? 10 : 6;
            P_LineAttack(mobj, pellet_angle, MISSILERANGE, slope, damage);
        }
        S_StartSound(mobj, sfx_shotgn);
        player->ammo[am_shell] = 200;
        arena_duel_player1_attack_cooldown = ARENA_DUEL_SHOTGUN_COOLDOWN_TICS;
    }
    else
    {
        damage = 5 * (P_Random() % 3 + 1);
        P_LineAttack(mobj, mobj->angle, MISSILERANGE, slope, damage);
        S_StartSound(mobj, sfx_pistol);
        player->ammo[am_clip] = 200;
        arena_duel_player1_attack_cooldown = ARENA_DUEL_ATTACK_COOLDOWN_TICS;
    }

    P_SetMobjState(mobj, S_PLAY_ATK2);
    ArenaDuel_TriggerPlayer1ViewFire(ready_weapon);
    arena_duel_player1_shots_fired++;
    ArenaDuel_AddEvent("participant_fired: player_1");
}

static boolean ArenaDuel_Player1GiveHealth(int amount)
{
    player_t *player;
    mobj_t *mobj;

    player = &players[consoleplayer];
    mobj = ArenaDuel_Player1Mobj();
    if (mobj == NULL || mobj->health >= ARENA_DUEL_PARTICIPANT_HEALTH)
    {
        return false;
    }

    mobj->health += amount;
    if (mobj->health > ARENA_DUEL_PARTICIPANT_HEALTH)
    {
        mobj->health = ARENA_DUEL_PARTICIPANT_HEALTH;
    }
    player->health = mobj->health;
    return true;
}

static boolean ArenaDuel_Player1ApplyPickup(mobj_t *special)
{
    player_t *player;
    mobj_t *mobj;
    char event[128];

    player = &players[consoleplayer];
    mobj = ArenaDuel_Player1Mobj();
    if (special == NULL || mobj == NULL)
    {
        return false;
    }

    switch (special->type)
    {
    case MT_SHOTGUN:
        if (!Arena_WeaponPickupsEnabled())
        {
            P_RemoveMobj(special);
            return false;
        }
        player->weaponowned[wp_shotgun] = true;
        player->readyweapon = wp_shotgun;
        player->pendingweapon = wp_shotgun;
        player->maxammo[am_shell] = 200;
        player->ammo[am_shell] = 200;
        S_StartSound(mobj, sfx_wpnup);
        snprintf(event,
                 sizeof(event),
                 "pickup: player_1 shotgun x=%d y=%d",
                 special->x >> FRACBITS,
                 special->y >> FRACBITS);
        ArenaDuel_AddEvent(event);
        P_RemoveMobj(special);
        return true;

    case MT_MISC10:
        if (!ArenaDuel_Player1GiveHealth(10))
        {
            return false;
        }
        S_StartSound(mobj, sfx_itemup);
        ArenaDuel_AddEvent("pickup: player_1 stimpack");
        P_RemoveMobj(special);
        return true;

    case MT_MISC11:
        if (!ArenaDuel_Player1GiveHealth(100))
        {
            return false;
        }
        S_StartSound(mobj, sfx_itemup);
        ArenaDuel_AddEvent("pickup: player_1 medikit");
        P_RemoveMobj(special);
        return true;

    default:
        return false;
    }
}

static void ArenaDuel_CheckPlayer1Pickups(void)
{
    thinker_t *thinker;
    thinker_t *next;
    mobj_t *player1;

    player1 = ArenaDuel_Player1Mobj();
    if (player1 == NULL || player1->health <= 0)
    {
        return;
    }

    for (thinker = thinkercap.next; thinker != &thinkercap; thinker = next)
    {
        mobj_t *special;
        fixed_t pickup_distance;
        fixed_t touch_distance;

        next = thinker->next;
        if (thinker->function.acp1 != (actionf_p1) P_MobjThinker)
        {
            continue;
        }

        special = (mobj_t *) thinker;
        if (!(special->flags & MF_SPECIAL))
        {
            continue;
        }

        pickup_distance = P_AproxDistance(special->x - player1->x,
                                          special->y - player1->y);
        touch_distance = special->radius + player1->radius;
        if (pickup_distance >= touch_distance)
        {
            continue;
        }

        if (special->z - player1->z > player1->height
            || special->z - player1->z < -8 * FRACUNIT)
        {
            continue;
        }

        ArenaDuel_Player1ApplyPickup(special);
    }
}

static void ArenaDuel_Player2Attack(void)
{
    fixed_t slope;
    int damage;
    int i;

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

    if (arena_duel_player2_ready_weapon == wp_shotgun
        && arena_duel_player2_ammo_shells > 0)
    {
        for (i = 0; i < 5; i++)
        {
            angle_t pellet_angle;

            pellet_angle = arena_duel_player2->angle + (P_SubRandom() << 18);
            damage = (P_Random() & 1) ? 10 : 6;
            P_LineAttack(arena_duel_player2,
                         pellet_angle,
                         MISSILERANGE,
                         slope,
                         damage);
        }
        S_StartSound(arena_duel_player2, sfx_shotgn);
        arena_duel_player2_ammo_shells = 200;
        arena_duel_player2_attack_cooldown = ARENA_DUEL_SHOTGUN_COOLDOWN_TICS;
    }
    else
    {
        damage = 5 * (P_Random() % 3 + 1);
        P_LineAttack(arena_duel_player2,
                     arena_duel_player2->angle,
                     MISSILERANGE,
                     slope,
                     damage);
        S_StartSound(arena_duel_player2, sfx_pistol);
        arena_duel_player2_ammo_bullets = ARENA_DUEL_PLAYER2_BULLETS;
        arena_duel_player2_attack_cooldown = ARENA_DUEL_ATTACK_COOLDOWN_TICS;
    }
    ArenaDuel_TriggerPlayer2ViewFire();

    arena_duel_player2_shots_fired++;
    ArenaDuel_AddEvent("participant_fired: player_2");
}

static boolean ArenaDuel_Player2GiveHealth(int amount)
{
    if (arena_duel_player2 == NULL || arena_duel_player2->health >= ARENA_DUEL_PARTICIPANT_HEALTH)
    {
        return false;
    }

    arena_duel_player2->health += amount;
    if (arena_duel_player2->health > ARENA_DUEL_PARTICIPANT_HEALTH)
    {
        arena_duel_player2->health = ARENA_DUEL_PARTICIPANT_HEALTH;
    }
    return true;
}

static boolean ArenaDuel_Player2ApplyPickup(mobj_t *special)
{
    char event[128];

    if (special == NULL || arena_duel_player2 == NULL)
    {
        return false;
    }

    switch (special->type)
    {
    case MT_SHOTGUN:
        if (!Arena_WeaponPickupsEnabled())
        {
            P_RemoveMobj(special);
            return false;
        }
        arena_duel_player2_ready_weapon = wp_shotgun;
        arena_duel_player2_ammo_shells = 200;
        ArenaDuel_SetPlayer2ViewReadyWeapon(wp_shotgun);
        S_StartSound(arena_duel_player2, sfx_wpnup);
        snprintf(event,
                 sizeof(event),
                 "pickup: player_2 shotgun x=%d y=%d",
                 special->x >> FRACBITS,
                 special->y >> FRACBITS);
        ArenaDuel_AddEvent(event);
        P_RemoveMobj(special);
        return true;

    case MT_MISC10:
        if (!ArenaDuel_Player2GiveHealth(10))
        {
            return false;
        }
        S_StartSound(arena_duel_player2, sfx_itemup);
        ArenaDuel_AddEvent("pickup: player_2 stimpack");
        P_RemoveMobj(special);
        return true;

    case MT_MISC11:
        if (!ArenaDuel_Player2GiveHealth(100))
        {
            return false;
        }
        S_StartSound(arena_duel_player2, sfx_itemup);
        ArenaDuel_AddEvent("pickup: player_2 medikit");
        P_RemoveMobj(special);
        return true;

    default:
        return false;
    }
}

static void ArenaDuel_CheckPlayer2Pickups(void)
{
    thinker_t *thinker;
    thinker_t *next;

    if (arena_duel_player2 == NULL || arena_duel_player2->health <= 0)
    {
        return;
    }

    for (thinker = thinkercap.next; thinker != &thinkercap; thinker = next)
    {
        mobj_t *special;
        fixed_t pickup_distance;
        fixed_t touch_distance;

        next = thinker->next;
        if (thinker->function.acp1 != (actionf_p1) P_MobjThinker)
        {
            continue;
        }

        special = (mobj_t *) thinker;
        if (!(special->flags & MF_SPECIAL))
        {
            continue;
        }

        pickup_distance = P_AproxDistance(special->x - arena_duel_player2->x,
                                          special->y - arena_duel_player2->y);
        touch_distance = special->radius + arena_duel_player2->radius;
        if (pickup_distance >= touch_distance)
        {
            continue;
        }

        if (special->z - arena_duel_player2->z > arena_duel_player2->height
            || special->z - arena_duel_player2->z < -8 * FRACUNIT)
        {
            continue;
        }

        ArenaDuel_Player2ApplyPickup(special);
    }
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

static arena_participant_command_t ArenaDuel_Player1Command(void)
{
    arena_participant_command_t command;
    arena_participant_autopilot_input_t input;
    arena_participant_autopilot_command_t autopilot;
    player_t *player;
    mobj_t *player1;
    angle_t angle_to_player2;

    command = ArenaParticipantCommands_Command(ARENA_PARTICIPANT_PLAYER_1);
    if (!ArenaParticipantIntent_HasActive(ARENA_PARTICIPANT_PLAYER_1))
    {
        memset(&arena_duel_player1_last_autopilot_command, 0, sizeof(arena_duel_player1_last_autopilot_command));
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                 "no_active_intent");
        return command;
    }

    player = &players[consoleplayer];
    player1 = ArenaDuel_Player1Mobj();
    if (player1 == NULL || arena_duel_player2 == NULL)
    {
        memset(&arena_duel_player1_last_autopilot_command, 0, sizeof(arena_duel_player1_last_autopilot_command));
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                 "missing_participant_state");
        return command;
    }

    memset(&input, 0, sizeof(input));
    input.participant = ARENA_PARTICIPANT_PLAYER_1;
    input.intent = ArenaParticipantIntent_Get(ARENA_PARTICIPANT_PLAYER_1);
    input.self_x = player1->x >> FRACBITS;
    input.self_y = player1->y >> FRACBITS;
    input.self_angle = ArenaDuel_AngleDegrees(player1->angle);
    input.opponent_x = arena_duel_player2->x >> FRACBITS;
    input.opponent_y = arena_duel_player2->y >> FRACBITS;
    input.opponent_health = arena_duel_player2->health;
    input.self_ammo = player->ammo[am_clip];
    if (player->readyweapon == wp_shotgun)
    {
        input.self_ammo = player->ammo[am_shell];
    }
    input.self_health = player1->health;
    input.distance = P_AproxDistance(player1->x - arena_duel_player2->x,
                                     player1->y - arena_duel_player2->y) >> FRACBITS;
    angle_to_player2 = R_PointToAngle2(player1->x,
                                       player1->y,
                                       arena_duel_player2->x,
                                       arena_duel_player2->y);
    input.relative_angle =
        -ArenaDuel_NormalizedAngleDegrees(angle_to_player2 - player1->angle);
    input.line_of_sight = P_CheckSight(player1, arena_duel_player2) ? 1 : 0;
    input.stuck_ticks = ArenaDuel_Player1AutopilotStuckTicks();
    input.tick = leveltime;
    input.phase_finished = arena_duel_finished ? 1 : 0;

    autopilot = ArenaParticipantAutopilot_Decide(&input);
    if (!autopilot.active)
    {
        memset(&arena_duel_player1_last_autopilot_command, 0, sizeof(arena_duel_player1_last_autopilot_command));
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                 autopilot.reason);
        return command;
    }

    arena_duel_player1_last_autopilot_command = autopilot;
    ArenaParticipantAutopilot_RecordDecision(ARENA_PARTICIPANT_PLAYER_1,
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
    ArenaDuel_CopyField(command.command_id, sizeof(command.command_id), "player_1_autopilot");
    ArenaDuel_CopyField(command.status, sizeof(command.status), "autopilot");
    ArenaDuel_CopyField(command.last_action, sizeof(command.last_action), autopilot.action);
    return command;
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
        memset(&arena_duel_player2_last_autopilot_command, 0, sizeof(arena_duel_player2_last_autopilot_command));
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_2,
                                                 "no_active_intent");
        return command;
    }

    player = &players[consoleplayer];
    if (player->mo == NULL || arena_duel_player2 == NULL)
    {
        memset(&arena_duel_player2_last_autopilot_command, 0, sizeof(arena_duel_player2_last_autopilot_command));
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
        memset(&arena_duel_player2_last_autopilot_command, 0, sizeof(arena_duel_player2_last_autopilot_command));
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_2,
                                                 autopilot.reason);
        return command;
    }

    arena_duel_player2_last_autopilot_command = autopilot;
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

static void ArenaDuel_TickPlayer1CustomAutopilot(void)
{
    arena_participant_command_t command;
    mobj_t *player1;

    player1 = ArenaDuel_Player1Mobj();
    if (player1 == NULL)
    {
        memset(&arena_duel_player1_last_autopilot_command, 0, sizeof(arena_duel_player1_last_autopilot_command));
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                 "missing_participant_state");
        return;
    }

    if (player1->health <= 0)
    {
        player1->momx = 0;
        player1->momy = 0;
        memset(&arena_duel_player1_last_autopilot_command, 0, sizeof(arena_duel_player1_last_autopilot_command));
        return;
    }

    command = ArenaDuel_Player1Command();
    ArenaDuel_LogAutopilotEvent(ARENA_PARTICIPANT_PLAYER_1);

    player1->angle += (angle_t) (-command.turn * ARENA_DUEL_TURN_SPEED) << FRACBITS;

    if (arena_duel_player1_last_autopilot_command.route_waypoint_active)
    {
        ArenaDuel_ThrustTowardRouteWaypoint(player1, &arena_duel_player1_last_autopilot_command);
    }
    else if (command.forward != 0)
    {
        ArenaDuel_Thrust(player1,
                         player1->angle,
                         command.forward * ARENA_DUEL_MOVE_SPEED);
    }

    if (!arena_duel_player1_last_autopilot_command.route_waypoint_active && command.strafe != 0)
    {
        ArenaDuel_Thrust(player1,
                         player1->angle - ANG90,
                         command.strafe * ARENA_DUEL_SIDE_SPEED);
    }

    if (command.attack)
    {
        ArenaDuel_Player1Attack();
    }
    ArenaDuel_CheckPlayer1Pickups();
    ArenaDuel_LogPathPoint(ARENA_PARTICIPANT_PLAYER_1);
}

static void ArenaDuel_TickPlayer2CustomAutopilot(void)
{
    arena_participant_command_t command;

    if (arena_duel_player2 == NULL)
    {
        memset(&arena_duel_player2_last_autopilot_command, 0, sizeof(arena_duel_player2_last_autopilot_command));
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_2,
                                                 "missing_participant_state");
        return;
    }

    if (arena_duel_player2->health <= 0)
    {
        arena_duel_player2->momx = 0;
        arena_duel_player2->momy = 0;
        memset(&arena_duel_player2_last_autopilot_command, 0, sizeof(arena_duel_player2_last_autopilot_command));
        return;
    }

    command = ArenaDuel_Player2Command();
    ArenaDuel_LogAutopilotEvent(ARENA_PARTICIPANT_PLAYER_2);

    arena_duel_player2->angle += (angle_t) (-command.turn * ARENA_DUEL_TURN_SPEED) << FRACBITS;

    if (arena_duel_player2_last_autopilot_command.route_waypoint_active)
    {
        ArenaDuel_ThrustTowardRouteWaypoint(arena_duel_player2, &arena_duel_player2_last_autopilot_command);
    }
    else if (command.forward != 0)
    {
        ArenaDuel_Thrust(arena_duel_player2,
                         arena_duel_player2->angle,
                         command.forward * ARENA_DUEL_MOVE_SPEED);
    }

    if (!arena_duel_player2_last_autopilot_command.route_waypoint_active && command.strafe != 0)
    {
        ArenaDuel_Thrust(arena_duel_player2,
                         arena_duel_player2->angle - ANG90,
                         command.strafe * ARENA_DUEL_SIDE_SPEED);
    }

    if (command.attack)
    {
        ArenaDuel_Player2Attack();
    }
    ArenaDuel_CheckPlayer2Pickups();
    ArenaDuel_LogPathPoint(ARENA_PARTICIPANT_PLAYER_2);
}

boolean ArenaDuel_IsEnabled(void)
{
    // gameepisode is reset to 0 after deathmatch init even though we
    // booted with -warp 1 8, so checking it would permanently disable
    // the duel ticker. We only spawn the duel on E1M8, so gamemap == 8
    // is sufficient confirmation that we're in the right level.
    return Arena_DuelModeEnabled() && gamemap == 8;
}

void ArenaDuel_CachePlayer1Mobj(mobj_t *mobj)
{
    arena_duel_player1_cached_mo = mobj;
    if (mobj != NULL)
    {
        mobj->flags &= ~(MF_PICKUP | MF_NOTDMATCH);
    }
    ArenaDuel_LogCollisionProfile("player_1", mobj);
}

void ArenaDuel_RecordPlayer1WeaponFired(void)
{
    if (!ArenaDuel_IsEnabled() || !arena_duel_started || arena_duel_finished)
    {
        return;
    }

    arena_duel_player1_shots_fired++;
    ArenaDuel_AddEvent("participant_fired: player_1");
}

void ArenaDuel_RestorePlayer1Mobj(void)
{
    // Called from P_Ticker BEFORE P_PlayerThink so that the autopilot
    // path (Arena_PlayerApplyAutopilotCommand) sees a valid
    // players[consoleplayer].mo. Doing this only inside ArenaDuel_Ticker
    // happens too late â€” by then the autopilot has already dropped the
    // intent with reason "missing_participant_state".
    if (arena_duel_player1_cached_mo == NULL)
    {
        return;
    }
    if (players[consoleplayer].mo == NULL)
    {
        players[consoleplayer].mo = arena_duel_player1_cached_mo;
        arena_duel_player1_cached_mo->player = &players[consoleplayer];
    }
}

void ArenaDuel_InitLevel(void)
{
    arena_duel_player2 = NULL;
    arena_duel_player1_cached_mo = NULL;
    arena_duel_player2_ammo_bullets = ARENA_DUEL_PLAYER2_BULLETS;
    arena_duel_player2_ammo_shells = 0;
    arena_duel_player2_ready_weapon = wp_pistol;
    arena_duel_player1_attack_cooldown = 0;
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
    arena_duel_player1_reveal_until_tick = 0;
    arena_duel_player2_reveal_until_tick = 0;
    arena_duel_event_count = 0;
    arena_duel_player2_view_frame = 0;
    arena_duel_player2_view_nonzero_pixels = 0;
    arena_duel_player2_view_player_initialized = false;
    arena_duel_player2_view_player_last_tick = -1;
    arena_duel_player2_have_autopilot_position = false;
    arena_duel_player1_have_autopilot_position = false;
    arena_duel_player1_autopilot_stuck_ticks = 0;
    arena_duel_player2_autopilot_stuck_ticks = 0;
    memset(&arena_duel_player1_last_autopilot_command, 0, sizeof(arena_duel_player1_last_autopilot_command));
    memset(&arena_duel_player2_last_autopilot_command, 0, sizeof(arena_duel_player2_last_autopilot_command));
    arena_duel_player1_health_initialized = false;
    arena_duel_waiting_event_logged = false;
    arena_duel_waiting_first_intents_event_logged = false;
    memset(arena_duel_last_intent_id, 0, sizeof(arena_duel_last_intent_id));
    memset(arena_duel_intent_was_active, 0, sizeof(arena_duel_intent_was_active));
    memset(arena_duel_last_autopilot_key, 0, sizeof(arena_duel_last_autopilot_key));
    memset(arena_duel_stuck_recovery_was_active,
           0,
           sizeof(arena_duel_stuck_recovery_was_active));
    memset(arena_duel_path_log_have_position, 0, sizeof(arena_duel_path_log_have_position));
    memset(arena_duel_path_log_last_tick, 0, sizeof(arena_duel_path_log_last_tick));
    memset(arena_duel_path_log_last_x, 0, sizeof(arena_duel_path_log_last_x));
    memset(arena_duel_path_log_last_y, 0, sizeof(arena_duel_path_log_last_y));
    memset(arena_duel_path_log_last_angle, 0, sizeof(arena_duel_path_log_last_angle));
    ArenaParticipantCommands_Init();
    ArenaParticipantIntent_Init();
    ArenaParticipantAutopilot_ResetDebug();
}

void ArenaDuel_SpawnPlayer2(void)
{
    int x;
    int y;
    angle_t angle;
    mobj_t *mobj;

    if (!ArenaDuel_IsEnabled())
    {
        return;
    }

    ArenaDuel_EnsurePlayer1Label();
    ArenaDuel_EnsurePlayer1StartingHealth();

    switch (ArenaDuel_SpawnVariant())
    {
    case ARENA_DUEL_SPAWN_BLIND:
        x = 992;
        y = -736;
        angle = ANG90 + ANG45;
        break;
    case ARENA_DUEL_SPAWN_CORNER:
        x = 992;
        y = -736;
        angle = ANG90 + ANG45;
        break;
    case ARENA_DUEL_SPAWN_CENTER:
        x = 320;
        y = -520;
        angle = ANG180;
        break;
    case ARENA_DUEL_SPAWN_OPEN:
    default:
        x = 992;
        y = -736;
        angle = ANG90 + ANG45;
        break;
    }

    mobj = P_SpawnMobj(x << FRACBITS, y << FRACBITS, ONFLOORZ, MT_PLAYER);
    mobj->angle = angle;
    mobj->health = ARENA_DUEL_PARTICIPANT_HEALTH;
    mobj->radius = mobjinfo[MT_PLAYER].radius;
    mobj->height = mobjinfo[MT_PLAYER].height;
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
    ArenaDuel_LogCollisionProfile("player_2", mobj);
}

static void ArenaDuel_RemoveDisabledWeaponPickups(void)
{
    thinker_t *thinker;
    thinker_t *next;

    if (Arena_WeaponPickupsEnabled()) {
        return;
    }

    for (thinker = thinkercap.next; thinker != &thinkercap; thinker = next) {
        mobj_t *special;
        next = thinker->next;
        if (thinker->function.acp1 != (actionf_p1) P_MobjThinker) {
            continue;
        }
        special = (mobj_t *) thinker;
        if (special->type == MT_SHOTGUN) {
            P_RemoveMobj(special);
        }
    }
}

void ArenaDuel_Ticker(void)
{
    int player1_health;
    int player2_health;
    int delta;

    // Doom's deathmatch level-setup flow nulls players[consoleplayer].mo after
    // P_SpawnPlayer. Re-link it from our cache here so the entire downstream
    // duel pipeline (state writer, autopilot, damage, POV renderer) sees a
    // valid mobj instead of needing a fallback at every call site.
    if (players[consoleplayer].mo == NULL && arena_duel_player1_cached_mo != NULL)
    {
        players[consoleplayer].mo = arena_duel_player1_cached_mo;
        arena_duel_player1_cached_mo->player = &players[consoleplayer];
    }

    if (!ArenaDuel_IsEnabled() || arena_duel_player2 == NULL)
    {
        return;
    }

    ArenaDuel_EnsurePlayer1Label();
    ArenaDuel_EnsurePlayer1StartingHealth();
    ArenaDuel_EnsurePlayer1CombatState();
    ArenaDuel_RefillPlayer1Ammo();
    arena_duel_player2_ammo_bullets = ARENA_DUEL_PLAYER2_BULLETS;
    if (arena_duel_player2_ready_weapon == wp_shotgun)
    {
        arena_duel_player2_ammo_shells = 200;
    }

    Arena_LoadRunMetadata();
    ArenaDuel_RemoveDisabledWeaponPickups();
    ArenaParticipantCommands_Load();
    ArenaParticipantIntent_TickOrRefresh();
    ArenaDuel_LogIntentEvents();
    ArenaDuel_UpdateStartBarrier();

    if (!arena_duel_started)
    {
        const char *wait_reason;
        mobj_t *player1_mobj;

        wait_reason = ArenaDuel_StartWaitReason();
        player1_mobj = ArenaDuel_Player1Mobj();
        if (player1_mobj != NULL)
        {
            player1_mobj->momx = 0;
            player1_mobj->momy = 0;
        }
        arena_duel_player2->momx = 0;
        arena_duel_player2->momy = 0;
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_1,
                                                 wait_reason);
        ArenaParticipantAutopilot_RecordFallback(ARENA_PARTICIPANT_PLAYER_2,
                                                 wait_reason);
        return;
    }

    player1_health = ArenaDuel_Player1Health();
    player2_health = arena_duel_player2->health;

    if (player1_health < arena_duel_last_player1_health)
    {
        delta = arena_duel_last_player1_health - player1_health;
        arena_duel_player2_damage_dealt += delta;
        arena_duel_player2_shots_hit++;
        arena_duel_player1_reveal_until_tick = leveltime + ARENA_DUEL_HIT_REVEAL_TICKS;
        ArenaDuel_AddEvent("participant_hit: player_2 hit player_1");
    }
    if (player2_health < arena_duel_last_player2_health)
    {
        delta = arena_duel_last_player2_health - player2_health;
        arena_duel_player1_damage_dealt += delta;
        arena_duel_player1_shots_hit++;
        arena_duel_player2_reveal_until_tick = leveltime + ARENA_DUEL_HIT_REVEAL_TICKS;
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
        mobj_t *player1_mobj;

        player1_mobj = ArenaDuel_Player1Mobj();
        if (player1_mobj != NULL)
        {
            player1_mobj->momx = 0;
            player1_mobj->momy = 0;
        }
        arena_duel_player2->momx = 0;
        arena_duel_player2->momy = 0;
        return;
    }

    if (arena_duel_player1_attack_cooldown > 0)
    {
        arena_duel_player1_attack_cooldown--;
    }
    if (arena_duel_player2_attack_cooldown > 0)
    {
        arena_duel_player2_attack_cooldown--;
    }

    ArenaDuel_SeparateParticipantsIfStuck();
    if ((leveltime & 1) == 0)
    {
        ArenaDuel_TickPlayer1CustomAutopilot();
        ArenaDuel_TickPlayer2CustomAutopilot();
    }
    else
    {
        ArenaDuel_TickPlayer2CustomAutopilot();
        ArenaDuel_TickPlayer1CustomAutopilot();
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

int ArenaDuel_Player2AmmoShells(void)
{
    return arena_duel_player2_ammo_shells;
}

int ArenaDuel_Player2ReadyWeapon(void)
{
    return (int) arena_duel_player2_ready_weapon;
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
    R_RenderMobjView(arena_duel_player2, ArenaDuel_Player2ViewPlayer());

    nonzero_pixels = 0;
    for (i = 0; i < ARENA_DUEL_AUTOMAP_WIDTH * ARENA_DUEL_AUTOMAP_HEIGHT; i++)
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
    if (player1_mo == NULL)
    {
        player1_mo = arena_duel_player1_cached_mo;
    }
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
    for (i = 0; i < ARENA_DUEL_AUTOMAP_WIDTH * ARENA_DUEL_AUTOMAP_HEIGHT; i++)
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
    ArenaDuel_RenderPlayer1Automap();

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

ARENA_DUEL_EXPORT int ArenaDuel_Player1AutomapWidth(void)
{
    return ARENA_DUEL_AUTOMAP_WIDTH;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player1AutomapHeight(void)
{
    return ARENA_DUEL_AUTOMAP_HEIGHT;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player1AutomapFrame(void)
{
    return arena_duel_player1_automap_frame;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player1AutomapNonzeroPixels(void)
{
    return arena_duel_player1_automap_nonzero_pixels;
}

ARENA_DUEL_EXPORT uintptr_t ArenaDuel_Player1AutomapPaletted(void)
{
    return 0;
}

ARENA_DUEL_EXPORT uintptr_t ArenaDuel_Player1AutomapRGBA(void)
{
    return (uintptr_t) arena_duel_player1_automap_rgba;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player1PositionValid(void)
{
    return ArenaDuel_Player1Mobj() != NULL;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player1WorldX(void)
{
    mobj_t *mobj;

    mobj = ArenaDuel_Player1Mobj();
    return mobj != NULL ? mobj->x >> FRACBITS : 0;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player1WorldY(void)
{
    mobj_t *mobj;

    mobj = ArenaDuel_Player1Mobj();
    return mobj != NULL ? mobj->y >> FRACBITS : 0;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player2PositionValid(void)
{
    return arena_duel_player2 != NULL;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player2WorldX(void)
{
    return arena_duel_player2 != NULL ? arena_duel_player2->x >> FRACBITS : 0;
}

ARENA_DUEL_EXPORT int ArenaDuel_Player2WorldY(void)
{
    return arena_duel_player2 != NULL ? arena_duel_player2->y >> FRACBITS : 0;
}

ARENA_DUEL_EXPORT uintptr_t ArenaDuel_PalettePointer(void)
{
    return I_GetPaletteData();
}





