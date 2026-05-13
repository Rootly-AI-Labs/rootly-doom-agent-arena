//
// Doom Agent Arena enemy spawning.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "doomdef.h"
#include "doomstat.h"
#include "p_local.h"
#include "agentic_control.h"
#include "arena_enemies.h"

#define ARENA_RUN_METADATA_PATH "arena_run_metadata.local.tsv"

typedef struct
{
    int x;
    int y;
    int angle;
} arena_spawn_slot_t;

static const arena_spawn_slot_t arena_spawn_slots[] =
{
    { 424, 4041, 267 },
    { 1323, 3312, 199 },
    { -553, 3347, 336 },
    { 1022, 2178, 130 },
    { -206, 2142, 46 },
    { 411, 2743, 266 },
    { 528, 2884, 272 },
};

static arena_enemy_t arena_enemies[ARENA_MAX_ENEMIES];
static int arena_enemy_count;
static char arena_run_id[64] = "run_unknown";
static char arena_scenario_id[64] = "scenario_unknown";
static char arena_mode[16] = "enemies";
static char arena_player_1_model[32] = "";
static char arena_player_2_model[32] = "";
static int arena_round = 1;
static int arena_seed = 0;
static int arena_timeout_seconds = 120;

static void Arena_CopyField(char *dest, size_t dest_size, const char *value)
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

boolean Arena_ModeEnabled(void)
{
    return true;
}

boolean Arena_EnemiesModeEnabled(void)
{
    return strcmp(arena_mode, "duel") != 0;
}

boolean Arena_DuelModeEnabled(void)
{
    return !strcmp(arena_mode, "duel");
}

const char *Arena_RunId(void)
{
    return arena_run_id;
}

const char *Arena_ScenarioId(void)
{
    return arena_scenario_id;
}

const char *Arena_Mode(void)
{
    return arena_mode;
}

const char *Arena_Player1Model(void)
{
    return arena_player_1_model;
}

const char *Arena_Player2Model(void)
{
    return arena_player_2_model;
}

int Arena_Round(void)
{
    return arena_round;
}

int Arena_Seed(void)
{
    return arena_seed;
}

int Arena_TimeoutSeconds(void)
{
    return arena_timeout_seconds > 0 ? arena_timeout_seconds : 120;
}

int Arena_EnemyCount(void)
{
    return arena_enemy_count;
}

const char *Arena_EnemyId(int arena_entity_index)
{
    if (arena_entity_index < 0 || arena_entity_index >= arena_enemy_count)
    {
        return "";
    }

    return arena_enemies[arena_entity_index].enemy_id;
}

const char *Arena_EnemyType(int arena_entity_index)
{
    if (arena_entity_index < 0 || arena_entity_index >= arena_enemy_count)
    {
        return "";
    }

    return arena_enemies[arena_entity_index].enemy_type;
}

static void Arena_Chomp(char *line)
{
    size_t len;

    len = strlen(line);

    while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r'))
    {
        line[len - 1] = '\0';
        len--;
    }
}

static int Arena_SplitTsv(char *line, char **fields, int max_fields)
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

static mobjtype_t Arena_EnemyTypeToMobjType(const char *enemy_type)
{
    if (!strcmp(enemy_type, "imp"))
    {
        return MT_TROOP;
    }
    else if (!strcmp(enemy_type, "shotgunner"))
    {
        return MT_SHOTGUY;
    }
    else if (!strcmp(enemy_type, "former_human"))
    {
        return MT_POSSESSED;
    }
    else if (!strcmp(enemy_type, "demon"))
    {
        return MT_SERGEANT;
    }
    else if (!strcmp(enemy_type, "baron"))
    {
        return MT_BRUISER;
    }

    return MT_TROOP;
}

static int Arena_SpawnSlotCount(void)
{
    return sizeof(arena_spawn_slots) / sizeof(arena_spawn_slots[0]);
}

boolean Arena_GetSpawnSlot(int spawn_slot, int *x, int *y, int *angle)
{
    const arena_spawn_slot_t *slot;

    if (spawn_slot < 0 || spawn_slot >= Arena_SpawnSlotCount())
    {
        return false;
    }

    slot = &arena_spawn_slots[spawn_slot];
    if (x != NULL)
    {
        *x = slot->x;
    }
    if (y != NULL)
    {
        *y = slot->y;
    }
    if (angle != NULL)
    {
        *angle = slot->angle;
    }

    return true;
}

static void Arena_AssignSpawnSlot(arena_enemy_t *enemy)
{
    const arena_spawn_slot_t *slot;

    slot = &arena_spawn_slots[enemy->spawn_slot];
    enemy->x = slot->x;
    enemy->y = slot->y;
    enemy->angle = slot->angle;
}

void Arena_LoadRunMetadata(void)
{
    FILE *file;
    char line[256];
    char *fields[9];
    int field_count;

    Arena_CopyField(arena_run_id, sizeof(arena_run_id), "run_unknown");
    Arena_CopyField(arena_scenario_id, sizeof(arena_scenario_id), "scenario_unknown");
    Arena_CopyField(arena_mode, sizeof(arena_mode), "enemies");
    Arena_CopyField(arena_player_1_model, sizeof(arena_player_1_model), "");
    Arena_CopyField(arena_player_2_model, sizeof(arena_player_2_model), "");
    arena_round = 1;
    arena_seed = 0;
    arena_timeout_seconds = 120;

    file = fopen(ARENA_RUN_METADATA_PATH, "r");
    if (file == NULL)
    {
        file = fopen("/" ARENA_RUN_METADATA_PATH, "r");
    }

    if (file == NULL)
    {
        return;
    }

    if (fgets(line, sizeof(line), file) == NULL
        || fgets(line, sizeof(line), file) == NULL)
    {
        fclose(file);
        return;
    }

    Arena_Chomp(line);
    field_count = Arena_SplitTsv(line, fields, 9);
    if (field_count >= 2)
    {
        Arena_CopyField(arena_run_id, sizeof(arena_run_id), fields[0]);
        Arena_CopyField(arena_scenario_id, sizeof(arena_scenario_id), fields[1]);
    }
    if (field_count >= 3 && fields[2][0] != '\0')
    {
        Arena_CopyField(arena_mode, sizeof(arena_mode), fields[2]);
    }
    if (field_count >= 6)
    {
        Arena_CopyField(arena_player_1_model, sizeof(arena_player_1_model), fields[4]);
        Arena_CopyField(arena_player_2_model, sizeof(arena_player_2_model), fields[5]);
    }
    if (field_count >= 9)
    {
        arena_round = atoi(fields[6]);
        arena_seed = atoi(fields[7]);
        arena_timeout_seconds = atoi(fields[8]);
    }
    if (arena_round <= 0)
    {
        arena_round = 1;
    }
    if (arena_timeout_seconds <= 0)
    {
        arena_timeout_seconds = 120;
    }

    if (strcmp(arena_mode, "duel") && strcmp(arena_mode, "enemies"))
    {
        Arena_CopyField(arena_mode, sizeof(arena_mode), "enemies");
    }

    fclose(file);
}

void Arena_LoadEnemies(void)
{
    FILE *file;
    char line[512];
    char *fields[6];
    int line_number;
    int field_count;
    int spawn_slot_count;
    arena_enemy_t *enemy;

    arena_enemy_count = 0;
    if (!Arena_EnemiesModeEnabled())
    {
        printf("Doom Agent Arena: skipping arena enemy TSV in %s mode\n",
               Arena_Mode());
        return;
    }

    spawn_slot_count = Arena_SpawnSlotCount();

    file = fopen("arena_enemies.local.tsv", "r");
    if (file == NULL)
    {
        file = fopen("/arena_enemies.local.tsv", "r");
    }

    if (file == NULL)
    {
        file = fopen("arena_enemies.mock.tsv", "r");
    }

    if (file == NULL)
    {
        file = fopen("/arena_enemies.mock.tsv", "r");
    }

    if (file == NULL)
    {
        printf("Doom Agent Arena: could not open arena enemy TSV\n");
        return;
    }

    line_number = 0;

    while (fgets(line, sizeof(line), file) != NULL)
    {
        line_number++;
        Arena_Chomp(line);

        if (line[0] == '\0')
        {
            continue;
        }

        if (line_number == 1 && !strncmp(line, "enemy_id", 8))
        {
            continue;
        }

        if (arena_enemy_count >= ARENA_MAX_ENEMIES)
        {
            printf("Doom Agent Arena: reached max enemy cap %d\n",
                   ARENA_MAX_ENEMIES);
            break;
        }

        if (arena_enemy_count >= spawn_slot_count)
        {
            printf("Doom Agent Arena: ignoring extra enemy on line %d; no spawn slot available\n",
                   line_number);
            continue;
        }

        field_count = Arena_SplitTsv(line, fields, 6);
        if (field_count < 3)
        {
            printf("Doom Agent Arena: skipping malformed TSV line %d\n",
                   line_number);
            continue;
        }

        enemy = &arena_enemies[arena_enemy_count];
        memset(enemy, 0, sizeof(*enemy));

        strncpy(enemy->enemy_id, fields[0], sizeof(enemy->enemy_id) - 1);
        strncpy(enemy->enemy_type, fields[1], sizeof(enemy->enemy_type) - 1);
        strncpy(enemy->label, fields[2], sizeof(enemy->label) - 1);
        enemy->type = Arena_EnemyTypeToMobjType(enemy->enemy_type);
        enemy->spawn_slot = arena_enemy_count;
        enemy->health = 0;

        if (field_count >= 4 && fields[3][0] != '\0')
        {
            enemy->spawn_slot = atoi(fields[3]);
        }

        if (enemy->spawn_slot < 0 || enemy->spawn_slot >= spawn_slot_count)
        {
            printf("Doom Agent Arena: invalid spawn slot %d on line %d\n",
                   enemy->spawn_slot,
                   line_number);
            continue;
        }

        if (field_count >= 6 && fields[5][0] != '\0')
        {
            enemy->health = atoi(fields[5]);
        }

        if (enemy->label[0] == '\0')
        {
            strncpy(enemy->label, enemy->enemy_id, sizeof(enemy->label) - 1);
        }

        Arena_AssignSpawnSlot(enemy);
        arena_enemy_count++;
    }

    fclose(file);

    printf("Doom Agent Arena: loaded %d enemy/enemies\n", arena_enemy_count);
}

void Arena_BuildRemainingSummary(char *buffer, int buffer_size)
{
    thinker_t *thinker;
    mobj_t *mobj;
    int remaining;

    if (buffer_size <= 0)
    {
        return;
    }

    buffer[0] = '\0';

    if (!Arena_ModeEnabled() || arena_enemy_count <= 0)
    {
        return;
    }

    remaining = 0;

    for (thinker = thinkercap.next; thinker != &thinkercap; thinker = thinker->next)
    {
        if (thinker->function.acp1 != (actionf_p1) P_MobjThinker)
        {
            continue;
        }

        mobj = (mobj_t *) thinker;
        if (mobj->arena_entity_index < 0 || mobj->health <= 0)
        {
            continue;
        }

        remaining++;
    }

    snprintf(buffer, buffer_size, "Enemies: %d/%d", remaining, arena_enemy_count);
}

void Arena_SpawnEnemies(void)
{
    int i;
    arena_enemy_t *enemy;
    mobj_t *mobj;

    if (!Arena_ModeEnabled())
    {
        return;
    }

    if (!Arena_EnemiesModeEnabled())
    {
        return;
    }

    for (i = 0; i < arena_enemy_count; i++)
    {
        enemy = &arena_enemies[i];

        mobj = P_SpawnMobj(enemy->x << FRACBITS,
                           enemy->y << FRACBITS,
                           ONFLOORZ,
                           enemy->type);

        mobj->angle = ANG45 * (enemy->angle / 45);
        mobj->arena_entity_index = i;
        strncpy(mobj->arena_entity_id, enemy->enemy_id,
                sizeof(mobj->arena_entity_id) - 1);
        mobj->arena_entity_id[sizeof(mobj->arena_entity_id) - 1] = '\0';
        strncpy(mobj->arena_label, enemy->label,
                sizeof(mobj->arena_label) - 1);
        mobj->arena_label[sizeof(mobj->arena_label) - 1] = '\0';

        if (enemy->health > 0)
        {
            mobj->health = enemy->health;
        }

        if (mobj->flags & MF_COUNTKILL)
        {
            totalkills++;
        }

        printf("Doom Agent Arena: spawned %s %s at (%d, %d)\n",
               enemy->enemy_type,
               enemy->enemy_id,
               enemy->x,
               enemy->y);
    }

    Agentic_ExportState();
}
