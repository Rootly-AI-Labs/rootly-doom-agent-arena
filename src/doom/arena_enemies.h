//
// Doom Agent Arena enemy spawning.
//

#ifndef __ARENA_ENEMIES__
#define __ARENA_ENEMIES__

#include "doomtype.h"
#include "info.h"
#include "p_mobj.h"

#define ARENA_MAX_ENEMIES 24
#define ARENA_ENTITY_ID_MAX 32
#define ARENA_LABEL_MAX 64
#define ARENA_ENEMY_TYPE_MAX 32

typedef struct
{
    char enemy_id[ARENA_ENTITY_ID_MAX];
    char enemy_type[ARENA_ENEMY_TYPE_MAX];
    mobjtype_t type;
    char label[ARENA_LABEL_MAX];
    int spawn_slot;
    int health;
    int x;
    int y;
    int angle;
} arena_enemy_t;

boolean Arena_ModeEnabled(void);
boolean Arena_EnemiesModeEnabled(void);
boolean Arena_DuelModeEnabled(void);
void Arena_LoadRunMetadata(void);
const char *Arena_RunId(void);
const char *Arena_ScenarioId(void);
const char *Arena_Mode(void);
const char *Arena_Player1Model(void);
const char *Arena_Player2Model(void);
int Arena_Round(void);
int Arena_Seed(void);
int Arena_TimeoutSeconds(void);
boolean Arena_GetSpawnSlot(int spawn_slot, int *x, int *y, int *angle);
void Arena_LoadEnemies(void);
void Arena_SpawnEnemies(void);
int Arena_EnemyCount(void);
const char *Arena_EnemyId(int arena_entity_index);
const char *Arena_EnemyType(int arena_entity_index);
void Arena_BuildRemainingSummary(char *buffer, int buffer_size);

#endif
