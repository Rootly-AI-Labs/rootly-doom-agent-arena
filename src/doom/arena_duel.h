//
// Doom Agent Arena duel mode.
//

#ifndef __ARENA_DUEL__
#define __ARENA_DUEL__

#include <stdint.h>

#include "doomtype.h"
#include "p_mobj.h"

void ArenaDuel_InitLevel(void);
void ArenaDuel_SpawnPlayer2(void);
void ArenaDuel_CachePlayer1Mobj(mobj_t *mobj);
void ArenaDuel_RestorePlayer1Mobj(void);
void ArenaDuel_Ticker(void);
boolean ArenaDuel_IsEnabled(void);
boolean ArenaDuel_IsFinished(void);
boolean ArenaDuel_IsStarted(void);
boolean ArenaDuel_IsPlayer2(const mobj_t *mobj);
mobj_t *ArenaDuel_Player2Mobj(void);
int ArenaDuel_Player2AmmoBullets(void);
int ArenaDuel_ElapsedMs(void);
int ArenaDuel_ElapsedSecondsTenths(void);
int ArenaDuel_TimeoutSeconds(void);
const char *ArenaDuel_Phase(void);
const char *ArenaDuel_Winner(void);
const char *ArenaDuel_TerminalReason(void);
int ArenaDuel_Player1DamageDealt(void);
int ArenaDuel_Player2DamageDealt(void);
int ArenaDuel_Player1ShotsFired(void);
int ArenaDuel_Player2AttackRequests(void);
int ArenaDuel_Player2ShotsFired(void);
int ArenaDuel_Player1ShotsHit(void);
int ArenaDuel_Player2ShotsHit(void);
int ArenaDuel_Player1InvalidActions(void);
int ArenaDuel_Player2InvalidActions(void);
int ArenaDuel_EventCount(void);
const char *ArenaDuel_Event(int index);
void ArenaDuel_WriteEvents(void);
void ArenaDuel_RenderPlayer1View(void);
int ArenaDuel_Player1ViewWidth(void);
int ArenaDuel_Player1ViewHeight(void);
int ArenaDuel_Player1ViewFrame(void);
int ArenaDuel_Player1ViewNonzeroPixels(void);
uintptr_t ArenaDuel_Player1ViewPaletted(void);
uintptr_t ArenaDuel_Player1ViewRGBA(void);
void ArenaDuel_RenderPlayer2View(void);
int ArenaDuel_Player2ViewWidth(void);
int ArenaDuel_Player2ViewHeight(void);
int ArenaDuel_Player2ViewFrame(void);
int ArenaDuel_Player2ViewNonzeroPixels(void);
uintptr_t ArenaDuel_Player2ViewPaletted(void);
uintptr_t ArenaDuel_Player2ViewRGBA(void);
uintptr_t ArenaDuel_PalettePointer(void);

#endif
