//
// Doom Agent Arena participant command parsing.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "i_timer.h"
#include "arena_enemies.h"
#include "arena_participant_commands.h"

typedef struct
{
    arena_participant_command_t command;
    char active_command_id[64];
    int start_ms;
    int duration_ms;
} participant_command_slot_t;

static participant_command_slot_t participant_slots[ARENA_PARTICIPANT_COUNT];

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

static int ClampInt(int value, int low, int high)
{
    if (value < low)
    {
        return low;
    }
    if (value > high)
    {
        return high;
    }
    return value;
}

static int ParseBool(const char *value)
{
    return !strcmp(value, "1")
        || !strcmp(value, "true")
        || !strcmp(value, "yes");
}

static int DurationMs(const char *issued_at_ms, const char *expires_at_ms, const char *duration_ms)
{
    double issued;
    double expires;
    int duration;

    issued = strtod(issued_at_ms, NULL);
    expires = strtod(expires_at_ms, NULL);
    duration = atoi(duration_ms);

    if (expires > issued)
    {
        duration = (int) (expires - issued);
    }

    if (duration <= 0)
    {
        duration = 100;
    }
    if (duration > 60000)
    {
        duration = 60000;
    }

    return duration;
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

static void BuildLastAction(arena_participant_command_t *command)
{
    char action[64];

    action[0] = '\0';
    if (command->forward > 0)
    {
        strncat(action, "forward", sizeof(action) - strlen(action) - 1);
    }
    else if (command->forward < 0)
    {
        strncat(action, "back", sizeof(action) - strlen(action) - 1);
    }

    if (command->strafe != 0)
    {
        if (action[0] != '\0')
        {
            strncat(action, "+", sizeof(action) - strlen(action) - 1);
        }
        strncat(action, command->strafe > 0 ? "strafe_right" : "strafe_left",
                sizeof(action) - strlen(action) - 1);
    }

    if (command->turn != 0)
    {
        if (action[0] != '\0')
        {
            strncat(action, "+", sizeof(action) - strlen(action) - 1);
        }
        strncat(action, command->turn > 0 ? "turn_right" : "turn_left",
                sizeof(action) - strlen(action) - 1);
    }

    if (command->attack)
    {
        if (action[0] != '\0')
        {
            strncat(action, "+", sizeof(action) - strlen(action) - 1);
        }
        strncat(action, "attack", sizeof(action) - strlen(action) - 1);
    }

    if (command->use)
    {
        if (action[0] != '\0')
        {
            strncat(action, "+", sizeof(action) - strlen(action) - 1);
        }
        strncat(action, "use", sizeof(action) - strlen(action) - 1);
    }

    if (action[0] == '\0')
    {
        CopyField(action, sizeof(action), "noop");
    }

    CopyField(command->last_action, sizeof(command->last_action), action);
}

static arena_participant_command_t NoopCommand(const char *status)
{
    arena_participant_command_t command;

    memset(&command, 0, sizeof(command));
    command.valid = true;
    CopyField(command.status, sizeof(command.status), status);
    CopyField(command.last_action, sizeof(command.last_action), "noop");
    return command;
}

void ArenaParticipantCommands_Init(void)
{
    int i;

    for (i = 0; i < ARENA_PARTICIPANT_COUNT; i++)
    {
        memset(&participant_slots[i], 0, sizeof(participant_slots[i]));
        participant_slots[i].command = NoopCommand("missing");
    }
}

static void ApplyCommand(arena_participant_id_t participant,
                         const char *command_id,
                         int duration_ms,
                         char **fields)
{
    participant_command_slot_t *slot;
    arena_participant_command_t command;

    slot = &participant_slots[participant];
    if (command_id == NULL || command_id[0] == '\0')
    {
        slot->command = NoopCommand("invalid");
        return;
    }

    if (strcmp(slot->active_command_id, command_id))
    {
        CopyField(slot->active_command_id, sizeof(slot->active_command_id), command_id);
        slot->start_ms = I_GetTimeMS();
        slot->duration_ms = duration_ms;
    }

    if (I_GetTimeMS() - slot->start_ms > slot->duration_ms)
    {
        slot->command = NoopCommand("expired");
        return;
    }

    memset(&command, 0, sizeof(command));
    command.forward = ClampInt(atoi(fields[6]), -1, 1);
    command.strafe = ClampInt(atoi(fields[7]), -1, 1);
    command.turn = ClampInt(atoi(fields[8]), -1, 1);
    command.attack = ParseBool(fields[9]);
    command.use = ParseBool(fields[10]);
    command.active = true;
    command.valid = true;
    CopyField(command.command_id, sizeof(command.command_id), command_id);
    CopyField(command.status, sizeof(command.status), "valid");
    BuildLastAction(&command);

    slot->command = command;
}

void ArenaParticipantCommands_Load(void)
{
    FILE *file;
    char line[256];
    char *fields[12];
    int line_number;
    int field_count;
    arena_participant_id_t participant;
    int duration_ms;
    int seen[ARENA_PARTICIPANT_COUNT];
    int i;

    for (i = 0; i < ARENA_PARTICIPANT_COUNT; i++)
    {
        seen[i] = false;
    }

    file = fopen(ARENA_PARTICIPANT_COMMAND_PATH, "r");
    if (file == NULL)
    {
        file = fopen("/" ARENA_PARTICIPANT_COMMAND_PATH, "r");
    }

    if (file == NULL)
    {
        for (i = 0; i < ARENA_PARTICIPANT_COUNT; i++)
        {
            participant_slots[i].command = NoopCommand("missing");
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

        field_count = SplitTsv(line, fields, 12);
        if (field_count < 12)
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

        duration_ms = DurationMs(fields[3], fields[4], fields[11]);
        ApplyCommand(participant, fields[2], duration_ms, fields);
        seen[participant] = true;
    }

    fclose(file);

    for (i = 0; i < ARENA_PARTICIPANT_COUNT; i++)
    {
        if (!seen[i])
        {
            participant_slots[i].command = NoopCommand("missing");
        }
    }
}

arena_participant_command_t ArenaParticipantCommands_Command(arena_participant_id_t participant)
{
    if (participant < 0 || participant >= ARENA_PARTICIPANT_COUNT)
    {
        return NoopCommand("invalid");
    }

    return participant_slots[participant].command;
}

const char *ArenaParticipantCommands_LastAction(arena_participant_id_t participant)
{
    if (participant < 0 || participant >= ARENA_PARTICIPANT_COUNT)
    {
        return "noop";
    }

    return participant_slots[participant].command.last_action;
}

const char *ArenaParticipantCommands_Status(arena_participant_id_t participant)
{
    if (participant < 0 || participant >= ARENA_PARTICIPANT_COUNT)
    {
        return "invalid";
    }

    return participant_slots[participant].command.status;
}
