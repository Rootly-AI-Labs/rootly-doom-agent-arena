//
// Doom Agent Arena participant intent parsing.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "i_timer.h"
#include "arena_participant_intents.h"

#define ARENA_PARTICIPANT_INTENT_GRACE_MS 2000
#define ARENA_PARTICIPANT_INTENT_LEGACY_FIELD_COUNT 12
#define ARENA_PARTICIPANT_INTENT_FIELD_COUNT 19

extern const char *Arena_RunId(void);
extern const char *Arena_ScenarioId(void);

typedef struct
{
    int present;
    double issued_at_ms;
    double expires_at_ms;
    char run_id[64];
    char scenario_id[64];
    char intent_id[64];
    char participant_id[32];
    char intent[32];
    char style[32];
    char target_id[32];
    char preferred_distance[32];
    char aggression[32];
    char duration_ms[32];
    char strafe_direction[32];
    char movement_bias[32];
    char fire_policy[32];
    char distance_policy[32];
    char replan_if[128];
    char sequence_number[32];
    char decision_cadence_ms[32];
} arena_participant_intent_row_t;

typedef struct
{
    arena_participant_intent_t intent;
    char active_intent_id[64];
    int start_ms;
    int duration_ms;
    double latest_issued_at_ms;
    int has_latest_sequence_number;
    int latest_sequence_number;
    char last_debug_state[512];
} arena_participant_intent_slot_t;

static arena_participant_intent_slot_t intent_slots[ARENA_PARTICIPANT_COUNT];
static char active_run_id[64];

static int IntentDurationMs(const arena_participant_intent_row_t *row);

static void CopyField(char *dest, size_t dest_size, const char *value)
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

static void Chomp(char *line)
{
    size_t len;

    len = strlen(line);
    while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r'))
    {
        line[len - 1] = '\0';
        len--;
    }
}

static int SplitTsv(char *line, char **fields, int max_fields)
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

static const char *ParticipantName(arena_participant_id_t participant)
{
    return participant == ARENA_PARTICIPANT_PLAYER_2 ? "player_2" : "player_1";
}

static int ParseParticipant(const char *value, arena_participant_id_t *participant)
{
    if (!strcmp(value, "player_1"))
    {
        *participant = ARENA_PARTICIPANT_PLAYER_1;
        return true;
    }
    if (!strcmp(value, "player_2"))
    {
        *participant = ARENA_PARTICIPANT_PLAYER_2;
        return true;
    }

    return false;
}

static int ValidIntent(const char *value)
{
    return !strcmp(value, "hold")
        || !strcmp(value, "engage_opponent")
        || !strcmp(value, "strafe_attack")
        || !strcmp(value, "search");
}

static int ValidStyle(const char *value)
{
    return !strcmp(value, "balanced")
        || !strcmp(value, "aggressive")
        || !strcmp(value, "evasive")
        || !strcmp(value, "cautious");
}

static int ValidStrafeDirection(const char *value)
{
    return !strcmp(value, "left")
        || !strcmp(value, "right")
        || !strcmp(value, "alternate")
        || !strcmp(value, "auto");
}

static int ValidMovementBias(const char *value)
{
    return !strcmp(value, "direct")
        || !strcmp(value, "circle")
        || !strcmp(value, "evasive")
        || !strcmp(value, "cautious");
}

static int ValidFirePolicy(const char *value)
{
    return !strcmp(value, "hold_fire")
        || !strcmp(value, "only_when_aligned")
        || !strcmp(value, "burst_when_aligned")
        || !strcmp(value, "suppressive");
}

static int ValidDistancePolicy(const char *value)
{
    return !strcmp(value, "close")
        || !strcmp(value, "maintain")
        || !strcmp(value, "kite");
}

static int OptionalPositiveInt(const char *value)
{
    char *end;
    long parsed;

    if (value == NULL || value[0] == '\0')
    {
        return true;
    }

    parsed = strtol(value, &end, 10);
    return end != value && *end == '\0' && parsed > 0;
}

static int OptionalNonNegativeInt(const char *value)
{
    char *end;
    long parsed;

    if (value == NULL || value[0] == '\0')
    {
        return true;
    }

    parsed = strtol(value, &end, 10);
    return end != value && *end == '\0' && parsed >= 0;
}

static int RowHasSequenceNumber(const arena_participant_intent_row_t *row)
{
    return row != NULL
        && row->sequence_number[0] != '\0'
        && OptionalNonNegativeInt(row->sequence_number);
}

static int RowSequenceNumber(const arena_participant_intent_row_t *row)
{
    return RowHasSequenceNumber(row) ? atoi(row->sequence_number) : 0;
}

static int RowHasUsableDuration(const arena_participant_intent_row_t *row)
{
    return row != NULL && IntentDurationMs(row) > 0;
}

static int RowFreshnessNewerOrEqual(const arena_participant_intent_row_t *candidate,
                                    const arena_participant_intent_row_t *current)
{
    if (RowHasSequenceNumber(candidate) && RowHasSequenceNumber(current))
    {
        if (RowSequenceNumber(candidate) != RowSequenceNumber(current))
        {
            return RowSequenceNumber(candidate) > RowSequenceNumber(current);
        }
    }

    return candidate->issued_at_ms >= current->issued_at_ms;
}

static int CandidatePreferred(const arena_participant_intent_row_t *candidate,
                              const arena_participant_intent_row_t *current)
{
    int candidate_usable;
    int current_usable;

    if (candidate == NULL || !candidate->present)
    {
        return false;
    }

    if (current == NULL || !current->present)
    {
        return true;
    }

    candidate_usable = RowHasUsableDuration(candidate);
    current_usable = RowHasUsableDuration(current);
    if (candidate_usable != current_usable)
    {
        return candidate_usable;
    }

    return RowFreshnessNewerOrEqual(candidate, current);
}

static int RowStaleForSlot(const arena_participant_intent_row_t *row,
                           const arena_participant_intent_slot_t *slot)
{
    if (row == NULL || slot == NULL)
    {
        return true;
    }

    if (RowHasSequenceNumber(row) && slot->has_latest_sequence_number)
    {
        if (RowSequenceNumber(row) < slot->latest_sequence_number)
        {
            return true;
        }
        if (RowSequenceNumber(row) > slot->latest_sequence_number)
        {
            return false;
        }
    }

    return row->issued_at_ms < slot->latest_issued_at_ms;
}

static void UpdateSlotFreshness(arena_participant_intent_slot_t *slot,
                                const arena_participant_intent_row_t *row)
{
    if (slot == NULL || row == NULL)
    {
        return;
    }

    slot->latest_issued_at_ms = row->issued_at_ms;
    if (RowHasSequenceNumber(row))
    {
        slot->has_latest_sequence_number = true;
        slot->latest_sequence_number = RowSequenceNumber(row);
    }
    else
    {
        slot->has_latest_sequence_number = false;
        slot->latest_sequence_number = 0;
    }
}

static arena_participant_id_t OpponentOf(arena_participant_id_t participant)
{
    return participant == ARENA_PARTICIPANT_PLAYER_1
        ? ARENA_PARTICIPANT_PLAYER_2
        : ARENA_PARTICIPANT_PLAYER_1;
}

static int IntentDurationMs(const arena_participant_intent_row_t *row)
{
    double duration;
    int fallback;

    if (row->expires_at_ms > row->issued_at_ms)
    {
        duration = row->expires_at_ms - row->issued_at_ms;
    }
    else if (row->expires_at_ms <= 0)
    {
        fallback = atoi(row->duration_ms);
        if (fallback <= 0)
        {
            return 0;
        }
        duration = fallback;
    }
    else
    {
        return 0;
    }

    if (duration > 60000)
    {
        return 60000;
    }

    return (int) duration;
}

static arena_participant_intent_t InactiveIntent(arena_participant_id_t participant,
                                                 const char *status,
                                                 const char *reason)
{
    arena_participant_intent_t intent;

    memset(&intent, 0, sizeof(intent));
    intent.participant = participant;
    intent.target_participant = OpponentOf(participant);
    intent.valid = true;
    CopyField(intent.intent, sizeof(intent.intent), "none");
    CopyField(intent.style, sizeof(intent.style), "balanced");
    CopyField(intent.strafe_direction, sizeof(intent.strafe_direction), "auto");
    CopyField(intent.movement_bias, sizeof(intent.movement_bias), "direct");
    CopyField(intent.fire_policy, sizeof(intent.fire_policy), "only_when_aligned");
    CopyField(intent.distance_policy, sizeof(intent.distance_policy), "maintain");
    intent.replan_if[0] = '\0';
    CopyField(intent.status, sizeof(intent.status), status);
    CopyField(intent.reason, sizeof(intent.reason), reason);
    return intent;
}

static void SetInactive(arena_participant_id_t participant,
                        const char *status,
                        const char *reason)
{
    intent_slots[participant].intent = InactiveIntent(participant, status, reason);
    intent_slots[participant].active_intent_id[0] = '\0';
    intent_slots[participant].start_ms = 0;
    intent_slots[participant].duration_ms = 0;
}

static void SetExpired(arena_participant_id_t participant, const char *reason)
{
    intent_slots[participant].intent = InactiveIntent(participant, "expired", reason);
    intent_slots[participant].duration_ms = 0;
}

static int SlotIntentStillLive(const arena_participant_intent_slot_t *slot,
                               int now)
{
    return slot != NULL
        && slot->intent.active
        && slot->duration_ms > 0
        && now - slot->start_ms <= slot->duration_ms + ARENA_PARTICIPANT_INTENT_GRACE_MS;
}

static void LogIntentChange(arena_participant_id_t participant)
{
    arena_participant_intent_slot_t *slot;
    arena_participant_intent_t *intent;
    char state[512];

    slot = &intent_slots[participant];
    intent = &slot->intent;
    snprintf(state,
             sizeof(state),
             "%d|%s|%s|%s|%s|%s",
             intent->active,
             intent->intent_id,
             intent->intent,
             intent->style,
             intent->status,
             intent->reason);

    if (!strcmp(slot->last_debug_state, state))
    {
        return;
    }

    CopyField(slot->last_debug_state, sizeof(slot->last_debug_state), state);
    printf("Doom Agent Arena: intent %s status=%s active=%d intent=%s style=%s reason=%s\n",
           ParticipantName(participant),
           intent->status,
           intent->active,
           intent->intent,
           intent->style,
           intent->reason);
}

static void ResetSlot(arena_participant_id_t participant)
{
    memset(&intent_slots[participant], 0, sizeof(intent_slots[participant]));
    intent_slots[participant].latest_issued_at_ms = -1;
    intent_slots[participant].has_latest_sequence_number = false;
    intent_slots[participant].latest_sequence_number = 0;
    intent_slots[participant].intent = InactiveIntent(participant, "missing", "intent file missing or empty");
}

void ArenaParticipantIntent_Init(void)
{
    int i;

    CopyField(active_run_id, sizeof(active_run_id), Arena_RunId());
    for (i = 0; i < ARENA_PARTICIPANT_COUNT; i++)
    {
        ResetSlot((arena_participant_id_t) i);
    }
}

void ArenaParticipantIntent_ClearDebugState(void)
{
    int i;

    for (i = 0; i < ARENA_PARTICIPANT_COUNT; i++)
    {
        intent_slots[i].last_debug_state[0] = '\0';
    }
}

static void RefreshRunState(void)
{
    if (strcmp(active_run_id, Arena_RunId()))
    {
        ArenaParticipantIntent_Init();
    }
}

static void CopyRowField(char *dest, size_t dest_size, const char *value)
{
    CopyField(dest, dest_size, value == NULL ? "" : value);
}

static void StoreCandidate(arena_participant_intent_row_t *row,
                           char **fields,
                           int field_count)
{
    row->present = true;
    row->issued_at_ms = strtod(fields[3], NULL);
    row->expires_at_ms = strtod(fields[4], NULL);
    CopyRowField(row->run_id, sizeof(row->run_id), fields[0]);
    CopyRowField(row->scenario_id, sizeof(row->scenario_id), fields[1]);
    CopyRowField(row->intent_id, sizeof(row->intent_id), fields[2]);
    CopyRowField(row->participant_id, sizeof(row->participant_id), fields[5]);
    CopyRowField(row->intent, sizeof(row->intent), fields[6]);
    CopyRowField(row->style, sizeof(row->style), fields[7]);
    CopyRowField(row->target_id, sizeof(row->target_id), fields[8]);
    CopyRowField(row->preferred_distance, sizeof(row->preferred_distance), fields[9]);
    CopyRowField(row->aggression, sizeof(row->aggression), fields[10]);
    CopyRowField(row->duration_ms, sizeof(row->duration_ms), fields[11]);
    CopyRowField(row->strafe_direction,
                 sizeof(row->strafe_direction),
                 field_count > 12 ? fields[12] : "auto");
    CopyRowField(row->movement_bias,
                 sizeof(row->movement_bias),
                 field_count > 13 ? fields[13] : "direct");
    CopyRowField(row->fire_policy,
                 sizeof(row->fire_policy),
                 field_count > 14 ? fields[14] : "only_when_aligned");
    CopyRowField(row->distance_policy,
                 sizeof(row->distance_policy),
                 field_count > 15 ? fields[15] : "maintain");
    CopyRowField(row->replan_if,
                 sizeof(row->replan_if),
                 field_count > 16 ? fields[16] : "");
    CopyRowField(row->sequence_number,
                 sizeof(row->sequence_number),
                 field_count > 17 ? fields[17] : "");
    CopyRowField(row->decision_cadence_ms,
                 sizeof(row->decision_cadence_ms),
                 field_count > 18 ? fields[18] : "");
}

static void ApplyCandidate(arena_participant_id_t participant,
                           const arena_participant_intent_row_t *row)
{
    arena_participant_intent_slot_t *slot;
    arena_participant_intent_t intent;
    arena_participant_id_t target_participant;
    int duration_ms;
    int now;

    slot = &intent_slots[participant];
    now = I_GetTimeMS();
    if (!row->present)
    {
        SetInactive(participant, "missing", "no active intent row");
        return;
    }

    if (row->intent_id[0] == '\0')
    {
        SetInactive(participant, "invalid", "missing intent_id");
        return;
    }

    if (!ValidIntent(row->intent))
    {
        SetInactive(participant, "invalid", "invalid intent");
        return;
    }

    if (!ValidStyle(row->style))
    {
        SetInactive(participant, "invalid", "invalid style");
        return;
    }

    if (!ValidStrafeDirection(row->strafe_direction))
    {
        SetInactive(participant, "invalid", "invalid strafe_direction");
        return;
    }

    if (!ValidMovementBias(row->movement_bias))
    {
        SetInactive(participant, "invalid", "invalid movement_bias");
        return;
    }

    if (!ValidFirePolicy(row->fire_policy))
    {
        SetInactive(participant, "invalid", "invalid fire_policy");
        return;
    }

    if (!ValidDistancePolicy(row->distance_policy))
    {
        SetInactive(participant, "invalid", "invalid distance_policy");
        return;
    }

    if (!OptionalNonNegativeInt(row->sequence_number))
    {
        SetInactive(participant, "invalid", "invalid sequence_number");
        return;
    }

    if (!OptionalPositiveInt(row->decision_cadence_ms))
    {
        SetInactive(participant, "invalid", "invalid decision_cadence_ms");
        return;
    }

    if (RowStaleForSlot(row, slot))
    {
        if (SlotIntentStillLive(slot, now))
        {
            return;
        }
        SetInactive(participant, "stale", "ignored older intent");
        return;
    }

    if (!ParseParticipant(row->target_id, &target_participant)
        || target_participant != OpponentOf(participant))
    {
        SetInactive(participant, "invalid", "target_id must be opposing participant");
        return;
    }

    duration_ms = IntentDurationMs(row);
    if (duration_ms <= 0)
    {
        SetInactive(participant, "expired", "expires_at_ms is not after issued_at_ms");
        return;
    }

    if (strcmp(slot->active_intent_id, row->intent_id))
    {
        CopyField(slot->active_intent_id, sizeof(slot->active_intent_id), row->intent_id);
        slot->start_ms = now;
    }

    slot->duration_ms = duration_ms;
    if (now - slot->start_ms > duration_ms + ARENA_PARTICIPANT_INTENT_GRACE_MS)
    {
        SetExpired(participant, "intent duration elapsed");
        return;
    }

    UpdateSlotFreshness(slot, row);

    memset(&intent, 0, sizeof(intent));
    intent.active = true;
    intent.valid = true;
    intent.participant = participant;
    intent.target_participant = target_participant;
    intent.preferred_distance = atoi(row->preferred_distance);
    intent.aggression = strtod(row->aggression, NULL);
    intent.duration_ms = duration_ms;
    intent.issued_at_ms = row->issued_at_ms;
    intent.expires_at_ms = row->expires_at_ms;
    intent.sequence_number = row->sequence_number[0] == '\0'
        ? 0
        : atoi(row->sequence_number);
    intent.has_sequence_number = row->sequence_number[0] != '\0';
    intent.decision_cadence_ms = row->decision_cadence_ms[0] == '\0'
        ? 0
        : atoi(row->decision_cadence_ms);
    CopyField(intent.intent_id, sizeof(intent.intent_id), row->intent_id);
    CopyField(intent.intent, sizeof(intent.intent), row->intent);
    CopyField(intent.style, sizeof(intent.style), row->style);
    CopyField(intent.strafe_direction,
              sizeof(intent.strafe_direction),
              row->strafe_direction);
    CopyField(intent.movement_bias,
              sizeof(intent.movement_bias),
              row->movement_bias);
    CopyField(intent.fire_policy,
              sizeof(intent.fire_policy),
              row->fire_policy);
    CopyField(intent.distance_policy,
              sizeof(intent.distance_policy),
              row->distance_policy);
    CopyField(intent.replan_if,
              sizeof(intent.replan_if),
              row->replan_if);
    if (now - slot->start_ms > duration_ms)
    {
        CopyField(intent.status, sizeof(intent.status), "grace");
        CopyField(intent.reason,
                  sizeof(intent.reason),
                  "active intent grace period");
    }
    else
    {
        CopyField(intent.status, sizeof(intent.status), "valid");
        CopyField(intent.reason, sizeof(intent.reason), "active intent");
    }
    slot->intent = intent;
}

void ArenaParticipantIntent_TickOrRefresh(void)
{
    FILE *file;
    char line[768];
    char *fields[ARENA_PARTICIPANT_INTENT_FIELD_COUNT];
    int line_number;
    int field_count;
    arena_participant_id_t participant;
    arena_participant_intent_row_t candidates[ARENA_PARTICIPANT_COUNT];
    int i;

    RefreshRunState();
    memset(candidates, 0, sizeof(candidates));

    file = fopen(ARENA_PARTICIPANT_INTENT_PATH, "r");
    if (file == NULL)
    {
        file = fopen("/" ARENA_PARTICIPANT_INTENT_PATH, "r");
    }

    if (file == NULL)
    {
        for (i = 0; i < ARENA_PARTICIPANT_COUNT; i++)
        {
            SetInactive((arena_participant_id_t) i, "missing", "intent file missing");
            LogIntentChange((arena_participant_id_t) i);
        }
        return;
    }

    line_number = 0;
    while (fgets(line, sizeof(line), file) != NULL)
    {
        line_number++;
        Chomp(line);
        if (line[0] == '\0')
        {
            continue;
        }
        if (line_number == 1 && !strncmp(line, "run_id", 6))
        {
            continue;
        }

        field_count = SplitTsv(line, fields, ARENA_PARTICIPANT_INTENT_FIELD_COUNT);
        if (field_count < ARENA_PARTICIPANT_INTENT_LEGACY_FIELD_COUNT)
        {
            continue;
        }
        if (strcmp(fields[0], Arena_RunId()) || strcmp(fields[1], Arena_ScenarioId()))
        {
            continue;
        }
        if (!ParseParticipant(fields[5], &participant))
        {
            continue;
        }

        {
            arena_participant_intent_row_t row;

            memset(&row, 0, sizeof(row));
            StoreCandidate(&row, fields, field_count);
            if (CandidatePreferred(&row, &candidates[participant]))
            {
                candidates[participant] = row;
            }
        }
    }

    fclose(file);

    for (i = 0; i < ARENA_PARTICIPANT_COUNT; i++)
    {
        ApplyCandidate((arena_participant_id_t) i, &candidates[i]);
        LogIntentChange((arena_participant_id_t) i);
    }
}

arena_participant_intent_t ArenaParticipantIntent_Get(arena_participant_id_t participant)
{
    if (participant < 0 || participant >= ARENA_PARTICIPANT_COUNT)
    {
        return InactiveIntent(ARENA_PARTICIPANT_PLAYER_1, "invalid", "invalid participant index");
    }

    return intent_slots[participant].intent;
}

boolean ArenaParticipantIntent_HasActive(arena_participant_id_t participant)
{
    if (participant < 0 || participant >= ARENA_PARTICIPANT_COUNT)
    {
        return false;
    }

    return intent_slots[participant].intent.active;
}
